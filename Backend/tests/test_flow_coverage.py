"""Check that flow coverage distinguishes attempts from observed completion."""

import json
from pathlib import Path
import unittest

from Backend.flow_coverage import assess_flows


CATALOG = json.loads((Path(__file__).resolve().parents[1] /
                      'flow_catalog.json').read_text(encoding='utf-8'))


def step(number, target, before_url, after_url, before_text='', after_text='',
         result='executed', before_controls=None, after_controls=None):
    before = {'url': before_url, 'visible_text': before_text,
              'controls': [{'id': 0, 'name': target}] + (before_controls or [])}
    after = {'url': after_url, 'visible_text': after_text,
             'controls': after_controls or []}
    return {'step': number, 'decision': {'action': 'click', 'target': 0},
            'result': result, 'before': before, 'after': after,
            'observed_change': {'url': before_url != after_url,
                                'visible_text': before_text != after_text,
                                'controls': before['controls'] != after['controls']}}


class FlowCoverageTests(unittest.TestCase):
    def test_attempt_and_completed_collection_are_distinct(self):
        home = 'http://127.0.0.1:5173/'
        history = [step(1, 'Discover', home, home),
                   step(2, 'Explore the collection', home, home + 'products')]
        flows = {f['id']: f for f in assess_flows(history, CATALOG)}
        self.assertEqual(flows['collection']['status'], 'confirmed')
        self.assertEqual(flows['collection']['evidence_steps'], [1, 2])
        self.assertEqual(flows['filter']['status'], 'untested')

    def test_existing_text_and_blocked_action_do_not_confirm(self):
        url = 'http://127.0.0.1:5173/products'
        history = [step(1, 'View Arc Table Lamp', url, url,
                        'Arc Table Lamp Add to bag', 'Arc Table Lamp Add to bag'),
                   step(2, 'Add to bag', url, url, result='blocked: boundary')]
        flows = {f['id']: f for f in assess_flows(history, CATALOG)}
        self.assertEqual(flows['product_details']['status'], 'attempted')
        self.assertEqual(flows['add_to_bag']['status'], 'blocked')

    def test_filter_requires_query_parameter(self):
        url = 'http://127.0.0.1:5173/products'
        history = [step(1, 'Apply filters', url, url + '?category=lighting')]
        flows = {f['id']: f for f in assess_flows(history, CATALOG)}
        self.assertEqual(flows['filter']['status'], 'confirmed')

    def test_product_details_require_new_visible_evidence(self):
        url = 'http://127.0.0.1:5173/products'
        history = [step(1, 'View Arc Table Lamp', url, url,
                        'Arc Table Lamp', 'Arc Table Lamp Add to bag')]
        flows = {f['id']: f for f in assess_flows(history, CATALOG)}
        self.assertEqual(flows['product_details']['status'], 'confirmed')


if __name__ == '__main__':
    unittest.main()
