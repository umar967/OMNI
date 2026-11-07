"""Stage A boundaries, both runners and real Chrome; no paid model calls."""
from contextlib import ExitStack
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, MagicMock, patch

from playwright.sync_api import sync_playwright
from Backend.tests.test_perception_v1 import fixture
from Backend.persona_engine.perception_v1 import PilotPerception, validate_action, project_history
from Backend.persona_engine.resolver import resolve_persona, agent_persona
from Backend.persona_engine.session import PerceptionSession, policy_report
from Backend.action_journal import ActionJournal
from Backend.explore_website import observe, execute, release
from Backend.app import storage as db


def runtime():
    return resolve_persona({'schema_version':'1.0', 'profile':{'name':'Visitor','technical_experience':'beginner'}}, 'Find a product')


class PerceptionBoundaryTests(unittest.TestCase):
    def test_cache_handles_reindexed_ids_and_changed_ranking_inputs(self):
        obs = fixture()
        p = PilotPerception(runtime().persona.profile.model_dump())
        p.perceive(obs)
        for c in obs['controls']:
            c['id'] += 100
        self.assertTrue(all(i >= 100 for i in p.perceive(obs).allowed_targets))
        self.assertEqual(len(p._view_cache), 2)
        obs['controls'][0]['style']['font_size'] = '32px'
        p.perceive(obs)
        obs['viewport']['height'] = 900
        p.perceive(obs)
        self.assertEqual(len(p._view_cache), 4)

    def test_resolved_presets_and_custom_profiles_share_identical_policy(self):
        for path in (Path(__file__).parents[1]/'personas').glob('*.json'):
            built = resolve_persona(json.loads(path.read_text()))
            custom = built.persona.model_dump()
            custom['provenance']['origin'] = 'custom'
            a = PerceptionSession(built, 'provisional_pilot_v1')
            b = PerceptionSession(resolve_persona(custom), 'provisional_pilot_v1')
            self.assertEqual(a.perceive(fixture()), b.perceive(fixture()))
            self.assertEqual(agent_persona(built), agent_persona(resolve_persona(custom)))

    def test_invalid_mode_and_unsupported_capabilities_fail_closed(self):
        with self.assertRaises(ValueError):
            PerceptionSession(runtime(), 'guess')
        r = resolve_persona({'profile':{'name':'Visitor','accessibility':{'screen_reader_required':True}}})
        with self.assertRaises(ValueError):
            PerceptionSession(r, 'provisional_pilot_v1')

    def test_guard_rejects_float_bool_missing_duplicate_and_disabled_targets(self):
        obs = fixture(2)
        obs['controls'][0]['disabled'] = True
        step = PerceptionSession(runtime(), 'neutral_passthrough').perceive(obs)
        for decision in [{'action':'click','target':0}, {'action':'click','target':True},
                         {'action':'click','target':1.0}, {'action':'stop'}, {'action':'stop','target':-1.0},
                         {'action':'press','target':0,'value':'Escape'}, {'action':[], 'target':1}]:
            self.assertIsNotNone(validate_action(decision, step))
        obs['controls'][1]['id'] = 0
        with self.assertRaises(ValueError):
            PilotPerception(runtime().persona.profile.model_dump()).perceive(obs)

    def test_no_alias_or_nested_metadata_value_leak(self):
        obs = fixture(1)
        c = obs['controls'][0]
        c.update(tag='input', value='PRIVATE_VALUE')
        c['label_metadata']['raw_internal'] = 'PRIVATE_NESTED'
        p = PerceptionSession(runtime(), 'provisional_pilot_v1')
        step = p.perceive(obs)
        self.assertNotIn('PRIVATE', json.dumps(step.model_observation))
        self.assertTrue(step.model_observation['controls'][0]['filled'])
        step.model_observation['controls'][0]['label_metadata']['dom_id'] = 'mutated'
        self.assertNotEqual(c['label_metadata']['dom_id'], 'mutated')

    def test_history_does_not_leak_raw_after_errors_decisions_or_changed_flags(self):
        session = PerceptionSession(runtime(), 'provisional_pilot_v1')
        step = session.perceive(fixture())
        row = {'step':1, 'before':fixture(), 'after':fixture(), 'model_before':step.model_observation,
               'model_after':deepcopy(step.model_observation), 'perception_policy':step.provenance,
               'decision':{'action':'click','target':0,'value':'SECRET','reason':'SECRET','extra':'SECRET'},
               'result':'automation_error: SECRET', 'automation_error':'SECRET', 'observed_change':{'SECRET':True}}
        safe = session.history([row])[0]
        self.assertNotIn('SECRET', json.dumps(safe))
        self.assertFalse(any(safe['observed_change'].values()))

    def test_history_from_other_mode_or_profile_is_not_reused(self):
        neutral = PerceptionSession(runtime(), 'neutral_passthrough')
        observed = neutral.perceive(fixture())
        row = {'step':1,'model_before':observed.model_observation,'model_after':observed.model_observation,
               'perception_policy':observed.provenance, 'result':'executed','decision':{'action':'click','target':0}}
        restricted = PerceptionSession(runtime(), 'provisional_pilot_v1')
        self.assertEqual(restricted.history([row])[0]['before']['controls'], [])
        self.assertNotIn('SECRET', json.dumps(restricted.history([row])))
        self.assertTrue(restricted.report([row])['mixed_policy_history'])
        self.assertEqual(project_history([{'step':1,'before':fixture(), 'after':fixture()}])[0]['result'], 'unverified_history')

    def test_missing_projected_after_cannot_create_review_observations(self):
        from Backend.finding_validation import observations
        session = PerceptionSession(runtime(), 'provisional_pilot_v1')
        perceived = session.perceive(fixture())
        row = {'step':1, 'journal_version':1, 'model_before':perceived.model_observation,
               'perception_policy':perceived.provenance, 'result':'executed',
               'action_status':'executed', 'decision':{'action':'click','target':0},
               'after':fixture()}
        safe = session.history([row])
        self.assertEqual(safe[0]['after'], {})
        self.assertEqual(safe[0]['journal_version'], 1)
        self.assertEqual(observations(safe)[0], [])

    def test_both_provider_decision_prompts_receive_only_projected_data(self):
        from Backend.agents.exploration_agent import explore_next
        for provider in ('gemini','ollama'):
            session = PerceptionSession(runtime(), 'provisional_pilot_v1')
            step = session.perceive(fixture())
            with patch.dict('os.environ', {'OMNI_MODEL_PROVIDER':provider}), \
                 patch('Backend.agents.exploration_agent.request_json', return_value={'action':'stop','target':-1}) as request:
                session.decide(explore_next, agent_persona(runtime()), step, [{'step':1,'before':fixture(),'after':fixture()}])
            prompt = request.call_args.args[0]
            self.assertNotIn('SECRET', prompt)
            self.assertNotIn('never-send', prompt)
            self.assertNotIn('target_snapshot', prompt)

    def test_ollama_has_no_second_candidate_cap(self):
        from Backend.agents.local_persona import next_action
        p = PerceptionSession(runtime(), 'neutral_passthrough').perceive(fixture())
        request = Mock(return_value={'action':'stop','target':-1})
        next_action(agent_persona(runtime()), p.model_observation, [], request)
        self.assertEqual(len(request.call_args.args[1]['properties']['target']['enum']), 46)

    def test_journal_stores_projection_before_dispatch_and_rejection_is_durable(self):
        session = PerceptionSession(runtime(), 'provisional_pilot_v1')
        raw = fixture()
        perceived = session.perceive(raw)
        with tempfile.TemporaryDirectory() as folder:
            journal = ActionJournal(Path(folder)/'history.json', [])
            disallowed = next(c['id'] for c in raw['controls'] if c['id'] not in perceived.allowed_targets)
            row = journal.begin(1, raw, {'action':'click','target':disallowed}, 0)
            session.record_before(journal, row, perceived)
            executor = Mock()
            session.execute(journal, row, perceived, executor, None, {}, raw['url'])
            executor.assert_not_called()
            saved = json.loads(journal.path.read_text())[0]
            self.assertEqual(saved['action_status'], 'blocked')
            self.assertEqual(saved['dispatch_state'], 'not_dispatched')
            self.assertIn('SECRET', saved['before']['visible_text'])
            self.assertNotIn('SECRET', json.dumps(saved['model_before']))
            self.assertFalse(session.report(journal.history)['human_calibrated'])


