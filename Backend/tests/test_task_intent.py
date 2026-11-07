"""Task intent must win over starting-page content and default persona goals."""
import unittest
from unittest.mock import Mock, MagicMock
from Backend.agents.local_persona import next_action
from Backend.action_safety import validate


class TaskIntentTests(unittest.TestCase):
    def test_cart_task_overrides_signup_persona_goal(self):
        task = 'Add Studio Headphones to the cart'
        request = Mock(return_value={'action':'click','target':7,'value':'','reason':'Find headphones'})
        observation = {'visible_text':'Create an account', 'controls':[
            {'id':7,'name':'Explore the collection','tag':'a'},
            {'id':10,'name':'Full name','tag':'input','type':'text'}]}
        next_action({'name':'Older user','goal':'Create an account independently', 'task':task}, observation, [], request)
        prompt = request.call_args.args[0]
        self.assertTrue(prompt.startswith('CURRENT TASK (your objective): ' + task))
        self.assertNotIn('Create an account independently', prompt)
        self.assertNotIn('Fill empty text/email inputs', prompt)
        self.assertIn('Follow same-site links', prompt)

    def test_cart_form_button_is_allowed_but_checkout_stays_blocked(self):
        current = {'identity':'test:1', 'connected':True, 'visible':True, 'enabled':True,
                   'semantic':{'name':'Add to cart', 'tag':'button', 'type':'submit',
                               'form':{'action':'http://localhost:5173/cart', 'target':'', 'credentials':False}}}
        self.assertIsNone(validate(current, current, 'click', '', 'http://localhost:5173/'))
        current['semantic']['name'] = 'Checkout'
        self.assertTrue(validate(current, current, 'click', '', 'http://localhost:5173/').startswith('blocked:'))

    def test_recent_action_memory_retains_cart_confirmation(self):
        request = Mock(return_value={'action':'click','target':6,'value':'','reason':'Verify cart'})
        before = {'visible_text':'Studio Headphones\nAdd to bag', 'controls':[{'id':1,'name':'Add to bag'}]}
        after = {'visible_text':'Studio Headphones added to your bag.',
                 'controls':[{'id':6,'name':'Shopping bag, 1 items','tag':'a'}]}
        history = [{'decision':{'action':'click','target':1}, 'before':before, 'after':after,
                    'result':'executed', 'observed_change':{'visible_text':True}}]
        next_action({'task':'Add Studio Headphones to cart'}, after, history, request)
        self.assertIn('Studio Headphones added to your bag.', request.call_args.args[0])
        self.assertIn('NEVER add the same item again', request.call_args.args[0])
