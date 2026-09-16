"""JobPilot local web workbench. No external messaging or submission endpoints."""
import argparse
from contextlib import closing
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import sqlite3
from urllib.parse import urlsplit

from jobpilot import ROOT, LABELS, VERSION, connect, import_boss, now

REVIEWS = {'unreviewed':'未审阅', 'worth_applying':'值得申请', 'needs_verification':'待核实', 'unsuitable':'不合适'}
APPLICATIONS = {'not_applied':'未投递', 'prepared':'材料已准备', 'submitted':'已正式投递',
                'submission_unknown':'提交结果待确认', 'interview':'面试中', 'rejected':'已拒绝', 'offer':'已获 Offer', 'withdrawn':'已撤回'}
CONTACTS = {'greeting_sent':'已打招呼', 'resume_sent':'已发送简历', 'replied':'对方已回复', 'follow_up':'已跟进'}

def init_db(path):
    with closing(connect(path)) as db, db:
        db.execute('''CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY, job_key TEXT, company TEXT NOT NULL, person TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL, occurred_at TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL,
            external_ref TEXT UNIQUE)''')

def connection(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    return db

def snapshot(db):
    jobs = []
    for row in db.execute('SELECT * FROM jobs'):
        item = dict(row)
        item['raw'] = json.loads(item.pop('raw_json'))
        item['assessment'] = json.loads(item.pop('assessment_json'))
        jobs.append(item)
    return {'jobs':jobs, 'contacts':[dict(r) for r in db.execute('SELECT * FROM contacts ORDER BY occurred_at DESC,id DESC')],
            'labels':LABELS, 'reviews':REVIEWS, 'applications':APPLICATIONS, 'contact_types':CONTACTS,
            'rules_version':VERSION}

def required(data, key, limit=4000):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value)>limit:
        raise ValueError(f'{key} 不能为空且不得超过 {limit} 字符')
    return value.strip()

def job_exists(db, key):
    row = db.execute('SELECT * FROM jobs WHERE key=?', (key,)).fetchone()
    if not row:
        raise ValueError('岗位不存在，请刷新后重试')
    return row

def mutate(db, route, data):
    with db:
        if route in {'/api/review','/api/application'}:
            key = required(data, 'key', 300)
            row = job_exists(db, key)
            # Reject a save from a stale detail pane after an import/reassessment.
            if required(data,'fingerprint',100) != row['fingerprint']:
                raise ValueError('岗位已更新，请刷新并重新核对后保存')
            note = required(data,'note')
            state = required(data,'state',40)
            if route == '/api/review':
                if state not in REVIEWS: raise ValueError('无效的审阅状态')
                if state == 'worth_applying' and json.loads(row['assessment_json'])['decision'] in {'excluded','source_removed'}:
                    raise ValueError('已排除或移除的岗位不能标为值得申请；请先核实来源与资格')
                db.execute('UPDATE jobs SET review=?,review_note=? WHERE key=?', (state,note,key))
                kind = 'human_review'
            else:
                if state not in APPLICATIONS: raise ValueError('无效的申请状态')
                db.execute('UPDATE jobs SET application_state=? WHERE key=?', (state,key))
                kind = 'manual_application_update'
            db.execute('INSERT INTO events(job_key,kind,details,at) VALUES(?,?,?,?)',
                       (key,kind,json.dumps({'state':state,'note':note,'actor':'user','action':'record_only'},ensure_ascii=False),now()))
        elif route == '/api/contacts':
            company, kind = required(data,'company',200), required(data,'kind',40)
            if kind not in CONTACTS: raise ValueError('无效的沟通类型')
            key = data.get('job_key') or None
            if key:
                row = job_exists(db, required(data,'job_key',300))
                if company != json.loads(row['raw_json']).get('company'):
                    raise ValueError('公司与关联岗位不一致')
            person = data.get('person','')
            if not isinstance(person,str) or len(person)>100: raise ValueError('联系人过长')
            note = required(data,'note')
            occurred = required(data,'occurred_at',32)
            from datetime import datetime
            parsed = datetime.fromisoformat(occurred)
            if parsed.tzinfo is None: raise ValueError('沟通时间必须包含时区')
            db.execute('INSERT INTO contacts(job_key,company,person,kind,occurred_at,note,created_at) VALUES(?,?,?,?,?,?,?)',
                       (key,company,person,kind,occurred,note,now()))
        elif route == '/api/contacts/link':
            contact_id = data.get('id')
            if not isinstance(contact_id,int): raise ValueError('无效的沟通记录')
            contact = db.execute('SELECT * FROM contacts WHERE id=?',(contact_id,)).fetchone()
            if not contact: raise ValueError('沟通记录不存在')
            key = data.get('job_key') or None
            if key:
                row = job_exists(db,required(data,'job_key',300))
                if json.loads(row['raw_json']).get('company') != contact['company']:
                    raise ValueError('只能关联同公司的岗位')
            db.execute('UPDATE contacts SET job_key=? WHERE id=?',(key,contact_id))
            db.execute('INSERT INTO events(job_key,kind,details,at) VALUES(?,?,?,?)',
                       (key or 'contact:'+str(contact_id),'contact_link',json.dumps({'id':contact_id,'from':contact['job_key'],'to':key},ensure_ascii=False),now()))
        else:
            raise ValueError('未知操作')
    return {'ok':True}

