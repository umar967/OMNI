import io
import json
import os
import unittest
from unittest.mock import patch
from Backend.agents.exploration_agent import request_ollama
from Backend.agents.gemini_requests import ModelRequestError


class OllamaRequestTests(unittest.TestCase):
    def test_local_action_prompt_is_small_and_keeps_observed_ids(self):
        from Backend.agents.local_persona import next_action
        from unittest.mock import Mock
        request = Mock(return_value={'action':'fill','target':10,'value':'Visitor','reason':'Enter name'})
        observation = {'visible_text':'Signup', 'controls':[{'id':10,'tag':'input','type':'text','name':'Full name','value':'private-entered-value'}]}
        decision = next_action({'name':'Older user','task':'Try signup'}, observation, [], request)
        prompt, schema = request.call_args.args
        self.assertNotIn('private-entered-value', prompt)
        self.assertLess(len(prompt), 2000)
        self.assertIn('"id":10', prompt)
        self.assertEqual(decision['target'], 10)
        self.assertIn('action', schema['properties'])

    def test_local_experience_is_checked_against_real_executed_steps(self):
        from Backend.agents.local_persona import experience
        from Backend.agents.exploration_agent import clean_review
        from unittest.mock import Mock
        state = {'visible_text':'Full name', 'controls':[{'id':10,'name':'Full name'}]}
        row = {'step':1,'result':'executed','before':state,'after':state,'decision':{'action':'fill','target':10}}
        comment = {'comment':'I could find the name field.','step':1,'evidence':'Full name'}
        request = Mock(return_value={'impression':comment,'helpful':comment,'improvement':comment})
        review = clean_review(experience({'name':'Visitor'}, [row], request), [row])
        self.assertIsNotNone(review['persona_feedback']['overall_impression'])
        self.assertEqual(review['review_validation']['excluded_items'], [])

    def test_already_filled_control_is_not_offered_again(self):
        from Backend.agents.local_persona import next_action
        from unittest.mock import Mock
        control = {'id':10,'tag':'input','type':'text','name':'Full name'}
        state = {'controls':[control], 'visible_text':'Full name'}
        history = [{'result':'executed','decision':{'action':'fill','target':10},
                    'before':state,'observed_change':{'controls':True}}]
        request = Mock(return_value={'action':'stop','target':-1,'value':'','reason':'Done'})
        next_action({'name':'Visitor'},state,history,request)
        self.assertEqual(request.call_args.args[1]['properties']['target']['enum'], [-1])

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
