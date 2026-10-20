"""Check evidence handling for simulated persona experience reports."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from Backend.agents.exploration_agent import apply_review, clean_review, review_run


def interaction(result='executed'):
    before = {
        'url': 'http://example.test/', 'visible_text': 'Explore the collection',
        'controls': [{'id': 0, 'name': 'Explore the collection'}],
    }
    after = {
        'url': 'http://example.test/products', 'visible_text': 'The everyday edit.',
        'controls': [],
    }
    return {
        'step': 1, 'decision': {'action': 'click', 'target': 0, 'value': '',
                              'reason': 'I want to see the products.'},
        'result': result, 'before': before, 'after': after,
        'observed_change': {'url': True, 'visible_text': True},
    }


def review():
    comment = {
        'comment': 'I would understand where to begin browsing.',
        'steps': [1], 'evidence': 'Explore the collection',
    }
    return {
        'persona_feedback': {
            'overall_impression': deepcopy(comment),
            'what_worked_well': [deepcopy(comment)],
            'difficult_moments': [], 'suggested_improvements': [],
        },
        'findings': [], 'flow_assessments': [],
        'coverage_gaps': ['No coverage gaps observed'],
    }


class PersonaFeedbackTests(unittest.TestCase):
    def test_feedback_is_retained_without_any_defect(self):
        result = clean_review(review(), [interaction()])
        report = {'actions_recorded': 1, 'coverage': {'flows': [
            {'name': 'Search the collection', 'status': 'untested'},
        ]}}
        apply_review(report, result)
        self.assertTrue(report['persona_feedback']['what_worked_well'])
        self.assertEqual(report['findings'], [])
        self.assertEqual(report['feedback_type'], 'simulated_persona_experience')
        self.assertIn('not measured human feelings', report['feedback_note'])
        self.assertEqual(report['coverage_gaps'],
                         ['Search the collection: untested in the recorded visit.'])

    def test_invented_quote_and_unknown_step_are_excluded(self):
        candidate = review()
        candidate['persona_feedback']['difficult_moments'] = [
            {'comment': 'I might be unsure.', 'steps': [1], 'evidence': 'Made up label'},
            {'comment': 'I might be unsure.', 'steps': [99], 'evidence': 'Explore'},
        ]
        result = clean_review(candidate, [interaction()])
        self.assertEqual(result['persona_feedback']['difficult_moments'], [])
        self.assertEqual(len(result['review_validation']['excluded_items']), 2)

    def test_tool_failure_cannot_support_website_feedback(self):
        result = clean_review(review(), [interaction('automation_error')])
        self.assertIsNone(result['persona_feedback']['overall_impression'])
        self.assertEqual(result['persona_feedback']['what_worked_well'], [])

    def test_no_clear_issue_placeholder_is_not_a_defect(self):
        candidate = review()
        candidate['findings'] = [
            {'issue': 'No clear issue', 'steps': [1],
             'evidence': 'Explore the collection'},
        ]
        result = clean_review(candidate, [interaction()])
        self.assertEqual(result['findings'], [])

    def test_review_request_uses_experience_schema_and_preserves_reason(self):
        with patch.dict('os.environ', {'OMNI_MODEL_PROVIDER':'gemini'}), patch('Backend.agents.exploration_agent.request_json', return_value=review()) as request:
            review_run({'name': 'First-Time User'}, [interaction()])
        prompt, schema = request.call_args.args
        self.assertIn('persona_feedback', schema['required'])
        self.assertIn('never measured emotions', prompt)
        self.assertIn('I want to see the products.', prompt)
        json.dumps(schema)

    def test_saved_run_reviewer_persists_feedback_without_browser_actions(self):
        from Backend.review_saved_run import main
        with tempfile.TemporaryDirectory() as folder:
            run_dir = Path(folder)
            for name, data in (
                ('persona.json', {'name': 'First-Time User'}),
                ('history.json', [interaction()]),
                ('report.json', {'review_status': 'not_completed', 'findings': [],
                                 'limitations': ['Review failed; retry needed.']}),
            ):
                (run_dir / name).write_text(json.dumps(data), encoding='utf-8')
            with patch('sys.argv', ['review_saved_run.py', '--run', folder]), \
                    patch('Backend.review_saved_run.review_run', return_value=review()):
                main()
            report = json.loads((run_dir / 'report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['review_status'], 'completed')
            self.assertTrue(report['persona_feedback']['what_worked_well'])
            self.assertEqual(report['findings'], [])
            self.assertEqual(report['limitations'], [])


if __name__ == '__main__':
    unittest.main()