class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, db_path, source_path, profile_path):
        self.db_path, self.source_path, self.profile_path = map(Path,(db_path,source_path,profile_path))
        init_db(self.db_path)
        self.token = secrets.token_urlsafe(32)
        super().__init__(address, Handler)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args): pass

    def respond(self, status, data, content_type='application/json; charset=utf-8'):
        body = json.dumps(data,ensure_ascii=False).encode() if not isinstance(data,bytes) else data
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

    def do_GET(self):
        if not self.valid_host(): return self.respond(403,{'error':'Invalid host'})
        path = urlsplit(self.path).path
        if path == '/api/health': return self.respond(200,{'app':'JobPilot-CN','status':'ok','version':'0.2.0'})
        if path == '/api/state':
            with closing(connection(self.server.db_path)) as db: result = snapshot(db)
            result['csrf_token'] = self.server.token
            return self.respond(200,result)
        if path == '/api/events':
            with closing(connection(self.server.db_path)) as db:
                result = [dict(r) for r in db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 300')]
            return self.respond(200,result)
        assets = {'/':('index.html','text/html; charset=utf-8'), '/app.js':('app.js','text/javascript; charset=utf-8'), '/style.css':('style.css','text/css; charset=utf-8')}
        if path in assets:
            name, mime = assets[path]
            return self.respond(200,(ROOT/'web'/name).read_bytes(),mime)
        self.respond(404,{'error':'页面不存在'})

    def do_POST(self):
        origin = self.headers.get('Origin')
        if not self.valid_host() or origin != 'http://' + self.headers.get('Host','') or self.headers.get('X-JobPilot-Token') != self.server.token:
            return self.respond(403,{'error':'请求来源无效，请从工作台刷新后重试'})
        if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
            return self.respond(415,{'error':'需要 JSON 请求'})
        try:
            size = int(self.headers.get('Content-Length','0'))
            if not 0<size<=65536: raise ValueError('请求大小无效')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data,dict): raise ValueError('无效的数据格式')
            with closing(connection(self.server.db_path)) as db:
                if self.path == '/api/sync':
                    profile = json.loads(self.server.profile_path.read_text(encoding='utf-8-sig'))
                    result = import_boss(db,self.server.source_path,profile)
                else:
                    result = mutate(db,self.path,data)
            self.respond(200,result)
        except (ValueError,TypeError,KeyError) as exc:
            self.respond(400,{'error':str(exc)})
        except (OSError,sqlite3.Error):
            self.respond(503,{'error':'本地数据暂不可用，请检查来源、配置文件或稍后重试'})

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',type=int,default=8787)
    p.add_argument('--db',type=Path,default=ROOT/'data/jobpilot.db')
    p.add_argument('--source',type=Path,default=ROOT.parent/'upstream/BossHunter/data/bosshunter.db')
    p.add_argument('--profile',type=Path,default=ROOT/'private/candidate-rules.json')
    args = p.parse_args()
    with Server(('127.0.0.1',args.port),args.db,args.source,args.profile) as server:
        print(f'JobPilot-CN http://127.0.0.1:{args.port}',flush=True)
        server.serve_forever()

if __name__ == '__main__': main()
