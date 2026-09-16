"""Local job ledger. Standard library only; never sends applications."""
import argparse
from contextlib import closing
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

VERSION = 'eligibility-quality-v1'
ROOT = Path(__file__).resolve().parent

def now():
    return datetime.now(timezone.utc).isoformat()

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def assess(job, profile):
    """Deterministic guardrails independent of the upstream numeric score."""
    jd = str(job.get('jd') or '')
    title = str(job.get('title') or '')
    experience = str(job.get('experience') or '')
    text = title + '\n' + jd
    reasons = []
    gate = 'pass'
    def flag(code, evidence, hard=False):
        nonlocal gate
        gate = 'fail' if hard or gate == 'fail' else 'needs_verification'
        reasons.append({'code': code, 'evidence': evidence})
    campus = bool(re.search(r'校招|应届|在校', title + experience)) or job.get('recruitment_type') == 'campus'
    # Treat only explicit graduation requirements as hard cohort exclusions.
    cohorts = re.findall(r'(20\d{2})\s*届', text)
    if cohorts and not profile.get('graduation_year'):
        flag('graduation_unknown', '岗位有届别要求，候选人毕业年份未提供')
    if cohorts and profile.get('graduation_year'):
        years = {int(x) for x in cohorts}
        for start,end in re.findall(r'(20\d{2})\s*[-—–~至]\s*(20\d{2})\s*届', text):
            if 0 <= int(end)-int(start) <= 10:
                years.update(range(int(start),int(end)+1))
        flexible = bool(re.search(r'不限届别|往届也可|往届亦可|往届可投|往届生亦可', text))
        if profile['graduation_year'] not in years and not flexible:
            flag('graduation_cohort', ' / '.join(sorted(set(cohorts))) + '届', True)
    if campus and profile.get('recruitment_type') == 'experienced':
        flag('campus_eligibility', title + ' / ' + experience)
    if re.search(r'仅限在校|在校生身份|须为在校', text) and profile.get('is_student') is False:
        flag('student_required', '岗位明确要求在校身份', True)
    # Experience tags and phrases may be flexible; flag instead of silently rejecting.
    mins = re.findall(r'(\d+)\s*[-–~至]\s*\d+\s*年|(?:至少|不少于)\s*(\d+)\s*年|(\d+)\s*年(?:以上|及以上)', experience + '\n' + jd)
    required = max([int(next(v for v in group if v)) for group in mins], default=0)
    if required and (profile.get('experience_years') is None or required > profile['experience_years']):
        flag('experience_gap', f'岗位出现至少 {required} 年经验要求；需核实可否放宽')
    city = str(job.get('city') or '')
    cities = profile.get('cities') or []
    if cities and (not city or not any(c in city for c in cities)):
        flag('location', city or '地点缺失')
    quality = []
    length = len(re.sub(r'\s', '', jd))
    if length < 250:
        quality.append({'code': 'short_jd', 'evidence': f'JD 去空白后仅 {length} 字符，阈值 250；需核实信息完整度'})
    if not re.search(r'职责|负责|参与|开发|设计|建设|responsibilit|you will', jd, re.I):
        quality.append({'code': 'missing_duties', 'evidence': '未识别具体职责描述'})
    if re.search(r'agent|智能体|大模型', title, re.I) and not re.search(r'agent|智能体|大模型|langgraph|langchain|LLM|RAG|工具调用', jd, re.I):
        quality.append({'code': 'title_jd_mismatch', 'evidence': '标题涉及 Agent/大模型，但正文未识别相关职责'})
    noise = re.findall(r'BOSS直聘|kanzhun|岗直聘位', jd, re.I)
    warnings = [{'code':'watermark_noise', 'evidence':' / '.join(sorted(set(noise)))}] if noise else []
    score = job.get('score')
    scored = bool(job.get('score_reason')) and isinstance(score, (int, float))
    if job.get('deleted_at'):
        decision = 'source_removed'
    elif gate == 'fail':
        decision = 'excluded'
    elif quality:
        decision = 'insufficient_jd'
    elif gate == 'needs_verification':
        decision = 'needs_verification'
    elif not scored:
        decision = 'unscored'
    elif score < 70:
        decision = 'low_match'
    else:
        decision = 'review_candidate'
    return {'version': VERSION, 'eligibility': gate, 'eligibility_reasons': reasons,
            'quality': 'insufficient' if quality else 'adequate', 'quality_reasons': quality,
            'warnings': warnings, 'decision': decision, 'upstream_score': score,
            'note': '规则通过不代表全部资格已确认；原始分数不是录用概率。'}

