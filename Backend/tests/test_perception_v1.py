"""Offline safety/behavior tests for the provisional v1 perception boundary."""
import unittest
from Backend.persona_engine.perception_v1 import (
    PilotPerception, extract_features, project_history, validate_action,
)


def fixture(count=45):
    controls = []
    for i in range(count):
        controls.append({'id':i, 'tag':'button', 'name':f'Option {i}', 'type':'button',
                         'disabled':False, 'bounding_box':{'x':10+i*13, 'y':100+i*8,
                                                          'width':110,'height':28},
                         'style':{'font_size':'14px'}, 'label_metadata':{'dom_id':f'option-{i}'},
                         'target_snapshot':{'secret':'never-send'}})
    return {'url':'http://example.invalid/test', 'title':'Fixture',
            'visible_text':'SECRET: excluded control may appear in text',
            'controls':controls, 'viewport':{'width':1366,'height':768},
            'scroll':{'x':0,'y':0,'height':1900}}


class PersonaV1Tests(unittest.TestCase):
    def test_geometry_handles_clipped_and_missing_values(self):
        obs=fixture(2)
        obs['controls'][0]['bounding_box']={'x':-20,'y':-20,'width':80,'height':80}
        obs['controls'][1].pop('bounding_box')
        a,b=extract_features(obs)
        self.assertGreater(a['visible_area_fraction'],0)
        self.assertLess(a['visible_area_fraction'],1)
        self.assertIsNone(b['visible_area_fraction'])
        self.assertIn('missing_or_invalid_geometry',b['quality_flags'])

    def test_scenario_distinction_is_deterministic_and_unchanged_ids(self):
        obs=fixture()
        first=PilotPerception({'technical_experience':'beginner','perception':{'attention':'standard'}})
        expert=PilotPerception({'technical_experience':'advanced','perception':{'attention':'standard'}})
        f=first.perceive(obs)
        e=expert.perceive(obs)
        self.assertEqual(len(f.model_observation['controls']),16)
        self.assertEqual(len(e.model_observation['controls']),32)
        self.assertEqual(f,first.perceive(obs))
        self.assertTrue(f.allowed_targets.issubset({c['id'] for c in obs['controls']}))
        self.assertEqual(f.provenance['parameter_status'],'provisional')
        self.assertFalse(f.provenance['human_calibrated'])

    def test_no_raw_text_or_internal_target_snapshot_leaks(self):
        f=PilotPerception({'technical_experience':'beginner','perception':{'attention':'standard'}}).perceive(fixture())
        self.assertEqual(f.model_observation['visible_text'],'')
        self.assertTrue(all('target_snapshot' not in c for c in f.model_observation['controls']))
        self.assertNotIn('SECRET',str(f.model_observation))

    def test_allowed_disallowed_and_non_target_actions(self):
        f=PilotPerception({'technical_experience':'beginner','perception':{'attention':'standard'}}).perceive(fixture())
        permit=next(iter(f.allowed_targets))
        reject=next(i for i in range(45) if i not in f.allowed_targets)
        self.assertIsNone(validate_action({'action':'click','target':permit,'value':''},f))
        self.assertIn('blocked:',validate_action({'action':'click','target':reject,'value':''},f))
        self.assertIsNone(validate_action({'action':'scroll','target':-1,'value':'down'},f))
        self.assertIn('blocked:',validate_action({'action':'click','target':True,'value':''},f))
        self.assertIsNone(validate_action({'action':'press','target':-1,'value':'Escape'},f))

    def test_safe_history_fails_closed_without_previous_perception(self):
        old={'step':1,'before':fixture(1),'after':fixture(1),
             'decision':{'action':'click','target':0},'result':'executed'}
        p=project_history([old])[0]
        self.assertEqual(p['before']['controls'],[])
        self.assertEqual(p['before']['visible_text'],'')
        self.assertEqual(p['after']['visible_text'],'')

    def test_custom_and_builtin_with_same_profile_share_results(self):
        obs=fixture()
        profile={'technical_experience':'beginner','perception':{'attention':'focused'}}
        a=PilotPerception(profile).perceive(obs)
        b=PilotPerception(dict(profile)).perceive(obs)
        self.assertEqual(a,b)

    def test_neutral_passthrough_preserves_legacy_text(self):
        p=PilotPerception({'technical_experience':'beginner'},'neutral_passthrough')
        v=p.perceive(fixture())
        self.assertEqual(len(v.model_observation['controls']),45)
        self.assertIn('SECRET',v.model_observation['visible_text'])


if __name__=='__main__':
    unittest.main()
