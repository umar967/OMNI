"""Adversarial local browser and runner checks. No providers or external sites."""
from contextlib import ExitStack
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

from playwright.sync_api import sync_playwright
from Backend.action_journal import ActionJournal, atomic_json, evidence_gaps
from Backend.action_safety import install_navigation_guard
from Backend.explore_website import observe, execute, release
from Backend.agents.gemini_requests import ModelRequestError
from Backend.agents.exploration_agent import clean_review, compact_history
from Backend.app import storage as db


class TargetRevalidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = sync_playwright().start()
        cls.browser = cls.api.chromium.launch(
            channel=os.environ.get('OMNI_TEST_BROWSER_CHANNEL', 'chrome') or None, headless=True, timeout=15000)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.api.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)
        self.page.route('https://shop.test/**', lambda route: route.fulfill(body='<body>Fixture</body>', content_type='text/html'))
        self.page.goto('https://shop.test/')

    def target(self, html='<button id="target" onclick="window.hits++">Add to cart</button>'):
        self.page.set_content(html)
        self.page.evaluate('window.hits = 0')
        state, handles = observe(self.page)
        self.addCleanup(release, handles)
        return state, handles

    def act(self, state, handles, **decision):
        return execute(self.page, {'action': 'click', 'target': 0, **decision}, state, handles, 'https://shop.test/')

    def test_same_node_changed_label_role_or_type_is_rejected(self):
        for mutation in ["el.textContent='Pay'", "el.setAttribute('role','link')", "el.type='submit'", "el.setAttribute('aria-label','Delete')", "el.dataset.productId='other-product'"]:
            with self.subTest(mutation=mutation):
                state, handles = self.target('<button id="target" type="button" onclick="window.hits++">Details</button>')
                self.page.locator('#target').evaluate('el => {' + mutation + '}')
                self.assertTrue(self.act(state, handles).startswith('refresh_required:'))
                self.assertEqual(self.page.evaluate('window.hits'), 0)

    def test_replacement_and_reused_numeric_id_never_retarget(self):
        state, handles = self.target()
        self.page.locator('#target').evaluate('el => el.outerHTML = el.outerHTML')
        fresh, new_handles = observe(self.page)
        self.addCleanup(release, new_handles)
        self.assertEqual(state['controls'][0]['id'], fresh['controls'][0]['id'])
        self.assertTrue(self.act(state, handles).startswith('refresh_required:'))
        self.assertTrue(self.act(state, new_handles).startswith('refresh_required:'))
        self.assertEqual(self.page.evaluate('window.hits'), 0)

    def test_newly_disabled_hidden_and_inert_controls(self):
        for mutation in ["el.disabled=true", "el.hidden=true", "el.style.opacity='0'", "el.setAttribute('aria-disabled','true')", "el.inert=true"]:
            with self.subTest(mutation=mutation):
                state, handles = self.target()
                self.page.locator('#target').evaluate('el => {' + mutation + '}')
                self.assertTrue(self.act(state, handles).startswith('refresh_required:'))
                self.assertEqual(self.page.evaluate('window.hits'), 0)

    def test_changed_link_destination(self):
        state, handles = self.target('<a id="target" href="/products">Products</a>')
        self.page.locator('#target').evaluate("el => el.href='/checkout'")
        self.assertTrue(self.act(state, handles).startswith('refresh_required:'))
        self.assertEqual(self.page.url, 'https://shop.test/')

    def test_changed_form_semantics(self):
        for mutation in ["el.form.action='/payment'", "el.form.method='post'", "el.setAttribute('formaction','https://external.test/')",
                         "el.form.insertAdjacentHTML('beforeend','<input type=password>')", "el.form.querySelector('input').value='other-product'"]:
            with self.subTest(mutation=mutation):
                state, handles = self.target('<form action="/cart"><input type="hidden" name="product" value="private-hidden-token"><button id="target">Add to cart</button></form>')
                self.assertNotIn('private-hidden-token', json.dumps(state))
                self.page.locator('#target').evaluate('el => {' + mutation + '}')
                self.assertTrue(self.act(state, handles).startswith('refresh_required:'))

    def test_input_button_value_is_its_label_and_cannot_change_before_click(self):
        state, handles = self.target('<input id="target" type="button" value="Details" onclick="window.hits++">')
        self.assertEqual(state['controls'][0]['name'], 'Details')
        self.page.locator('#target').evaluate("el => el.value='Delete'")
        self.assertTrue(self.act(state, handles).startswith('refresh_required:'))
        self.assertEqual(self.page.evaluate('window.hits'), 0)

    def test_benign_labels_do_not_override_restricted_destinations_or_forms(self):
        for html in ['<a href="/checkout">Continue</a>', '<a href="javascript:void(0)">Details</a>',
                     '<a href="/delete?redirect=login">Log in</a>', '<a href="/account">Log in and delete</a>',
                     '<a href="https://external.test/">Products</a>', '<a download href="/file">Export</a>',
                     '<form action="/payment"><button>Add to cart</button></form>',
                     '<form action="/cart"><button>Add to cart</button><input type=password></form>',
                     '<form action="/cart"><button>Continue</button></form>']:
            with self.subTest(html=html):
                state, handles = self.target(html)
                self.assertTrue(self.act(state, handles).startswith('blocked:'))

    def test_unchanged_cart_action_executes_once(self):
        state, handles = self.target('<form action="/cart" onsubmit="event.preventDefault();window.hits++"><button>Add to cart</button></form>')
        self.assertEqual(self.act(state, handles), 'executed')
        self.assertEqual(self.page.evaluate('window.hits'), 1)

    def test_meaning_changes_during_pointerdown_before_click(self):
        state, handles = self.target('<button onpointerdown="this.textContent=\'Pay\'" onclick="window.hits++">Details</button>')
        with self.assertRaises(RuntimeError):
            self.act(state, handles)
        self.assertEqual(self.page.evaluate('window.hits'), 0)

    def test_form_action_changes_in_click_handler_before_submission(self):
        state, handles = self.target('<form action="/cart" onsubmit="window.hits++"><button onclick="this.form.action=\'/payment\'">Add to cart</button></form>')
        with self.assertRaises(RuntimeError):
            self.act(state, handles)
        self.assertEqual(self.page.url, 'https://shop.test/')
        self.assertEqual(self.page.evaluate('window.hits'), 0)

    def test_restricted_anchor_ancestor_and_implicit_submitter(self):
        state, handles = self.target('<a href="/checkout"><span role="button">Continue</span></a>')
        self.assertTrue(self.act(state, handles, target=1).startswith('blocked:'))
        state, handles = self.target('<form action="/search"><input aria-label="Search" type="search"><button formaction="/payment">Continue</button></form>')
        self.assertTrue(self.act(state, handles, action='press', value='Enter').startswith('blocked:'))

    def test_closed_browser_after_click_preserves_acknowledged_action(self):
        state, handles = self.target()
        with tempfile.TemporaryDirectory() as folder:
            journal = ActionJournal(Path(folder)/'history.json', [])
            row = journal.begin(1, state, {'action':'click', 'target':0}, 0)
            self.assertEqual(journal.execute(row, execute, self.page, handles, 'https://shop.test/'), 'executed')
            self.page.close()
            with self.assertRaises(Exception):
                journal.observe_after(row, self.page, observe, release)
            saved = json.loads(journal.path.read_text())[0]
            self.assertEqual(saved['action_status'], 'executed')
            self.assertEqual(saved['after'], {})
            self.assertIn('after_observation', saved['evidence_errors'])

    def test_duplicate_addition_is_blocked_after_fresh_observation(self):
        state, handles = self.target()
        with tempfile.TemporaryDirectory() as folder:
            journal = ActionJournal(Path(folder)/'history.json', [])
            row = journal.begin(1, state, {'action':'click', 'target':0}, 0)
            journal.execute(row, execute, self.page, handles, 'https://shop.test/')
            # Replacement reuses both the DOM id and next snapshot's numeric id.
            self.page.locator('#target').evaluate('el => el.outerHTML=el.outerHTML')
            fresh, fresh_handles = observe(self.page)
            self.addCleanup(release, fresh_handles)
            next_row = journal.begin(2, fresh, {'action':'click', 'target':0}, 1)
            self.assertTrue(journal.execute(next_row, execute, self.page, fresh_handles, 'https://shop.test/').startswith('blocked:'))
            self.assertEqual(self.page.evaluate('window.hits'), 1)


class JournalTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name)/'history.json'
        self.history = []
        self.journal = ActionJournal(self.path, self.history)
        self.state = {'url':'https://shop.test/', 'visible_text':'Details', 'controls':[{'id':0,'name':'Details','tag':'button'}]}

    def begin(self, step=1):
        return self.journal.begin(step, self.state, {'action':'click','target':0}, 0)

    def saved(self):
        return json.loads(self.path.read_text())

    def test_decision_dispatch_and_result_are_saved_before_evidence(self):
        row = self.begin()
        self.assertEqual(self.saved()[0]['action_status'], 'attempted')
        def executor(*args, on_dispatch):
            self.assertEqual(self.saved()[0]['intended_target']['name'], 'Details')
            on_dispatch()
            self.assertEqual(self.saved()[0]['action_status'], 'outcome_unknown')
            return 'executed'
        self.journal.execute(row, executor, None, {}, 'https://shop.test/')
        self.assertEqual(self.saved()[0]['action_status'], 'executed')
        self.assertEqual(self.saved()[0]['after'], {})

    def test_uncertain_dispatch_survives_reload_and_blocks_any_retry(self):
        row = self.begin()
        def executor(*args, on_dispatch):
            on_dispatch()
            raise RuntimeError('Browser closed immediately after click')
        self.journal.execute(row, executor, None, {}, 'https://shop.test/')
        self.assertEqual(self.saved()[0]['action_status'], 'outcome_unknown')
        restored = ActionJournal(self.path, self.saved())
        retry = restored.begin(2, self.state, {'action':'click','target':0}, 1)
        mock = Mock()
        self.assertTrue(restored.execute(retry, mock, None, {}, 'https://shop.test/').startswith('blocked:'))
        mock.assert_not_called()

    def test_known_pre_dispatch_failure_is_retryable(self):
        row = self.begin()
        self.journal.execute(row, Mock(side_effect=RuntimeError()), None, {}, '')
        self.assertEqual(row['action_status'], 'failed')
        retry = self.begin(2)
        self.assertEqual(self.journal.execute(retry, Mock(return_value='executed'), None, {}, ''), 'executed')

    def test_crash_during_dispatch_leaves_conservative_disk_record(self):
        row = self.begin()
        def executor(*args, on_dispatch):
            on_dispatch()
            # Snapshot at the exact point a process termination could occur.
            record = self.saved()[0]
            self.assertEqual(record['dispatch_state'], 'started')
            self.assertEqual(record['action_status'], 'outcome_unknown')
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.journal.execute(row, executor, None, {}, '')
        self.assertEqual(self.saved()[0]['action_status'], 'outcome_unknown')

    def test_screenshot_failure_does_not_erase_execution_or_prior_actions(self):
        row = self.begin()
        self.journal.execute(row, Mock(return_value='executed'), None, {}, '')
        self.journal.capture(row, None, self.path.parent, 'after', Mock(side_effect=RuntimeError('capture failed')))
        self.begin(2)
        saved = self.saved()
        self.assertEqual(saved[0]['result'], 'executed')
        self.assertIn('after_screenshot', saved[0]['evidence_errors'])
        self.assertEqual(saved[1]['action_status'], 'attempted')
        self.assertTrue(evidence_gaps(saved[0]))

    def test_atomic_replace_failure_preserves_previous_file(self):
        self.begin()
        before = self.path.read_bytes()
        with patch('Backend.action_journal.os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                atomic_json(self.path, [{'bad':'replacement'}])
        self.assertEqual(self.path.read_bytes(), before)

    def test_no_dispatch_if_initial_journal_write_fails(self):
        with patch('Backend.action_journal.atomic_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.begin()
        self.assertFalse(self.path.exists())

    def test_partial_rows_cannot_support_review_claims(self):
        row = self.begin()
        self.journal.execute(row, Mock(return_value='executed'), None, {}, '')
        self.assertFalse(compact_history([row])[0]['after_observation_available'])
        result = clean_review({'findings':[{'issue':'Broken', 'steps':[1], 'evidence':'Details'}]}, [row])
        self.assertEqual(result['findings'], [])

    def test_shared_navigation_guard_blocks_external_and_workspace_requests(self):
        context = Mock()
        install_navigation_guard(context, 'https://shop.test/')
        guard = context.route.call_args.args[1]
        for url, navigation, blocked in [('https://shop.test/cart',True,False), ('http://shop.test/cart',True,True),
                                         ('https://external.test/',True,True), ('http://localhost:8000/api/personas',False,True)]:
            route = Mock()
            route.request.url = url
            route.request.is_navigation_request.return_value = navigation
            guard(route)
            self.assertEqual(route.abort.called, blocked)

    def test_node_identity_change_is_not_visible_progress(self):
        self.state['controls'][0]['target_snapshot'] = {'identity':'one'}
        row = self.begin()
        after = deepcopy(self.state)
        after['controls'][0]['target_snapshot']['identity'] = 'two'
        self.journal.observe_after(row, None, Mock(return_value=(after, {})), Mock())
        self.assertFalse(any(row['observed_change'].values()))

    def test_library_reconstructs_partial_journal_when_report_lags(self):
        with patch.object(db, 'ROOT', self.path.parent):
            folder = self.path.parent/'results/exploration_crashed'
            journal = ActionJournal(folder/'history.json', [])
            atomic_json(folder/'report.json', {'run_status':'running', 'actions_recorded':0})
            journal.begin(1, self.state, {'action':'click','target':0}, 0)
            report = db.reports()[0]
            self.assertEqual(report['actions_recorded'], 1)
            self.assertEqual(report['execution_status'], 'partial')
            self.assertEqual(report['task_outcome'], 'unknown')
            self.assertTrue(report['evidence_incomplete'])
            self.assertEqual(db.report_evidence(folder.name)[0]['action_status'], 'attempted')

    def test_cli_refuses_uncertain_resume_without_rewriting_saved_evidence(self):
        from Backend import explore_website as cli
        root = self.path.parent
        folder = root/'results/exploration_resume'
        journal = ActionJournal(folder/'history.json', [])
        row = journal.begin(1, self.state, {'action':'click','target':0}, 0)
        journal.update(row, action_status='outcome_unknown', dispatch_state='started')
        for name, data in [('persona',{'name':'Visitor'}), ('flow_catalog',{'flows':[]}),
                           ('report',{'execution_status':'partial','outcome_verification':{'evidence':['saved']}}), ('browser_state',{})]:
            atomic_json(folder/(name+'.json'), data)
        originals = {p.name:p.read_bytes() for p in folder.glob('*.json')}
        with patch.object(cli, 'ROOT', root), patch.object(cli, 'sync_playwright') as browser, \
             patch('sys.argv', ['explore','--resume',str(folder),'--max-actions','2']):
            with self.assertRaises(SystemExit):
                cli.main()
            browser.assert_not_called()
        self.assertEqual({p.name:p.read_bytes() for p in folder.glob('*.json')}, originals)


class RunnerJournalTests(unittest.TestCase):
    def run_fixture(self, runner, failure):
        from Backend import explore_website as cli
        from Backend.app import live
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            module = live if runner == 'live' else cli
            stack.enter_context(patch.object(db, 'ROOT', root))
            stack.enter_context(patch.object(cli, 'ROOT', root))
            (root/'personas').mkdir()
            atomic_json(root/'personas/first_time_user.json', {'name':'Visitor'})
            atomic_json(root/'flows.json', {'flows':[]})
            api = MagicMock()
            stack.enter_context(patch.object(module, 'sync_playwright', api))
            state = {'url':'https://shop.test/', 'visible_text':'Details',
                     'controls':[{'id':0, 'tag':'button', 'type':'button', 'name':'Details', 'disabled':False}]}
            observed = Mock(return_value=(state, {}))
            if failure == 'after_observation':
                observed.side_effect = [(state, {}), RuntimeError('closed browser')]
            stack.enter_context(patch.object(module, 'observe', observed))
            stack.enter_context(patch.object(module, 'capture_step', side_effect=RuntimeError('no capture')))
            def executor(*args, on_dispatch):
                on_dispatch()
                if failure == 'dispatch':
                    raise RuntimeError('navigation failed after click')
                return 'executed'
            stack.enter_context(patch.object(module, 'execute', executor))
            prefix = 'Backend.app.live' if runner == 'live' else 'Backend.agents.exploration_agent'
            decisions = [{'action':'click','target':0}, ModelRequestError('Provider interrupted')]
            choose = stack.enter_context(patch(prefix + '.explore_next', side_effect=decisions))
            stack.enter_context(patch(prefix + '.review_run', return_value={}))
            if runner == 'live':
                live.run_live('fixture', {'persona':{'name':'Visitor'}, 'instructions':'Find details', 'cases':[],
                    'url':state['url'], 'project_id':None, 'persona_id':'visitor', 'max_actions':2}, Mock())
            else:
                stack.enter_context(patch('sys.argv', ['explore','--url',state['url'],'--max-actions','2','--flows',str(root/'flows.json')]))
                cli.main()
            directory = next((root/'results').glob('exploration_*'))
            report = db.read(directory/'report.json')
            history = db.read(directory/'history.json')
            self.assertEqual(len(history), 1)
            self.assertEqual(report['task_outcome'], 'unknown')
            self.assertEqual(report['execution_status'], 'partial')
            self.assertEqual(history[0]['action_status'], 'outcome_unknown' if failure == 'dispatch' else 'executed')
            self.assertIn('before_screenshot', history[0]['evidence_errors'])
            self.assertTrue(db.reports()[0]['evidence_incomplete'])
            self.assertTrue(db.report_evidence(directory.name)[0]['evidence_gaps'])
            if failure == 'provider':
                self.assertEqual(choose.call_count, 2)
            else:
                self.assertEqual(choose.call_count, 1)
            if failure == 'after_observation':
                self.assertEqual(history[0]['after'], {})
                self.assertIn('after_observation', history[0]['evidence_errors'])

    def test_live_and_cli_preserve_action_when_after_observation_fails(self):
        for runner in ('live','cli'):
            with self.subTest(runner=runner):
                self.run_fixture(runner, 'after_observation')

    def test_live_and_cli_preserve_prior_action_when_provider_interrupts(self):
        for runner in ('live','cli'):
            with self.subTest(runner=runner):
                self.run_fixture(runner, 'provider')

    def test_live_and_cli_stop_on_uncertain_dispatch(self):
        for runner in ('live','cli'):
            with self.subTest(runner=runner):
                self.run_fixture(runner, 'dispatch')
