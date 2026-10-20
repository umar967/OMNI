import io
import json
import os
import unittest
from unittest.mock import patch
from Backend.agents.exploration_agent import request_ollama
from Backend.agents.gemini_requests import ModelRequestError


class OllamaRequestTests(unittest.TestCase):
    def test_structured_response_and_non_thinking_payload(self):
        response = io.BytesIO(json.dumps({'response':'{"action":"stop"}'}).encode())
        with patch.dict(os.environ, {'OLLAMA_MAX_ATTEMPTS':'1', 'OLLAMA_TIMEOUT_SECONDS':'120'}), \
             patch('Backend.agents.exploration_agent.url_request.urlopen', return_value=response) as call:
            result = request_ollama('Choose action', {'type':'OBJECT', 'properties':{'action':{'type':'STRING'}}})
        self.assertEqual(result, {'action':'stop'})
        payload = json.loads(call.call_args.args[0].data)
        self.assertFalse(payload['think'])
        self.assertEqual(payload['format']['type'], 'object')
        self.assertEqual(call.call_args.kwargs['timeout'], 120)

    def test_timeout_does_not_retry_forever(self):
        with patch.dict(os.environ, {'OLLAMA_MAX_ATTEMPTS':'1'}), \
             patch('Backend.agents.exploration_agent.url_request.urlopen', side_effect=TimeoutError) as call, \
             patch('Backend.agents.exploration_agent.time.sleep') as sleep:
            with self.assertRaisesRegex(ModelRequestError, 'did not respond'):
                request_ollama('Choose action', {})
        self.assertEqual(call.call_count, 1)
        sleep.assert_not_called()
