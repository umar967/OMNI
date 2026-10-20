"""Integration tests use temporary data and a stubbed model; never call Gemini."""
import base64
import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from app import storage as db
from app.server import app, evaluate_run

BACKEND = Path(__file__).resolve().parents[1]
HEADERS = {'X-OMNI-Client':'workspace'}

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = db.ROOT
        db.ROOT = Path(self.temp.name)
        for folder in ('personas','results','screenshots'):
            shutil.copytree(BACKEND/folder,db.ROOT/folder)
        self.client = TestClient(app)

    def tearDown(self):
        db.ROOT = self.original
        self.temp.cleanup()

    def post(self,path,data):
        return self.client.post(path,json=data,headers=HEADERS)

    def plan(self):
        return self.post('/api/plans',{'url':'http://127.0.0.1:5173/login?mode=signup','instructions':'Create an account','persona_id':'older_user','screenshot_id':'signup.png','mode':'UX'}).json()

    def test_existing_data_and_frontend(self):
        people = self.client.get('/api/personas').json()
        self.assertEqual({p['id'] for p in people},{'older_user','first_time_user'})
        reports = self.client.get('/api/reports').json()
        self.assertEqual(len(reports),2)
        self.assertTrue(all(r['imported'] for r in reports))
        self.assertTrue(all('score' not in r for r in reports))
        self.assertIn('src/app.js',self.client.get('/').text)
        self.assertEqual(self.client.get('/api/screenshots/signup.png').status_code,200)

    def test_create_edit_persona_and_project(self):
        body={'name':'Presentation visitor','goal':'Complete signup','criteria':['Readable text','Clear labels']}
        person=self.post('/api/personas',body).json()
        body['name']='Updated visitor'
        response=self.client.put('/api/personas/'+person['id'],json=body,headers=HEADERS)
        self.assertEqual(response.json()['name'],'Updated visitor')
        self.assertEqual(db.read(db.safe_file('personas',person['id']))['name'],'Updated visitor')
        project=self.post('/api/projects',{'name':'TestLab','url':'http://127.0.0.1:5173/'}).json()
        self.assertEqual(self.client.get('/api/projects').json()[0]['id'],project['id'])

    def test_plan_uses_persona_criteria_and_rejects_qa(self):
        plan=self.plan()
        self.assertEqual(len(plan['cases']),5)
        plan['cases'][0]['selected']=False
        plan['cases'][1]['title']='Edited criterion'
        saved=self.client.put('/api/plans/'+plan['id'],json={'cases':plan['cases']},headers=HEADERS).json()
        self.assertFalse(saved['cases'][0]['selected'])
        self.assertEqual(saved['cases'][1]['title'],'Edited criterion')
        bad={k:plan[k] for k in ('url','instructions','persona_id','screenshot_id')}
        bad['mode']='QA'
        self.assertEqual(self.post('/api/plans',bad).status_code,422)

    def test_run_persists_snapshot_findings_and_real_evidence_link(self):
        plan=self.plan()
        finding={'issue':'Low contrast','category':'Readability','severity':'Medium','explanation':'Hard to read','evidence':'Light text','recommendation':'Increase contrast'}
        with patch.dict(os.environ,{'GEMINI_API_KEY':'unit-test-placeholder'}),patch('app.server.EXECUTOR.submit'):
            run=self.post('/api/runs',{'plan_id':plan['id']}).json()
            self.assertEqual(run['status'],'queued')
            self.assertEqual(self.post('/api/runs',{'plan_id':plan['id']}).status_code,409)
            with patch('app.server.evaluate_ux',return_value={'persona':'Older / Low-Tech User','task':'Create an account','findings':[finding]}):
                evaluate_run(run['id'],run['plan'])
        saved=self.client.get('/api/runs/'+run['id']).json()
        self.assertEqual(saved['status'],'completed')
        report=self.client.get('/api/reports/'+saved['report_id']).json()
        self.assertEqual(report['findings'],[finding])
        self.assertEqual(report['screenshot_id'],'signup.png')
        self.assertEqual(report['persona_snapshot']['name'],'Older / Low-Tech User')
        self.assertNotIn('score',report)

    def test_missing_key_and_model_failure_are_not_mocked(self):
        plan=self.plan()
        with patch.dict(os.environ,{'GEMINI_API_KEY':''}):
            self.assertEqual(self.post('/api/runs',{'plan_id':plan['id']}).status_code,503)
        with patch.dict(os.environ,{'GEMINI_API_KEY':'unit-test-placeholder'}),patch('app.server.EXECUTOR.submit'):
            run=self.post('/api/runs',{'plan_id':plan['id']}).json()
            with patch('app.server.evaluate_ux',side_effect=Exception('SDK failure')):
                evaluate_run(run['id'],run['plan'])
        self.assertEqual(self.client.get('/api/runs/'+run['id']).json()['status'],'failed')
        self.assertEqual(len(self.client.get('/api/reports').json()),2)

    def test_upload_validation_and_local_capture_guard(self):
        image=io.BytesIO();Image.new('RGB',(20,20)).save(image,format='PNG')
        response=self.post('/api/screenshots',{'name':'Test image','data':base64.b64encode(image.getvalue()).decode()})
        self.assertEqual(response.status_code,201)
        self.assertEqual(self.client.get(response.json()['url']).status_code,200)
        self.assertEqual(self.post('/api/screenshots',{'data':'not an image'}).status_code,400)
        self.assertEqual(self.post('/api/capture',{'url':'https://example.com'}).status_code,422)
        self.assertEqual(self.client.post('/api/personas',json={}).status_code,403)
        self.assertEqual(self.client.get('/api/personas',headers={'Host':'evil.example'}).status_code,403)
        self.assertEqual(self.post('/api/plans',{'url':'http://127.0.0.1:5173','instructions':'Review','persona_id':'../private','screenshot_id':'signup.png'}).status_code,400)

if __name__=='__main__':
    unittest.main()