class RunnerPerceptionTests(unittest.TestCase):
    def test_both_runners_modes_preserve_boundary_and_reobserve_rejected_decisions(self):
        from Backend import explore_website as cli
        from Backend.app import live
        for runner in ('live','cli'):
            for mode in ('neutral_passthrough','provisional_pilot_v1'):
                with self.subTest(runner=runner, mode=mode), tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                    root = Path(folder)
                    module = live if runner == 'live' else cli
                    stack.enter_context(patch.object(db, 'ROOT', root))
                    stack.enter_context(patch.object(cli, 'ROOT', root))
                    stack.enter_context(patch.dict('os.environ', {'OMNI_PERSONA_POLICY':mode}))
                    db.write(root/'personas/first_time_user.json', {'name':'Default'})
                    config = runtime().persona.model_dump()
                    db.write(root/'custom.json', config)
                    db.write(root/'flows.json', {'flows':[]})
                    raw = fixture()
                    stack.enter_context(patch.object(module, 'sync_playwright', MagicMock()))
                    observer = stack.enter_context(patch.object(module, 'observe', return_value=(raw, {})))
                    stack.enter_context(patch.object(module, 'capture_step', side_effect=RuntimeError('capture unavailable')))
                    executor = stack.enter_context(patch.object(module, 'execute'))
                    prefix = 'Backend.app.live' if runner == 'live' else 'Backend.agents.exploration_agent'
                    choose = stack.enter_context(patch(prefix + '.explore_next', side_effect=[
                        {'action':'click','target':999,'reason':'Guess'}, {'action':'stop','target':-1,'reason':'Stop'}]))
                    reviewer = stack.enter_context(patch(prefix + '.review_run', return_value={'findings':[], 'persona_feedback':{}}))
                    if runner == 'live':
                        live.run_live('policy', {'persona':config,'instructions':'Find a product','cases':[],
                            'url':raw['url'],'project_id':None,'persona_id':'custom','max_actions':2}, Mock())
                    else:
                        stack.enter_context(patch('sys.argv', ['explore','--url',raw['url'],'--max-actions','2',
                            '--persona',str(root/'custom.json'),'--flows',str(root/'flows.json')]))
                        cli.main()
                    directory = next((root/'results').glob('exploration_*'))
                    rows = db.read(directory/'history.json')
                    report = db.read(directory/'report.json')
                    self.assertEqual(report['perception_policy']['mode'], mode)
                    self.assertEqual(report['perception_policy']['policy_rejections'], 1)
                    self.assertEqual(report['execution_status'], 'finished')
                    self.assertEqual(report['task_outcome'], 'unknown')
                    self.assertFalse(report['perception_policy']['human_calibrated'])
                    self.assertEqual(choose.call_count, 2)
                    self.assertEqual(observer.call_count, 4)
                    executor.assert_not_called()
                    self.assertEqual(rows[0]['action_status'], 'blocked')
                    self.assertEqual(len(rows[0]['model_before']['controls']), 16 if mode=='provisional_pilot_v1' else 45)
                    self.assertNotIn('target_snapshot', json.dumps(choose.call_args_list[0].args))
                    if mode == 'provisional_pilot_v1':
                        self.assertNotIn('SECRET', json.dumps(choose.call_args_list[1].args))
                        self.assertNotIn('SECRET', json.dumps(reviewer.call_args.args))
                    self.assertIsNone(reviewer.call_args.args[2])

    def test_historical_reports_do_not_claim_an_active_policy(self):
        self.assertEqual(policy_report(None, [])['mode'], 'legacy_unrecorded')
        self.assertEqual(policy_report(policy_report(None, []), [])['mode'], 'legacy_unrecorded')


class PerceptionChromeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = sync_playwright().start()
        cls.browser = cls.api.chromium.launch(channel=os.getenv('OMNI_TEST_BROWSER_CHANNEL', 'chrome') or None, headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.api.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width':1366,'height':768})
        self.addCleanup(self.page.close)
        self.page.set_content('<button onclick="window.hits++">Add to cart</button>')
        self.page.evaluate('window.hits=0')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.journal = ActionJournal(Path(self.temp.name)/'history.json', [])
        self.session = PerceptionSession(runtime(), 'provisional_pilot_v1')

    def action(self):
        before, handles = observe(self.page)
        self.addCleanup(release, handles)
        perceived = self.session.perceive(before)
        row = self.journal.begin(len(self.journal.history)+1, before, {'action':'click','target':0}, 0)
        self.session.record_before(self.journal, row, perceived)
        return row, perceived, handles

    def test_stage_a_does_not_bypass_stale_target_safety(self):
        row, perceived, handles = self.action()
        self.page.locator('button').evaluate("el => el.textContent='Pay'")
        result = self.session.execute(self.journal, row, perceived, execute, self.page, handles, self.page.url)
        self.assertTrue(result.startswith('refresh_required:'))
        self.assertEqual(self.page.evaluate('window.hits'), 0)

    def test_stage_a_does_not_bypass_duplicate_prevention(self):
        row, perceived, handles = self.action()
        self.assertEqual(self.session.execute(self.journal, row, perceived, execute, self.page, handles, self.page.url), 'executed')
        row, perceived, handles = self.action()
        self.assertTrue(self.session.execute(self.journal, row, perceived, execute, self.page, handles, self.page.url).startswith('blocked:'))
        self.assertEqual(self.page.evaluate('window.hits'), 1)

    def test_real_geometry_preserves_ids_and_limits_candidates(self):
        self.page.set_content(''.join(f'<button style="position:absolute;left:{20+i%8*130}px;top:{20+i//8*70}px;width:110px;height:32px">Option {i}</button>' for i in range(40)))
        raw, handles = observe(self.page)
        self.addCleanup(release, handles)
        step = self.session.perceive(raw)
        self.assertEqual(len(step.model_observation['controls']), 16)
        denied = next(c['id'] for c in raw['controls'] if c['id'] not in step.allowed_targets)
        row = self.journal.begin(1, raw, {'action':'click','target':denied}, 0)
        self.session.record_before(self.journal, row, step)
        self.session.execute(self.journal, row, step, execute, self.page, handles, self.page.url)
        self.assertEqual(row['dispatch_state'], 'not_dispatched')
