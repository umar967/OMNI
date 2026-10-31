"""Trace-derived reports and bounded capture readiness, without provider calls."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
from Backend.app.journey import journey_summary
from Backend.app.visual_evidence import capture_step, wait_for_capture
from Backend.app import storage as db
from Backend.agents.exploration_agent import clean_review
from Backend.tests.test_persona_feedback import interaction, review


class JourneyReportTests(unittest.TestCase):
    def test_successful_click_does_not_prove_task_success(self):
        summary = journey_summary({'task': 'Buy a product', 'run_status': 'finished'}, [interaction()])
        self.assertEqual(summary['outcome'], 'Completion not verified')
        self.assertIn('Explore the collection', summary['text'])
        self.assertIn('Buy a product', summary['text'])

    def test_failed_and_missing_trace_are_honest(self):
        summary = journey_summary({}, [interaction('automation_error')])
        self.assertIn('not confirmed website defects', summary['text'])
        self.assertIn('No interaction trace', journey_summary({}, [])['text'])

    def test_narrative_requires_valid_steps_quote_and_length(self):
        candidate = review()
        candidate['experience_summary'] = {'comment': ' '.join(['Observed'] * 80), 'steps': [1], 'evidence': 'Explore the collection'}
        self.assertIsNotNone(clean_review(candidate, [interaction()])['experience_summary'])
        candidate['experience_summary']['steps'] = [99]
        self.assertIsNone(clean_review(candidate, [interaction()])['experience_summary'])
        candidate['experience_summary']['steps'] = [1]
        candidate['experience_summary']['comment'] = 'Generic feedback.'
        self.assertIsNone(clean_review(candidate, [interaction()])['experience_summary'])

    def test_readiness_timeout_is_saved_as_a_limitation(self):
        page = Mock()
        page.wait_for_function.side_effect = PlaywrightTimeoutError('not ready')
        page.evaluate.return_value = dict(content=True, images_ready=False, pending_images=1, fonts_ready=True, busy=False)
        status = wait_for_capture(page, timeout=25)
        self.assertFalse(status['ready'])
        self.assertTrue(status['timed_out'])
        self.assertEqual(status['pending_images'], 1)
        self.assertEqual(page.wait_for_function.call_args.kwargs['timeout'], 25)

    def test_capture_keeps_masking_and_restores_target_after_failure(self):
        page, target = Mock(), Mock()
        target.evaluate.return_value = 'color:red'
        page.screenshot.side_effect = RuntimeError('capture failed')
        with tempfile.TemporaryDirectory() as folder, patch('Backend.app.visual_evidence.wait_for_capture', return_value={'ready': True}):
            with self.assertRaises(RuntimeError):
                capture_step(page, Path(folder), 1, 'before', target)
        self.assertEqual(target.evaluate.call_args.args[1], 'color:red')
        self.assertIn('mask', page.screenshot.call_args.kwargs)
        self.assertFalse(page.screenshot.call_args.kwargs['full_page'])

    def test_api_retains_timestamps_and_excludes_entered_values(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(db, 'ROOT', Path(folder)):
            run = Path(folder) / 'results' / 'exploration_test'
            row = interaction()
            row['elapsed_seconds'] = 12.5
            row['capture_metadata'] = {'after': {'ready': False, 'pending_images': 1}}
            row['before']['controls'][0]['value'] = 'private input'
            db.write(run / 'report.json', {'persona': 'Visitor'})
            db.write(run / 'history.json', [row])
            result = db.report_evidence('exploration_test')[0]
            self.assertEqual(result['elapsed_seconds'], 12.5)
            self.assertFalse(result['capture_metadata']['after']['ready'])
            self.assertNotIn('value', result['before']['controls'][0])
            self.assertIn('journey_summary', db.reports()[0])


class CaptureBrowserTests(unittest.TestCase):
    """Small controlled rendering fixture: no model or external website access."""
    def test_delayed_visible_image_and_skeleton_are_awaited(self):
        with sync_playwright() as p:
            with p.chromium.launch(channel='chrome', headless=True) as browser:
                page = browser.new_page()
                page.set_content('''<h1>Product detail</h1><div aria-busy="true">Loading product</div>
                    <img width="50" height="50" id="product">
                    <script>setTimeout(() => {
                      document.querySelector('img').src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50"><rect width="50" height="50" fill="green"/></svg>';
                      document.querySelector('[aria-busy]').remove();
                    }, 300);</script>''')
                result = wait_for_capture(page, timeout=3000)
                self.assertTrue(result['ready'])
                self.assertEqual(result['pending_images'], 0)
                self.assertFalse(result['busy'])
                with tempfile.TemporaryDirectory() as folder:
                    meta = {}
                    filename = capture_step(page, Path(folder), 1, 'after', metadata=meta)
                    self.assertTrue((Path(folder) / 'evidence' / filename).is_file())
                    self.assertEqual(len(meta['sha256']), 64)
                page.set_content('<h1>Broken image fixture</h1><img width="50" height="50" src="data:image/png,invalid">')
                incomplete = wait_for_capture(page, timeout=200)
                self.assertFalse(incomplete['ready'])
                self.assertEqual(incomplete['pending_images'], 1)


if __name__ == '__main__':
    unittest.main()
