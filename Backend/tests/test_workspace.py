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
from Backend.app import storage as db
from Backend.app.server import app, evaluate_run

WORKSPACE = Path(__file__).resolve().parents[1]
HEADERS = {'X-OMNI-Client':'workspace'}

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = db.ROOT
        db.ROOT = Path(self.temp.name)
        for folder in ('personas','results','screenshots'):
            source = WORKSPACE/folder
            shutil.copytree(source,db.ROOT/folder,ignore=shutil.ignore_patterns('exploration_*'))
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
        self.assertEqual({p['id'] for p in people},{p.stem for p in (WORKSPACE/'personas').glob('*.json')})
        reports = self.client.get('/api/reports').json()
        self.assertEqual(len(reports),2)
        self.assertTrue(all(r['imported'] for r in reports))
        self.assertTrue(all('score' not in r for r in reports))
        self.assertIn('src/app.js',self.client.get('/').text)
        self.assertEqual(self.client.get('/api/screenshots/signup.png').status_code,200)

    def test_live_plan_without_screenshot_and_partial_report(self):
        body = {'url':'https://example.com/', 'instructions':'Find the help page',
                'persona_id':'older_user', 'method':'live', 'max_actions':3}
        response = self.post('/api/plans', body)
        self.assertEqual(response.status_code, 201)
        plan = response.json()
        self.assertIsNone(plan['screenshot_id'])
        with patch.dict(os.environ, {'GEMINI_API_KEY':'test'}), patch('Backend.app.server.EXECUTOR.submit'):
            run = self.post('/api/runs', {'plan_id':plan['id']}).json()
            with patch('Backend.app.live.sync_playwright', side_effect=RuntimeError('browser unavailable')):
                evaluate_run(run['id'], plan)
        saved = self.client.get('/api/runs/' + run['id']).json()
        self.assertEqual(saved['status'], 'failed')
        report = self.client.get('/api/reports/' + saved['report_id']).json()
        self.assertEqual(report['kind'], 'exploration')
        self.assertEqual(report['task'], body['instructions'])
        self.assertEqual(report['actions_recorded'], 0)
        self.assertEqual(report['review_status'], 'not_completed')
        self.assertEqual(self.client.get('/api/reports/' + saved['report_id'] + '/evidence').json(), [])
        body['url'] = 'http://127.0.0.1:8000/'
        self.assertEqual(self.post('/api/plans', body).status_code, 400)
        body['max_actions'] = 1000
        self.assertEqual(self.post('/api/plans', body).status_code, 422)

    def test_live_quota_failure_preserves_steps_without_another_model_call(self):
        from Backend.app.live import run_live
        from Backend.agents.gemini_requests import GeminiRequestError
        from unittest.mock import MagicMock
        plan = dict(self.plan(), method='live', max_actions=3)
        browser_api = MagicMock()
        state = {'url':plan['url'], 'visible_text':'Help', 'controls':[], 'scroll':{'y':0}}
        action = {'action':'scroll', 'target':-1, 'value':'down', 'reason':'Find help'}
        with patch('Backend.app.live.sync_playwright', return_value=browser_api), \
             patch('Backend.app.live.observe', return_value=(state, {})), \
             patch('Backend.app.live.execute', return_value='executed'), \
             patch('Backend.app.live.explore_next', side_effect=[action, GeminiRequestError('Gemini quota reached.')]), \
             patch('Backend.app.live.review_run') as review:
            progress = MagicMock()
            run_live('quota_test', plan, progress)
        review.assert_not_called()
        report = db.read(db.directory('results')/'exploration_quota_test'/'report.json')
        self.assertEqual(report['actions_recorded'], 1)
        self.assertEqual(report['run_status'], 'failed')
        self.assertIn('quota', report['stop_reason'])
        self.assertEqual(len(db.report_evidence('exploration_quota_test')), 1)
        self.assertEqual(progress.call_args.kwargs['status'], 'failed')

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
        with patch.dict(os.environ,{'GEMINI_API_KEY':'unit-test-placeholder'}),patch('Backend.app.server.EXECUTOR.submit'):
            run=self.post('/api/runs',{'plan_id':plan['id']}).json()
            self.assertEqual(run['status'],'queued')
            self.assertEqual(self.post('/api/runs',{'plan_id':plan['id']}).status_code,409)
            with patch('Backend.app.server.evaluate_ux',return_value={'persona':'Older / Low-Tech User','task':'Create an account','findings':[finding]}):
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
        with patch.dict(os.environ,{'GEMINI_API_KEY':'unit-test-placeholder'}),patch('Backend.app.server.EXECUTOR.submit'):
            run=self.post('/api/runs',{'plan_id':plan['id']}).json()
            with patch('Backend.app.server.evaluate_ux',side_effect=Exception('SDK failure')):
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

    def test_persona_updates_preserve_behavior_fields_in_shared_store(self):
        source=db.safe_file('personas','first_time_user')
        original=db.read(source)
        person=self.client.get('/api/personas').json()
        person=next(p for p in person if p['id']=='first_time_user')
        body={'name':person['name'],'technical_skill':'basic','goal':'Find a product','criteria':['Feedback']}
        response=self.client.put('/api/personas/first_time_user',json=body,headers=HEADERS)
        self.assertEqual(response.status_code,200)
        self.assertEqual(db.read(source)['goal'],'Find a product')
        self.assertEqual(db.read(source)['behavior_preferences'],original['behavior_preferences'])
        self.assertFalse((db.ROOT/'Backend'/'personas').exists())

    def test_saved_exploration_reports_include_safe_recorded_history(self):
        run=db.ROOT/'results'/'exploration_test_run'
        db.write(run/'report.json',{'persona':'First-Time User','actions_recorded':1,'review_status':'not_completed','findings':[]})
        db.write(run/'persona.json',{'name':'First-Time User','goal':'Explore the store'})
        db.write(run/'history.json',[{'step':1,'result':'executed','decision':{'action':'click','value':'private-input','reason':'Open products'},'before':{'url':'http://127.0.0.1:5173/','visible_text':'Discover','controls':[{'id':0,'name':'Discover','value':'private-input'}]},'after':{'url':'http://127.0.0.1:5173/products','visible_text':'Products','controls':[]},'observed_change':{'url':True}}])
        db.write(run/'browser_state.json',{'cookies':['private-cookie']})
        report=self.client.get('/api/reports/exploration_test_run').json()
        self.assertEqual(report['kind'],'exploration')
        self.assertEqual(report['url'],'http://127.0.0.1:5173/')
        self.assertEqual(report['review_status'],'not_completed')
        evidence=self.client.get('/api/reports/exploration_test_run/evidence')
        self.assertEqual(evidence.json()[0]['action'],'click')
        self.assertNotIn('private-input',evidence.text)
        self.assertNotIn('private-cookie',evidence.text)

if __name__=='__main__':
    unittest.main()
