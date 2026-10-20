"""No network or real sleeps: verify request bounds and quota handling."""
import os
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import httpx
from Backend.agents.gemini_requests import generate_json, GeminiRequestError


class APIError(Exception):
    def __init__(self, code, message='', headers=None):
        super().__init__(message)
        self.code = code
        self.response = SimpleNamespace(headers=headers or {})


class GeminiRequestTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'GEMINI_API_KEY':'test',
            'GEMINI_ACTION_TIMEOUT_SECONDS':'30', 'GEMINI_REVIEW_TIMEOUT_SECONDS':'60',
            'GEMINI_MAX_ATTEMPTS':'2', 'GEMINI_REQUEST_SPACING_SECONDS':'15'})
        self.env.start()
        self.client_patch = patch('Backend.agents.gemini_requests.genai.Client')
        self.factory = self.client_patch.start()
        self.client = MagicMock()
        self.factory.return_value.__enter__.return_value = self.client
        self.sleep_patch = patch('Backend.agents.gemini_requests.time.sleep')
        self.sleep = self.sleep_patch.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.client_patch.stop)
        self.addCleanup(self.sleep_patch.stop)

    def test_success_has_no_spacing_and_disables_sdk_retries(self):
        self.client.models.generate_content.return_value = SimpleNamespace(text='{"action":"stop"}')
        self.assertEqual(generate_json('prompt', decision=True)['action'], 'stop')
        options = self.factory.call_args.kwargs['http_options']
        self.assertEqual(options.timeout, 30000)
        self.assertEqual(options.retry_options.attempts, 1)
        self.sleep.assert_not_called()

    def test_transient_failure_retries_once_and_recovers(self):
        self.client.models.generate_content.side_effect = [APIError(503), SimpleNamespace(text='{}')]
        self.assertEqual(generate_json('prompt'), {})
        self.sleep.assert_called_once_with(2)
        self.assertEqual(self.factory.call_args.kwargs['http_options'].timeout, 60000)

    def test_timeout_stops_after_two_attempts(self):
        self.client.models.generate_content.side_effect = httpx.ReadTimeout('private request data')
        with self.assertRaisesRegex(GeminiRequestError, 'after 2 attempts'):
            generate_json('prompt')
        self.assertEqual(self.client.models.generate_content.call_count, 2)
        self.sleep.assert_called_once_with(2)

    def test_long_or_unknown_quota_wait_stops_immediately(self):
        for message in ('retryDelay: 60s', ''):
            with self.subTest(message=message):
                self.client.models.generate_content.reset_mock()
                self.client.models.generate_content.side_effect = APIError(429, message)
                with self.assertRaisesRegex(GeminiRequestError, 'quota reached'):
                    generate_json('prompt')
                self.assertEqual(self.client.models.generate_content.call_count, 1)
        self.sleep.assert_not_called()

    def test_short_retry_after_is_respected(self):
        self.client.models.generate_content.side_effect = [APIError(429, headers={'retry-after':'5'}), SimpleNamespace(text='{}')]
        self.assertEqual(generate_json('prompt'), {})
        self.sleep.assert_called_once_with(5)

    def test_permanent_error_and_invalid_json_do_not_retry_or_expose_details(self):
        for outcome in (APIError(403, 'secret'), SimpleNamespace(text='not JSON')):
            self.client.models.generate_content.reset_mock()
            self.client.models.generate_content.side_effect = None
            if isinstance(outcome, Exception):
                self.client.models.generate_content.side_effect = outcome
            else:
                self.client.models.generate_content.return_value = outcome
            with self.assertRaises(GeminiRequestError) as error:
                generate_json('prompt')
            self.assertNotIn('secret', str(error.exception))
            self.assertEqual(self.client.models.generate_content.call_count, 1)
        self.sleep.assert_not_called()