def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript('''
    CREATE TABLE IF NOT EXISTS jobs (
      key TEXT PRIMARY KEY, source TEXT NOT NULL, source_id TEXT NOT NULL,
      raw_json TEXT NOT NULL, assessment_json TEXT NOT NULL, fingerprint TEXT NOT NULL,
      imported_at TEXT NOT NULL, review TEXT NOT NULL DEFAULT 'unreviewed',
      review_note TEXT NOT NULL DEFAULT '', application_state TEXT NOT NULL DEFAULT 'not_applied');
    CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY, job_key TEXT, kind TEXT, details TEXT, at TEXT);
    CREATE TABLE IF NOT EXISTS snapshots (
      job_key TEXT, fingerprint TEXT, raw_json TEXT, at TEXT,
      PRIMARY KEY(job_key,fingerprint));
    ''')
    return db

def import_records(db, records, profile):
    counts = {'inserted':0, 'updated':0, 'unchanged':0}
    with db:
        for raw in records:
            source = str(raw.get('source_platform') or 'boss')
            source_id = str(raw.get('source_job_id') or raw.get('id') or '')
            if not source_id:
                raise ValueError('Missing source job ID; import rolled back')
            key = source + ':' + source_id
            result = assess(raw, profile)
            fingerprint = digest({'raw':raw, 'profile':profile, 'rules':VERSION})
            old = db.execute('SELECT * FROM jobs WHERE key=?',(key,)).fetchone()
            if old and old['fingerprint']==fingerprint:
                counts['unchanged']+=1
                continue
            raw_json = json.dumps(raw, ensure_ascii=False)
            assessment_json = json.dumps(result, ensure_ascii=False)
            db.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?)',(key,fingerprint,raw_json,now()))
            if old:
                db.execute("UPDATE jobs SET raw_json=?,assessment_json=?,fingerprint=?,imported_at=?,review='unreviewed',review_note='' WHERE key=?",
                           (raw_json,assessment_json,fingerprint,now(),key))
                counts['updated']+=1
            else:
                db.execute('INSERT INTO jobs(key,source,source_id,raw_json,assessment_json,fingerprint,imported_at) VALUES(?,?,?,?,?,?,?)',
                           (key,source,source_id,raw_json,assessment_json,fingerprint,now()))
                counts['inserted']+=1
            db.execute('INSERT INTO events(job_key,kind,details,at) VALUES(?,?,?,?)',
                       (key,'import_updated' if old else 'imported',fingerprint,now()))
    return counts

def import_boss(db, path, profile):
    # A single read-only transaction observes committed SQLite state, including WAL.
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True)) as src:
        src.row_factory=sqlite3.Row
        columns={r[1] for r in src.execute('PRAGMA table_info(jobs)')}
        if not {'id','title','company','jd','url','score','score_reason'} <= columns:
            raise ValueError('Unsupported BossHunter jobs schema')
        src.execute('BEGIN')
        records=[dict(row) for row in src.execute('SELECT * FROM jobs')]
    return import_records(db, records, profile)

LABELS={'excluded':'排除','insufficient_jd':'信息不足','needs_verification':'资格待核实',
        'unscored':'待评分','low_match':'低匹配','review_candidate':'可人工评估','source_removed':'来源已移除'}

