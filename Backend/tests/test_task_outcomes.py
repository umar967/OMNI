"""Adversarial endpoint verification, without model calls or external sites."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from pydantic import ValidationError

from Backend.task_outcomes import TaskContract, evaluate_sample, verify, attach_verification, unverified
from Backend.agents.exploration_agent import clean_review, apply_review
from Backend.app.journey import journey_summary
from Backend.app import storage as db
from Backend.tests.test_persona_feedback import interaction, review


def contract(strategy='cart_product', **changes):
    endpoint = dict(strategy=strategy, expected_url='https://shop.test/cart',
                    container_selector='#collection', ready_selector='#ready',
                    item_selector='.item', name_selector='.name', product_name='Arc Lamp',
                    quantity_selector='.quantity', complete_collection=True)
    if strategy == 'product_search':
        endpoint.update(query_selector='#query', query_value='Arc Lamp')
    endpoint.update(changes)
    return TaskContract(description='Find the requested endpoint', endpoint=endpoint)


def sample(**changes):
    return dict(url='https://shop.test/cart', container=True, ready=True, truncated=False,
                rows=[{'visible': True, 'name': 'Arc Lamp', 'quantity': '1'}], query='Arc Lamp', empty=False) | changes


class OutcomeTests(unittest.TestCase):
    def test_matching_endpoint_and_linked_evidence(self):
        result = evaluate_sample(contract(), sample(), step=3, final=True)
        self.assertEqual(result.task_outcome, 'verified_complete')
        self.assertEqual(result.evidence[0]['step'], 3)
        self.assertEqual(result.evidence[0]['observed']['rows'][0]['quantity'], '1')
        self.assertTrue(result.evidence[0]['id'])

    def test_wrong_product_quantity_and_duplicate_rows(self):
        for rows in [[{'visible': True, 'name': 'Other Lamp', 'quantity': '1'}],
                     [{'visible': True, 'name': 'Arc Lamp', 'quantity': '2'}],
                     sample()['rows'] * 2]:
            with self.subTest(rows=rows):
                self.assertEqual(evaluate_sample(contract(), sample(rows=rows), final=True).task_outcome,
                                 'verified_incomplete')
                self.assertEqual(evaluate_sample(contract(), sample(rows=rows)).task_outcome, 'unknown')

    def test_click_or_unrelated_change_cannot_complete(self):
        for data in [sample(url='https://shop.test/products'), sample(container=False),
                     sample(ready=False), sample(rows=[]), sample(truncated=True),
                     sample(rows=[{'visible': False, 'name': 'Arc Lamp', 'quantity': '1'}])]:
            with self.subTest(data=data):
                self.assertEqual(evaluate_sample(contract(), data, final=True).task_outcome, 'unknown')

    def test_missing_or_ambiguous_quantity_is_not_failed_expectation(self):
        for quantity in [None, 'Quantity: 1', '', '1.0']:
            result = evaluate_sample(contract(), sample(rows=[{'visible': True, 'name': 'Arc Lamp', 'quantity': quantity}]), final=True)
            self.assertEqual(result.task_outcome, 'unknown')

    def test_empty_collection_needs_explicit_evidence(self):
        self.assertEqual(evaluate_sample(contract(), sample(rows=[]), final=True).task_outcome, 'unknown')
        self.assertEqual(evaluate_sample(contract(), sample(rows=[], empty=True), final=True).task_outcome, 'verified_incomplete')

    def test_cart_needs_complete_collection_even_for_positive(self):
        self.assertEqual(evaluate_sample(contract(complete_collection=False), sample(), final=True).task_outcome, 'unknown')

    def test_listing_requires_products_and_correct_url(self):
        c = contract('product_listing')
        self.assertEqual(evaluate_sample(c, sample()).task_outcome, 'verified_complete')
        self.assertEqual(evaluate_sample(c, sample(rows=[])).task_outcome, 'unknown')
        self.assertEqual(evaluate_sample(c, sample(url='https://other.test/cart')).task_outcome, 'unknown')

    def test_search_requires_query_and_exact_product(self):
        c = contract('product_search')
        self.assertEqual(evaluate_sample(c, sample()).task_outcome, 'verified_complete')
        self.assertEqual(evaluate_sample(c, sample(query='other')).task_outcome, 'unknown')
        self.assertEqual(evaluate_sample(c, sample(query=None), final=True).task_outcome, 'unknown')
        self.assertEqual(evaluate_sample(c, sample(rows=[{'visible': True, 'name': 'Arc Lamp Pro', 'quantity': None}]), final=True).task_outcome, 'verified_incomplete')

    def test_unconfigured_unsupported_and_inspection_failure(self):
        page = MagicMock()
        self.assertEqual(verify(page, TaskContract(description='Pay')).task_outcome, 'unknown')
        page.evaluate.assert_not_called()
        page.evaluate.side_effect = TimeoutError('Unavailable')
        self.assertEqual(verify(page, contract(), final=True).task_outcome, 'unknown')
        self.assertEqual(unverified('Screenshot cannot verify live endpoint', unsupported=True).task_outcome, 'unsupported')
        with self.assertRaises(ValidationError):
            contract('purchase')

    def test_model_claim_cannot_write_outcome_or_execution(self):
        report = {'limitations': [], 'execution_status': 'failed'}
        attach_verification(report, contract(), unverified())
        original = deepcopy(report['outcome_verification'])
        candidate = review() | {'task_outcome': 'verified_complete', 'execution_status': 'finished',
                                'outcome_verification': {'verifier': 'dom-endpoint-v1', 'task_outcome': 'verified_complete'},
                                'flow_assessments': [{'status': 'completed', 'steps': [1], 'explanation': 'It worked'}]}
        cleaned = clean_review(candidate, [interaction()])
        self.assertNotIn('task_outcome', cleaned)
        apply_review(report, cleaned)
        self.assertEqual(report['task_outcome'], 'unknown')
        self.assertEqual(report['execution_status'], 'failed')
        self.assertEqual(report['outcome_verification'], original)
        self.assertEqual(report['flow_assessments'][0]['status'], 'attempted')

    def test_legacy_ai_status_not_trusted_by_journey(self):
        result = journey_summary({'task_outcome': 'verified_complete', 'run_status': 'finished'}, [interaction()])
        self.assertEqual(result['task_outcome'], 'unknown')
        self.assertEqual(result['outcome'], 'Completion not verified')

    def test_schema_requires_strategy_conditions(self):
        for changes in [{'product_name': None}, {'quantity_selector': None}, {'expected_url': 'javascript:alert(1)'}]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                contract(**changes)
        with self.assertRaises(ValidationError):
            contract('product_search', query_selector=None)


class BrowserOutcomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = sync_playwright().start()
        cls.browser = cls.p.chromium.launch(channel='chrome', headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.p.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)
        self.page.route('**/*', lambda route: route.fulfill(body='<html><body></body></html>', content_type='text/html'))
        self.page.goto('https://shop.test/cart')

    def render(self, name='Arc Lamp', quantity='1'):
        self.page.set_content(f'<div id="ready">Ready</div><input id="query" value="Arc Lamp">'
                              f'<section id="collection"><article class="item"><h2 class="name">{name}</h2>'
                              f'<output class="quantity">{quantity}</output></article></section>')

    def test_real_dom_matches_all_strategies(self):
        self.render()
        for strategy in ['product_listing', 'product_search', 'cart_product']:
            with self.subTest(strategy=strategy):
                result = verify(self.page, contract(strategy), final=True)
                self.assertEqual(result.task_outcome, 'verified_complete')

    def test_add_button_and_nonempty_wrong_cart_insufficient(self):
        self.page.set_content('<button onclick="this.textContent=\'Added\'">Add to Cart</button>')
        self.page.locator('button').click()
        self.assertEqual(verify(self.page, contract(), final=True).task_outcome, 'unknown')
        self.render('Wrong product')
        self.assertEqual(verify(self.page, contract(), final=True).task_outcome, 'verified_incomplete')
        self.render(quantity='2')
        self.assertEqual(verify(self.page, contract(), final=True).task_outcome, 'verified_incomplete')

    def test_busy_hidden_and_invalid_selectors_are_unknown(self):
        self.render()
        self.page.locator('#collection').evaluate("el => el.setAttribute('aria-busy','true')")
        self.assertEqual(verify(self.page, contract(), final=True).task_outcome, 'unknown')
        self.render()
        self.page.locator('.quantity').evaluate("el => el.style.display='none'")
        self.assertEqual(verify(self.page, contract(), final=True).task_outcome, 'unknown')
        self.assertEqual(verify(self.page, contract(name_selector='['), final=True).task_outcome, 'unknown')


class OutcomeIntegrationTests(unittest.TestCase):
    def test_testlab_fixtures_use_the_shared_contract(self):
        fixtures = json.loads((Path(__file__).parent / 'fixtures/testlab_outcomes.json').read_text())
        self.assertEqual({TaskContract.model_validate(item).endpoint.strategy for item in fixtures},
                         {'product_listing', 'product_search', 'cart_product'})

    def test_cli_uses_same_verifier_and_saves_separate_statuses(self):
        from Backend import explore_website as cli
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'personas').mkdir()
            (root / 'personas/first_time_user.json').write_text(json.dumps({'name': 'Visitor'}))
            (root / 'flows.json').write_text(json.dumps({'flows': []}))
            (root / 'contract.json').write_text(contract().model_dump_json())
            api = MagicMock()
            page = api.return_value.__enter__.return_value.chromium.launch.return_value.new_context.return_value.new_page.return_value
            page.evaluate.return_value = sample(rows=[{'visible': True, 'name': 'Other', 'quantity': '1'}])
            state = {'url': 'https://shop.test/cart', 'title': 'Cart', 'visible_text': 'Other', 'controls': []}
            with patch.object(cli, 'ROOT', root), patch.object(cli, 'sync_playwright', api), \
                 patch.object(cli, 'observe', return_value=(state, {})), \
                 patch('Backend.agents.exploration_agent.explore_next', return_value={'action': 'stop', 'target': -1, 'reason': 'Complete'}), \
                 patch('Backend.agents.exploration_agent.review_run', return_value=review()), \
                 patch.dict('os.environ', {}), \
                 patch('sys.argv', ['explore', '--url', 'https://shop.test/cart', '--max-actions', '1',
                                    '--flows', str(root / 'flows.json'), '--task-contract', str(root / 'contract.json')]):
                cli.main()
            result = json.loads(next((root / 'results').glob('*/report.json')).read_text())
            self.assertEqual(result['task_outcome'], 'verified_incomplete')
            self.assertEqual(result['execution_status'], 'finished')
            self.assertEqual(result['review_status'], 'unavailable')

    def test_live_saved_result_survives_review_claim(self):
        from Backend.app.live import run_live
        with tempfile.TemporaryDirectory() as folder, patch.object(db, 'ROOT', Path(folder)):
            api = MagicMock()
            page = api.return_value.__enter__.return_value.chromium.launch.return_value.new_context.return_value.new_page.return_value
            page.evaluate.return_value = sample(rows=[{'visible': True, 'name': 'Other', 'quantity': '1'}])
            plan = {'persona': {'name': 'Visitor'}, 'instructions': contract().description,
                    'task_contract': contract().model_dump(), 'cases': [], 'url': 'https://shop.test/cart',
                    'persona_id': 'visitor', 'project_id': None, 'max_actions': 1}
            state = {'url': plan['url'], 'visible_text': 'Help', 'controls': []}
            with patch('Backend.app.live.sync_playwright', api), \
                 patch('Backend.app.live.observe', return_value=(state, {})), \
                 patch('Backend.app.live.capture_step', return_value='step-1-after.png'), \
                 patch('Backend.app.live.explore_next', return_value={'action': 'stop', 'target': -1, 'reason': 'Task completed', 'task_outcome': 'verified_complete'}), \
                 patch('Backend.app.live.review_run', return_value=review()):
                run_live('outcome', plan, MagicMock())
            result = db.read(Path(folder) / 'results/exploration_outcome/report.json')
            self.assertEqual(result['execution_status'], 'finished')
            self.assertEqual(result['task_outcome'], 'verified_incomplete')
            self.assertEqual(result['review_status'], 'unavailable')
            self.assertEqual(result['outcome_verification']['evidence'][0]['step'], 1)
            self.assertEqual(db.reports()[0]['journey_summary']['task_outcome'], 'verified_incomplete')

    def test_plan_contract_roundtrip_and_invalid_strategy(self):
        from Backend.app.server import app
        with tempfile.TemporaryDirectory() as folder, patch.object(db, 'ROOT', Path(folder)):
            db.write(db.safe_file('personas', 'visitor'), {'name': 'Visitor'})
            client = TestClient(app)
            body = {'url': 'https://shop.test', 'instructions': contract().description, 'persona_id': 'visitor',
                    'method': 'live', 'task_contract': contract().model_dump()}
            response = client.post('/api/plans', json=body, headers={'X-OMNI-Client': 'workspace'})
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(response.json()['task_contract'], contract().model_dump())
            body['task_contract']['endpoint']['strategy'] = 'payment'
            self.assertEqual(client.post('/api/plans', json=body, headers={'X-OMNI-Client': 'workspace'}).status_code, 422)
