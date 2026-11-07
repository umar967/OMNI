"""Geometry text, privacy, explicit rediscovery and offline evaluation contracts."""
from copy import deepcopy
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, MagicMock, patch
from playwright.sync_api import sync_playwright
from Backend.action_journal import ActionJournal
from Backend.explore_website import observe, release, execute, SELECTOR
from Backend.text_observations import observe_text
from Backend.persona_engine.session import PerceptionSession
from Backend.persona_engine.resolver import resolve_persona, agent_persona
from Backend.benchmarks.contract import BenchmarkSuite, TargetAnnotation
from Backend.benchmarks.geometry_retention import fixture_html, permitted_view_driver
from Backend.benchmarks.retention_metrics import exposure_sample, run_metrics
from Backend.task_outcomes import unverified
from Backend.tests.test_perception_v1 import fixture


def session(mode='provisional_pilot_v1', **settings):
    return PerceptionSession(resolve_persona({'profile':{'name':'Visitor','technical_experience':'beginner',
        'perception':settings}}), mode)


class GeometryChromeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = sync_playwright().start()
        cls.browser = cls.api.chromium.launch(channel='chrome', headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.api.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width':1366,'height':768})
        self.addCleanup(self.page.close)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def observation(self):
        state, handles = observe(self.page)
        self.addCleanup(release, handles)
        return state, handles

    def test_explicit_label_containment_aria_and_unassociated_text(self):
        self.page.set_content('''<label for="search">Search catalog</label><input id="search">
          <span id="description">Required keywords</span><button aria-describedby="description">Go</button>
          <span id="name">Browse catalog</span><button aria-labelledby="name">Open</button>
          <p>Independent instructions</p>''')
        raw, _ = self.observation()
        blocks = {b['text']:b for b in raw['text_observation']['blocks']}
        self.assertEqual(blocks['Search catalog']['association']['control_ids'], [0])
        self.assertIn('html_label', blocks['Search catalog']['association']['kinds'])
        self.assertEqual(blocks['Required keywords']['association']['control_ids'], [1])
        self.assertEqual(blocks['Browse catalog']['association']['control_ids'], [2])
        self.assertEqual(blocks['Independent instructions']['association']['status'], 'unassociated')
        same, _ = self.observation()
        self.assertEqual(raw['text_observation'], same['text_observation'])
        self.page.locator('p').evaluate("el => el.textContent='Changed instructions'")
        changed, _ = self.observation()
        a, b = blocks['Independent instructions'], changed['text_observation']['blocks'][-1]
        self.assertEqual(a['id'], b['id'])
        self.assertNotEqual(a['fingerprint'], b['fingerprint'])

    def test_visibility_viewport_ancestor_clipping_and_partial_text(self):
        self.page.set_content('''<p>Visible instructions</p><div style="opacity:0"><p>Transparent secret</p></div>
          <p aria-hidden="true">ARIA hidden</p><p style="display:none">Display hidden</p>
          <p style="position:absolute;left:-60px;top:180px;white-space:nowrap">Partially clipped text</p>
          <div style="position:absolute;top:250px;width:60px;overflow:hidden"><span style="white-space:nowrap">Ancestor clipped text</span></div>
          <p style="position:absolute;top:1500px">Below viewport</p>''')
        raw, _ = self.observation()
        blocks = {b['text']:b for b in raw['text_observation']['blocks']}
        for text in ('Transparent secret','ARIA hidden','Display hidden','Below viewport'):
            self.assertNotIn(text, blocks)
        for text in ('Partially clipped text','Ancestor clipped text'):
            self.assertLess(blocks[text]['viewport_intersection']['visible_fraction'], 1)
            self.assertIn('partially_clipped',blocks[text]['quality_flags'])
        projected = session().perceive(raw).model_observation
        self.assertEqual(projected['visible_text'], 'Visible instructions')
        self.assertTrue(projected['text_status']['partial'])

    def test_private_and_reflected_values_do_not_reach_either_model_mode(self):
        self.page.set_content('''<input value="PRIVATE_TOKEN"><textarea>PRIVATE_NOTE</textarea>
          <input type="password" value="PASSWORD_TOKEN"><p>Echo PRIVATE_TOKEN</p><p>Echo PASSWORD_TOKEN</p>
          <div contenteditable="true">EDITABLE_SECRET</div><p data-omni-private>MARKED_SECRET</p>
          <button>Echo PASSWORD_TOKEN</button><p>contact somebody@real.example</p><p>4111 1111 1111 1111</p><p>Try another product.</p>''')
        self.page.evaluate("document.title='PASSWORD_TOKEN'")
        raw, _ = self.observation()
        for mode in ('neutral_passthrough','provisional_pilot_v1'):
            p = session(mode)
            view = p.perceive(raw)
            data = json.dumps(view.model_observation)
            for secret in ('PRIVATE_TOKEN','PRIVATE_NOTE','PASSWORD_TOKEN','EDITABLE_SECRET','MARKED_SECRET','somebody@real.example','4111'):
                self.assertNotIn(secret,data)
            self.assertIn('Try another product.',data)
            history = p.history([{'step':1,'perception_policy':view.provenance,'model_before':view.model_observation,
                'model_after':view.model_observation,'before':raw,'after':raw,'result':'executed','decision':{'action':'fill','target':0,'value':'PRIVATE_TOKEN'}}])
            self.assertNotIn('PRIVATE_TOKEN',json.dumps(history))
            unavailable = deepcopy(raw)
            unavailable['text_observation']={'version':'geometry-text-1','status':'unavailable','blocks':[]}
            failed_view=p.perceive(unavailable).model_observation
            self.assertTrue(all(not c['name'] for c in failed_view['controls']))
            self.assertNotIn('PASSWORD_TOKEN',json.dumps(failed_view))

    def test_filtered_label_shared_description_and_copy_cannot_leak(self):
        self.page.set_content(fixture_html('dense'))
        self.page.evaluate('''() => {
          const d=document.createElement('div'); d.innerHTML='<p>Open product listing</p><p>Open product <span>listing</span></p><p id="shared">Special catalog hint</p><p>Arc Lamp</p><p>Use available controls to browse.</p>';
          document.body.append(d);
          document.querySelector('#open-catalog').setAttribute('aria-describedby','shared');
          document.querySelectorAll('button')[1].setAttribute('aria-describedby','shared');
        }''')
        raw, _ = self.observation()
        p = session()
        view = p.perceive(raw)
        self.assertNotIn(0,view.allowed_targets)
        data = json.dumps(view.model_observation)
        self.assertNotIn('Open product',data)
        self.assertNotIn('Special catalog hint',data)
        self.assertIn('Arc Lamp',data)
        self.assertIn('Use available controls',data)

    def test_partial_or_unavailable_text_never_falls_back_to_raw_flat_text(self):
        self.page.set_content('<p>First instruction</p><p>Second instruction</p><p>Third instruction</p>')
        raw, handles = self.observation()
        raw['text_observation'] = observe_text(self.page, handles, SELECTOR, max_fragments=1)
        for mode in ('neutral_passthrough','provisional_pilot_v1'):
            view = session(mode).perceive(raw).model_observation
            self.assertEqual(view['visible_text'],'First instruction')
            self.assertEqual(view['text_status']['source_status'],'partial')
        with patch.object(self.page, 'evaluate', side_effect=RuntimeError('browser closed')):
            raw['text_observation'] = observe_text(self.page, handles, SELECTOR)
        self.assertEqual(session('neutral_passthrough').perceive(raw).model_observation['visible_text'], '')

    def test_text_budget_can_expand_by_explicit_scan_without_raw_history_leak(self):
        self.page.set_content('<p>First instruction</p><p>Second instruction</p><p>Third instruction</p>')
        raw, _ = self.observation()
        p=session(text_budget=1)
        first=p.perceive(raw)
        self.assertEqual(first.model_observation['visible_text'],'First instruction')
        self.assertTrue(p.policy.scan(first))
        second=p.perceive(raw)
        self.assertEqual(second.model_observation['visible_text'],'First instruction\nSecond instruction')
        self.assertEqual(first.model_observation['text_blocks'][0]['id'],second.model_observation['text_blocks'][0]['id'])
        history=p.history([{'step':1,'before':raw,'after':raw,'model_before':first.model_observation,
            'model_after':second.model_observation,'perception_policy':first.provenance,
            'result':'perception_scanned','decision':{'action':'scan','target':-1}}])
        self.assertNotIn('Third instruction',json.dumps(history))
        zero=session(text_budget=0)
        self.assertFalse(zero.perceive(raw).model_observation['perception']['scan_available'])
        self.assertEqual(zero.perceive(raw).model_observation['visible_text'],'')

    def test_offscreen_control_label_is_associated_but_not_exposed(self):
        self.page.set_content('<label for="below">UNAVAILABLE_CONTROL</label><input id="below" style="position:absolute;top:1600px"><p>Visible instruction</p>')
        raw, _ = self.observation()
        label = raw['text_observation']['blocks'][0]
        self.assertFalse(label['association']['complete'])
        self.assertNotIn('UNAVAILABLE_CONTROL',session().perceive(raw).model_observation['visible_text'])

    def test_scanning_reveals_original_ids_and_stale_handle_is_still_rejected(self):
        self.page.set_content(fixture_html('dense'))
        raw, handles = self.observation()
        p, journal = session(), ActionJournal(Path(self.temp.name)/'history.json', [])
        first = p.perceive(raw)
        self.assertNotIn(0, first.allowed_targets)
        for number in (1,2):
            view = p.perceive(raw)
            row = journal.begin(number,raw,{'action':'scan','target':-1},0)
            p.record_before(journal,row,view)
            executor = Mock()
            self.assertEqual(p.execute(journal,row,view,executor,self.page,handles,self.page.url),'perception_scanned')
            executor.assert_not_called()
        final = p.perceive(raw)
        self.assertIn(0,final.allowed_targets)
        self.assertEqual([c['id'] for c in final.model_observation['controls']],list(handles))
        self.page.locator('#open-catalog').evaluate("el => el.outerHTML='<button id=\"open-catalog\">Pay now</button>'")
        row = journal.begin(3,raw,{'action':'click','target':0},0)
        p.record_before(journal,row,final)
        result = p.execute(journal,row,final,execute,self.page,handles,self.page.url)
        self.assertTrue(result.startswith('refresh_required:'))
        self.assertEqual(row['dispatch_state'],'not_dispatched')

    def test_scrolling_makes_a_previously_offscreen_target_discoverable(self):
        self.page.set_content(fixture_html('below_fold'))
        raw, _ = self.observation()
        self.assertFalse(raw['controls'])
        self.page.evaluate('scrollTo(0,900)')
        raw, _ = self.observation()
        view = session().perceive(raw)
        self.assertEqual(view.allowed_targets,frozenset(c['id'] for c in raw['controls']))
        self.assertIn('Open product listing',view.model_observation['visible_text'])

    def test_metrics_measure_known_retention_and_flag_invalid_annotations(self):
        self.page.set_content(fixture_html('dense'))
        raw, handles = self.observation()
        p = session()
        annotations = [TargetAnnotation(target_id='entry',selector='#open-catalog')]
        initial = exposure_sample(raw,p.perceive(raw),annotations,handles,page=self.page)
        self.assertEqual(initial['task_target_retention']['value'],0)
        self.assertEqual(initial['permitted_control_coverage']['value'],16/40)
        self.assertEqual(initial['exposure_precision']['value'],0)
        for _ in range(2):
            self.assertTrue(p.policy.scan(p.perceive(raw)))
        scanned = exposure_sample(raw,p.perceive(raw),annotations,handles,'scan',self.page)
        self.assertEqual(scanned['exposure_precision']['value'],1/40)
        metrics = run_metrics([initial,scanned],[],unverified('No endpoint'),Path(self.temp.name))
        self.assertEqual(metrics['critical_retained_after_scan'],['entry'])
        self.assertEqual(metrics['cumulative_critical_retention']['value'],1)
        self.assertIsNone(metrics['evidence_complete_actions']['value'])
        bad = exposure_sample(raw,p.perceive(raw),[TargetAnnotation(target_id='bad',selector='button')],handles,page=self.page)
        self.assertFalse(run_metrics([bad],[],unverified('No endpoint'),Path(self.temp.name))['annotations_valid'])
        self.assertIsNone(bad['exposure_precision'])

    def test_disabled_target_is_exposed_but_not_actionable(self):
        self.page.set_content(fixture_html('disabled'))
        raw, handles = self.observation()
        sample = exposure_sample(raw,session().perceive(raw),
            [TargetAnnotation(target_id='entry',selector='#open-catalog')],handles,page=self.page)
        self.assertEqual(sample['task_target_retention']['value'],1)
        self.assertEqual(sample['actionable_target_retention']['value'],0)
        self.assertEqual(sample['exposure_precision']['value'],1)
        self.assertIsNone(sample['permitted_control_coverage']['value'])

    def test_filtered_text_claim_ids_match_full_evidence_without_line_index_drift(self):
        from Backend.finding_validation import observations
        self.page.set_content(fixture_html('dense'))
        raw, _ = self.observation()
        p = session()
        before = p.perceive(raw)
        self.page.locator('#feedback').evaluate("el => el.textContent='Try another product.'")
        after, _ = self.observation()
        row={'step':1,'journal_version':1,'before':raw,'after':after,'result':'executed',
             'action_status':'executed','decision':{'action':'hover','target':1},
             'perception_policy':before.provenance,'model_before':before.model_observation,
             'model_after':p.perceive(after).model_observation}
        full={f['id']:f for f in observations([row])[0]}
        projected=[f for f in observations(p.history([row]))[0] if f['kind']=='text_appeared']
        self.assertTrue(projected)
        for fact in projected:
            self.assertEqual(full[fact['id']]['statement'],fact['statement'])
        row['after']['text_observation']['blocks'][-1]['text']='Unrecorded replacement'
        self.assertFalse(any('Unrecorded replacement' in f['statement'] for f in observations([row])[0]))


class ScanningContractTests(unittest.TestCase):
    def test_transient_file_lock_retries_only_atomic_replace_and_permanent_failure_aborts(self):
        from Backend import action_journal as journal_module
        import os
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'history.json'
            journal_module.atomic_json(path,{'old':True})
            real_replace=os.replace
            locked=PermissionError('Sharing lock')
            locked.winerror=32
            attempts=[]
            def replace(source,destination):
                attempts.append(source)
                if len(attempts)==1:
                    raise locked
                real_replace(source,destination)
            with patch.object(journal_module.os,'name','nt'), patch.object(journal_module.os,'replace',side_effect=replace), \
                 patch.object(journal_module.time,'sleep'):
                journal_module.atomic_json(path,{'new':True})
            self.assertEqual(len(attempts),2)
            self.assertEqual(json.loads(path.read_text()),{'new':True})
            with patch.object(journal_module.os,'name','nt'), patch.object(journal_module.os,'replace',side_effect=locked) as failing, \
                 patch.object(journal_module.time,'sleep'), self.assertRaises(PermissionError):
                journal_module.atomic_json(path,{'must_not_replace':True})
            self.assertEqual(failing.call_count,4)
            self.assertEqual(json.loads(path.read_text()),{'new':True})

    def test_profile_defaults_limits_and_builtin_custom_parity(self):
        for path in (Path(__file__).parents[1]/'personas').glob('*.json'):
            built = resolve_persona(json.loads(path.read_text()))
            custom = built.persona.model_dump()
            custom['provenance']['origin']='custom'
            a, b = PerceptionSession(built,'provisional_pilot_v1'), PerceptionSession(resolve_persona(custom),'provisional_pilot_v1')
            for _ in range(3):
                x,y = a.perceive(fixture()),b.perceive(fixture())
                self.assertEqual(x,y)
                self.assertEqual(a.policy.scan(x),b.policy.scan(y))
        for settings in ({'max_scan_passes':-1},{'max_scan_passes':True},{'scanning':'guess'},{'text_budget':257}):
            with self.assertRaises(ValueError):
                session(**settings)

    def test_scan_is_explicit_bounded_and_can_be_disabled(self):
        for p in (session(scanning='disabled'), session(max_scan_passes=0),session('neutral_passthrough')):
            self.assertFalse(p.policy.scan(p.perceive(fixture())))
        p = session(max_scan_passes=1)
        view = p.perceive(fixture())
        self.assertEqual(view,p.perceive(fixture()))
        self.assertTrue(p.policy.scan(view))
        self.assertFalse(p.policy.scan(view))
        self.assertEqual(len(p.perceive(fixture()).allowed_targets),32)
        self.assertFalse(p.policy.scan(p.perceive(fixture())))

    def test_missing_captures_partial_actions_and_rejections_remain_explicit(self):
        raw=fixture(1)
        rows=[{'step':i,'journal_version':1,'before':raw,'after':deepcopy(raw),'decision':{'action':'hover','target':0},
               'result':'executed','action_status':'executed'} for i in (1,2)]
        rows.append({'step':3,'before':raw,'after':{},'decision':{'action':'click','target':0},
                     'result':'executed','action_status':'executed'})
        rows.append({'step':4,'perception_rejection':'invalid target','action_status':'blocked'})
        metrics=run_metrics([],rows,unverified('No inspectable endpoint'),None)
        self.assertEqual(metrics['repeated_ineffective_interactions'],1)
        self.assertEqual(metrics['invalid_action_rejections'],1)
        self.assertEqual(metrics['uninspectable_execution_pairs'],1)
        self.assertEqual(metrics['evidence_complete_actions']['value'],0)
        self.assertEqual(metrics['task_outcome'],'unknown')

    def test_manifest_rejects_family_split_leakage_and_duplicate_tasks(self):
        path=Path(__file__).parents[1]/'benchmarks/fixtures/retention_v1.json'
        data=json.loads(path.read_text())
        BenchmarkSuite.model_validate(data)
        data['cases'][1]['split']='test'
        with self.assertRaises(ValueError):
            BenchmarkSuite.model_validate(data)
        data=json.loads(path.read_text())
        data['cases'].append(deepcopy(data['cases'][0]))
        with self.assertRaises(ValueError):
            BenchmarkSuite.model_validate(data)

    def test_driver_receives_no_evaluator_annotations(self):
        p=session()
        choose=Mock(return_value={'action':'stop','target':-1})
        p.decide(choose,{'task':'Open product listing'},p.perceive(fixture()),[])
        sent=json.dumps(choose.call_args.args)
        for field in ('selector','target_id','split','expected_url','endpoint'):
            self.assertNotIn('"'+field+'"',sent)

    def test_both_runners_share_journaled_scan_without_browser_dispatch(self):
        from Backend import explore_website as cli
        from Backend.app import live, storage as db
        for runner in ('live','cli'):
            with self.subTest(runner=runner), tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                root=Path(folder)
                module=live if runner=='live' else cli
                stack.enter_context(patch.object(db,'ROOT',root))
                stack.enter_context(patch.object(cli,'ROOT',root))
                stack.enter_context(patch.dict('os.environ',{'OMNI_PERSONA_POLICY':'provisional_pilot_v1'}))
                config={'profile':{'name':'Scanner','technical_experience':'beginner'}}
                db.write(root/'personas/first_time_user.json',config)
                db.write(root/'flow_catalog.json',{'flows':[]})
                stack.enter_context(patch.object(module,'sync_playwright',MagicMock()))
                stack.enter_context(patch.object(module,'observe',return_value=(fixture(),{})))
                stack.enter_context(patch.object(module,'capture_step',side_effect=RuntimeError('missing')))
                executor=stack.enter_context(patch.object(module,'execute'))
                prefix='Backend.app.live' if runner=='live' else 'Backend.agents.exploration_agent'
                choose=stack.enter_context(patch(prefix+'.explore_next',side_effect=[{'action':'scan','target':-1},{'action':'stop','target':-1}]))
                stack.enter_context(patch(prefix+'.review_run',return_value={'findings':[],'persona_feedback':{}}))
                if runner=='live':
                    live.run_live('scan',{'persona':config,'instructions':'Find a product','cases':[],
                        'url':'http://example.invalid/test','project_id':None,'persona_id':'custom','max_actions':2},Mock())
                else:
                    stack.enter_context(patch('sys.argv',['explore','--url','http://example.invalid/test','--max-actions','2',
                        '--flows',str(root/'flow_catalog.json')]))
                    cli.main()
                self.assertEqual(len(choose.call_args_list[0].args[1]['controls']),16)
                self.assertEqual(len(choose.call_args_list[1].args[1]['controls']),32)
                executor.assert_not_called()
                directory=next((root/'results').glob('exploration_*'))
                rows=db.read(directory/'history.json')
                self.assertEqual(rows[0]['result'],'perception_scanned')
                self.assertEqual(rows[0]['dispatch_state'],'not_dispatched')
                self.assertEqual(db.read(directory/'report.json')['task_outcome'],'unknown')