def export_report(db, target):
    records=[]
    for row in db.execute('SELECT * FROM jobs'):
        records.append((dict(row),json.loads(row['raw_json']),json.loads(row['assessment_json'])))
    order={'review_candidate':0,'needs_verification':1,'insufficient_jd':2,'unscored':3,'low_match':4,'excluded':5,'source_removed':6}
    records.sort(key=lambda r:(order[r[2]['decision']],-(r[2]['upstream_score'] or 0)))
    def clean(v): return str(v or '').replace('|','／').replace('\n',' ')
    lines=['# JobPilot-CN 统一岗位池','',f'生成时间：{now()}；共 {len(records)} 条；规则 {VERSION}。',
           '', '原始评分与资格、JD 质量分开显示；本系统没有投递功能。人工结论默认未审阅。',
           '', '| 公司 / 岗位 | 原分 | 系统判断 | 人工结论 | 原因 |','|---|---:|---|---|---|']
    for row,raw,a in records:
        reasons=a['eligibility_reasons']+a['quality_reasons']+a['warnings']
        lines.append(f"| {clean(raw.get('company'))} / {clean(raw.get('title'))} | {a['upstream_score']} | {LABELS[a['decision']]} | {row['review']} | {clean('；'.join(x['evidence'] for x in reasons)) or '待人工核对职责和事实证据'} |")
    for row,raw,a in records:
        jd = str(raw.get('jd') or '缺失')
        fence = '`' * max(3, max([len(x) for x in re.findall(r'`+',jd)],default=0)+1)
        url = str(raw.get('url') or '')
        link = f'[原始岗位](<{url}>)' if re.match(r'^https?://[^\s<>]+$',url) else '来源链接格式无效，需核实'
        lines+=['',f"## {clean(raw.get('company'))} / {clean(raw.get('title'))}",'',f"ID：`{row['key']}`",'',
                link,'',f"人工备注：{row['review_note'] or '无'}；申请状态：{row['application_state']}",'',
                '上游评分理由：'+str(raw.get('score_reason') or '未评分'),'', '### 原始 JD','',fence+'text',jd,fence]
    target=Path(target); target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return {label:sum(a['decision']==key for _,_,a in records) for key,label in LABELS.items()}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=ROOT/'data/jobpilot.db')
    sub=parser.add_subparsers(dest='command',required=True)
    imp=sub.add_parser('import-boss'); imp.add_argument('--source',type=Path,required=True); imp.add_argument('--profile',type=Path,required=True)
    manual=sub.add_parser('import-json'); manual.add_argument('file',type=Path); manual.add_argument('--profile',type=Path,required=True)
    exp=sub.add_parser('report'); exp.add_argument('--output',type=Path,default=ROOT/'data/job-pool.md')
    rev=sub.add_parser('review'); rev.add_argument('key'); rev.add_argument('--decision',choices=['worth_applying','unsuitable','needs_verification'],required=True); rev.add_argument('--note',required=True)
    app=sub.add_parser('application'); app.add_argument('key'); app.add_argument('--state',choices=['not_applied','prepared','submitted','submission_unknown','interview','rejected','offer','withdrawn'],required=True); app.add_argument('--evidence',required=True)
    args=parser.parse_args()
    with closing(connect(args.db)) as db, db:
        if args.command.startswith('import-'):
            profile=json.loads(args.profile.read_text(encoding='utf-8-sig'))
            result=import_boss(db,args.source,profile) if args.command=='import-boss' else import_records(db,json.loads(args.file.read_text(encoding='utf-8-sig')),profile)
        elif args.command=='report': result=export_report(db,args.output)
        elif args.command=='review':
            if not db.execute('SELECT 1 FROM jobs WHERE key=?',(args.key,)).fetchone():
                raise ValueError('Unknown job key')
            db.execute('UPDATE jobs SET review=?,review_note=? WHERE key=?',(args.decision,args.note,args.key))
            db.execute('INSERT INTO events(job_key,kind,details,at) VALUES(?,?,?,?)',(args.key,'human_review',json.dumps({'decision':args.decision,'note':args.note},ensure_ascii=False),now()))
            result={'review_saved':args.key}
        else:
            if not args.evidence.strip(): raise ValueError('Evidence or user confirmation note is required')
            if not db.execute('SELECT 1 FROM jobs WHERE key=?',(args.key,)).fetchone(): raise ValueError('Unknown job key')
            db.execute('UPDATE jobs SET application_state=? WHERE key=?',(args.state,args.key))
            db.execute('INSERT INTO events(job_key,kind,details,at) VALUES(?,?,?,?)',(args.key,'manual_application_update',json.dumps({'state':args.state,'evidence':args.evidence},ensure_ascii=False),now()))
            result={'application_recorded':args.key,'state':args.state,'action':'record_only'}
        print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__': main()
