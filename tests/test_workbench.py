import json
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from jobpilot import connect, import_records
from workbench import Server


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.db = self.path/'test.db'
        with closing(connect(self.db)) as db:
            import_records(db,[{'id':'1','company':'测试','title':'Agent开发','experience':'1-3年',
                'jd':'负责Agent开发和工具调用。'*40,'score':90,'score_reason':'test','city':'上海'},
                {'id':'2','company':'另一公司','title':'校招','experience':'在校/应届','jd':'负责开发。'*100}],
                {'recruitment_type':'experienced'})
        self.server = Server(('127.0.0.1',0),self.db,self.path/'missing.db',self.path/'missing.json')
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:'+str(self.server.server_port)
        self.state = self.get('/api/state')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def get(self,path):
        with urlopen(self.url+path) as r: return json.load(r)

    def post(self,path,data,origin=None,token=None):
        req = Request(self.url+path,data=json.dumps(data).encode(),headers={
            'Content-Type':'application/json','Origin':origin or self.url,
            'X-JobPilot-Token':token if token is not None else self.state['csrf_token']})
        with urlopen(req) as r: return json.load(r)

    def test_source_and_private_files_not_served(self):
        for path in ['/private/candidate-rules.json','/../workbench.py','/data/jobpilot.db']:
            with self.assertRaises(HTTPError) as error: self.get(path)
            self.assertEqual(error.exception.code,404)

    def test_cross_origin_and_missing_token_rejected(self):
        for kwargs in [{'origin':'https://evil.example'},{'token':''}]:
            with self.assertRaises(HTTPError) as error: self.post('/api/sync',{},**kwargs)
            self.assertEqual(error.exception.code,403)

    def test_review_and_application_are_separate(self):
        j=self.state['jobs'][0]
        self.post('/api/review',{'key':j['key'],'fingerprint':j['fingerprint'],'state':'needs_verification','note':'核实年限'})
        self.post('/api/contacts',{'job_key':j['key'],'company':'测试','person':'HR','kind':'greeting_sent',
            'occurred_at':'2026-09-16T15:57:00+08:00','note':'本人确认已打招呼'})
        state=self.get('/api/state')
        self.assertEqual(state['jobs'][0]['review'],'needs_verification')
        self.assertEqual(state['jobs'][0]['application_state'],'not_applied')
        self.assertEqual(len(state['contacts']),1)
        self.post('/api/application',{'key':j['key'],'fingerprint':j['fingerprint'],'state':'submitted','note':'本人确认提交成功'})
        self.assertEqual(self.get('/api/state')['jobs'][0]['application_state'],'submitted')
        self.assertEqual(len(self.get('/api/events')),4)

    def test_stale_save_and_excluded_approval_rejected(self):
        for j,fp in [(self.state['jobs'][0],'outdated'),(self.state['jobs'][1],self.state['jobs'][1]['fingerprint'])]:
            with self.assertRaises(HTTPError) as error:
                self.post('/api/review',{'key':j['key'],'fingerprint':fp,'state':'worth_applying','note':'test'})
            self.assertEqual(error.exception.code,400)

    def test_ambiguous_contact_and_invalid_link(self):
        self.post('/api/contacts',{'company':'测试','kind':'greeting_sent','occurred_at':'2026-09-16T15:00:00+08:00','note':'公司确认，岗位未知'})
        c=self.get('/api/state')['contacts'][0]
        self.assertIsNone(c['job_key'])
        with self.assertRaises(HTTPError):self.post('/api/contacts/link',{'id':c['id'],'job_key':'boss:2'})
        self.post('/api/contacts/link',{'id':c['id'],'job_key':'boss:1'})
        self.assertEqual(self.get('/api/state')['contacts'][0]['job_key'],'boss:1')

    def test_sync_failure_keeps_ledger(self):
        with self.assertRaises(HTTPError) as error:self.post('/api/sync',{})
        self.assertEqual(error.exception.code,503)
        self.assertEqual(len(self.get('/api/state')['jobs']),2)


if __name__ == '__main__': unittest.main()
