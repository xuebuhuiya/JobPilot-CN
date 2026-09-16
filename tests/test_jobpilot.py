import json
from contextlib import closing
import sqlite3
import tempfile
import unittest
import subprocess
import sys
from pathlib import Path
from jobpilot import assess, connect, import_records, import_boss

PROFILE={'recruitment_type':'experienced','graduation_year':2025,'experience_years':1,'is_student':False,'cities':['上海']}
def job(**kw):
    return dict({'id':'1','title':'AI Agent开发','company':'测试','city':'上海','experience':'1-3年',
                 'jd':'岗位职责：负责Agent工具调用和业务服务开发，参与系统评测。'*20,
                 'score':90,'score_reason':'技术匹配','status':'ready','url':'https://example.com/job/1'},**kw)

class Tests(unittest.TestCase):
    def test_campus_high_score_never_candidate(self):
        self.assertEqual(assess(job(experience='在校/应届'),PROFILE)['decision'],'needs_verification')
    def test_explicit_wrong_cohort(self):
        self.assertEqual(assess(job(jd='仅限2027届毕业生。'+'负责Agent开发。'*60),PROFILE)['decision'],'excluded')
    def test_allowed_cohort(self):
        self.assertNotEqual(assess(job(jd='2025届及2026届毕业生。'+'负责Agent开发。'*60),PROFILE)['eligibility'],'fail')
    def test_cohort_range(self):
        self.assertNotEqual(assess(job(jd='招聘2024-2026届毕业生。'+'负责Agent开发。'*60),PROFILE)['eligibility'],'fail')
    def test_missing_graduation_not_guessed(self):
        p={**PROFILE,'graduation_year':None}
        self.assertNotEqual(assess(job(title='2027届校招'),p)['eligibility'],'fail')
    def test_short_generic_high_score(self):
        a=assess(job(jd='熟练掌握Python，1年以上开发经验。',score=99),PROFILE)
        self.assertEqual(a['decision'],'insufficient_jd')
        self.assertEqual(a['upstream_score'],99)
    def test_experience_gap(self):
        self.assertEqual(assess(job(experience='3-5年'),PROFILE)['decision'],'needs_verification')
    def test_full_jd_valid(self):
        self.assertEqual(assess(job(),PROFILE)['decision'],'review_candidate')
    def test_unscored_and_deleted(self):
        self.assertEqual(assess(job(score_reason=''),PROFILE)['decision'],'unscored')
        self.assertEqual(assess(job(deleted_at='today'),PROFILE)['decision'],'source_removed')
    def test_idempotency_and_review_invalidation(self):
        with tempfile.TemporaryDirectory() as tmp, closing(connect(Path(tmp)/'ledger.db')) as db:
            self.assertEqual(import_records(db,[job()],PROFILE)['inserted'],1)
            db.execute("UPDATE jobs SET review='worth_applying',application_state='submitted'"); db.commit()
            self.assertEqual(import_records(db,[job()],PROFILE)['unchanged'],1)
            self.assertEqual(db.execute('SELECT review FROM jobs').fetchone()[0],'worth_applying')
            self.assertEqual(import_records(db,[job(jd='新职责。'*100)],PROFILE)['updated'],1)
            row=db.execute('SELECT review,application_state FROM jobs').fetchone()
            self.assertEqual(tuple(row),('unreviewed','submitted'))
    def test_invalid_batch_rolls_back(self):
        with tempfile.TemporaryDirectory() as tmp, closing(connect(Path(tmp)/'ledger.db')) as db:
            with self.assertRaises(ValueError): import_records(db,[job(),job(id='')],PROFILE)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],0)
    def test_schema_failure_does_not_change_source(self):
        with tempfile.TemporaryDirectory() as tmp, closing(connect(Path(tmp)/'ledger.db')) as db:
            source=Path(tmp)/'source.db'
            with closing(sqlite3.connect(source)) as s: s.execute('CREATE TABLE jobs(id TEXT)')
            before=source.read_bytes()
            with self.assertRaises(ValueError): import_boss(db,source,PROFILE)
            self.assertEqual(before,source.read_bytes())
    def test_manual_review_and_application_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'ledger.db'
            with closing(connect(path)) as db: import_records(db,[job()],PROFILE)
            for args in [
                ['review','boss:1','--decision','needs_verification','--note','Check eligibility'],
                ['application','boss:1','--state','submission_unknown','--evidence','User checking platform history']
            ]:
                subprocess.run([sys.executable,'jobpilot.py','--db',str(path),*args],check=True,capture_output=True)
            with closing(connect(path)) as db:
                self.assertEqual(tuple(db.execute('SELECT review,application_state FROM jobs').fetchone()),('needs_verification','submission_unknown'))
                self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],3)

if __name__=='__main__': unittest.main()
