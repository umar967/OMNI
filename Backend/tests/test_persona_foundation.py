"""Universal profiles are data, never a separate built-in/custom execution path."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from fastapi.testclient import TestClient
from pydantic import ValidationError

from Backend.app import storage as db
from Backend.app.server import app
from Backend.persona_engine.schema import UniversalPersona, CalibrationArtifact
from Backend.persona_engine.resolver import resolve_persona, compatibility_record, agent_persona

HEADERS = {'X-OMNI-Client': 'workspace'}


def profile(**fields):
    return {'schema_version': '1.0', 'profile': {'name': 'Visitor', **fields}}


class PersonaContractTests(unittest.TestCase):
    def test_minimum_defaults_and_roundtrip(self):
        result = resolve_persona(profile())
        self.assertEqual(result.persona.profile.environment.viewport.width, 1366)
        self.assertIsNone(result.task)
        self.assertFalse(result.unsupported_capabilities)
        self.assertEqual(result.engine.active_calibration_ids, [])
        self.assertFalse(result.engine.behavioral_simulation_enabled)
        self.assertEqual(resolve_persona(result.persona.model_dump()), result)

    def test_all_repository_presets_and_custom_copies_use_same_engine(self):
        for path in (Path(__file__).parents[1] / 'personas').glob('*.json'):
            with self.subTest(preset=path.stem):
                raw = json.loads(path.read_text())
                built_in = resolve_persona(raw)
                custom = built_in.persona.model_dump()
                custom['provenance']['origin'] = 'custom'
                resolved = resolve_persona(custom)
                self.assertEqual(built_in.persona.profile, resolved.persona.profile)
                self.assertEqual(built_in.engine, resolved.engine)
                self.assertEqual(built_in.unsupported_capabilities, resolved.unsupported_capabilities)

    def test_invalid_profiles(self):
        cases = [{}, profile(name=' '), profile(technical_experience='wizard'),
                 profile(website_familiarity='expert'), profile(unknown=True),
                 profile(environment={'viewport': {'width': 10}}),
                 profile(environment={'viewport': {'height': True}}),
                 profile(recovery={'retry_limit': -1}), profile(recovery={'retry_limit': 11}),
                 profile(perception={'attention': 'magic'}),
                 profile(navigation={'preferred_actions': ['delete']}),
                 profile(task_context={'criteria': []}),
                 {**profile(), 'schema_version': '2.0'},
                 {**profile(), 'engine': {'policy_mode': 'bypass'}}]
        for data in cases:
            with self.subTest(data=data), self.assertRaises((ValidationError, KeyError)):
                resolve_persona(data)

    def test_device_input_compatibility(self):
        for device, method in [('mobile', 'mouse_keyboard'), ('tablet', 'keyboard_only'), ('desktop', 'touch')]:
            with self.subTest(device=device), self.assertRaisesRegex(ValidationError, 'input'):
                resolve_persona(profile(environment={'device': device, 'input_method': method}))

    def test_valid_but_unsupported_capabilities_are_explicit(self):
        result = resolve_persona(profile(environment={'device': 'mobile', 'input_method': 'touch',
                                                     'viewport': {'width': 390, 'height': 844}},
                                         accessibility={'screen_reader_required': True,
                                                        'reduced_motion_required': True,
                                                        'visual_requirements': ['high_contrast']}))
        self.assertEqual(len(result.unsupported_capabilities), 6)
        with self.assertRaisesRegex(ValueError, 'not implemented'):
            result.require_supported()

    def test_legacy_aliases_and_non_destructive_migration(self):
        old = {'name': 'Existing', 'technical_level': 'low', 'goal': 'Find help',
               'website_familiarity': 'Has never used this website', 'gender': 'female',
               'behavior_preferences': ['Read labels'], 'custom_old_field': 42}
        original = deepcopy(old)
        result = compatibility_record(old, 'existing')
        self.assertEqual(old, original)
        self.assertEqual(result['custom_old_field'], 42)
        self.assertEqual(result['universal_persona']['profile']['technical_experience'], 'beginner')
        self.assertEqual(result['universal_persona']['profile']['website_familiarity'], 'first_visit')
        self.assertEqual(resolve_persona(result).persona, resolve_persona(old).persona)
        self.assertEqual(resolve_persona({'name': 'Other', 'gender': 'female'}).persona.profile.technical_experience,
                         'intermediate')

    def test_task_override_and_projection(self):
        data = profile(task_context={'default_goal': 'Default'})
        self.assertEqual(resolve_persona(data, ' Current ').task, 'Current')
        self.assertEqual(resolve_persona(data).task, 'Default')
        with self.assertRaises(ValueError):
            resolve_persona(data, ' ')
        prompt = agent_persona(data, 'Current')
        self.assertEqual(prompt['task'], 'Current')
        self.assertNotIn('universal_persona', prompt)
        self.assertNotIn('engine', prompt)

    def test_calibration_requires_evidence_and_never_activates_claims(self):
        artifact = {'artifact_id': 'test-artifact', 'dataset': 'UEyes', 'dataset_version': 'v1',
                    'source': 'https://example.invalid/test-only', 'license': 'test fixture',
                    'fitting_method': 'test-only histogram', 'parameter_paths': ['profile.perception.attention'],
                    'status': 'calibrated'}
        with self.assertRaisesRegex(ValidationError, 'held-out evaluation'):
            CalibrationArtifact.model_validate(artifact)
        artifact.update(fit_split='train', artifact_sha256='a' * 64,
                        evaluation={'split': 'test', 'metrics': {'test_metric': 0.5},
                                    'report_source': 'test report', 'leakage_controls': 'test-only split assertion'})
        result = resolve_persona({**profile(), 'calibration': [artifact]})
        self.assertEqual(result.engine.parameter_status, 'provisional')
        self.assertEqual(result.engine.active_calibration_ids, [])
        for mutation in [dict(parameter_paths=['profile.no_such_field']),
                         dict(evaluation={**artifact['evaluation'], 'split': 'train'}),
                         dict(evaluation={**artifact['evaluation'], 'metrics': {'metric': float('nan')}})]:
            with self.subTest(mutation=mutation), self.assertRaises(ValidationError):
                resolve_persona({**profile(), 'calibration': [{**artifact, **mutation}]})
        with self.assertRaisesRegex(ValidationError, 'unique'):
            resolve_persona({**profile(), 'calibration': [artifact, artifact]})

    def test_research_and_provisional_artifact_contracts(self):
        for dataset in ['UEyes', 'Mind2Web', 'Future Dataset']:
            for status in ['research-informed', 'provisional']:
                a = CalibrationArtifact(artifact_id='reference', dataset=dataset, dataset_version='documented-version',
                                        source='https://example.invalid', license='Unverified', fitting_method='Not fitted',
                                        parameter_paths=['profile.perception.attention'], status=status)
                self.assertIsNone(a.evaluation)


class PersonaAPITests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = patch.object(db, 'ROOT', Path(temp.name))
        root.start()
        self.addCleanup(root.stop)
        self.client = TestClient(app)

    def post(self, path, body):
        return self.client.post(path, json=body, headers=HEADERS)

    def test_schema_endpoint_contains_all_dimensions(self):
        schema = self.client.get('/api/personas/schema').json()
        properties = schema['$defs']['Profile']['properties']
        self.assertEqual(set(properties), {'name', 'description', 'technical_experience', 'website_familiarity',
                                          'environment', 'accessibility', 'perception', 'navigation', 'recovery', 'task_context'})
        self.assertEqual(schema['additionalProperties'], False)

    def test_create_list_and_update_canonical_with_legacy_frontend(self):
        original = profile(description='Preserve description', navigation={'strategy': 'search_first'},
                           recovery={'retry_limit': 2})
        response = self.post('/api/personas', original)
        self.assertEqual(response.status_code, 201, response.text)
        person = response.json()
        self.assertEqual(person['name'], 'Visitor')
        old_form = {'name': 'Renamed', 'goal': 'Find help', 'criteria': ['Feedback'], 'technical_skill': 'basic'}
        updated = self.client.put('/api/personas/' + person['id'], json=old_form, headers=HEADERS)
        self.assertEqual(updated.status_code, 200, updated.text)
        p = updated.json()['universal_persona']['profile']
        self.assertEqual(p['name'], 'Renamed')
        self.assertEqual(p['technical_experience'], 'beginner')
        self.assertEqual(p['navigation']['strategy'], 'search_first')
        self.assertEqual(p['recovery']['retry_limit'], 2)
        self.assertEqual(self.client.get('/api/personas').json()[0], updated.json())

    def test_legacy_and_canonical_requests_reject_invalid_values(self):
        for body in [profile(technical_experience='wizard'),
                     {'name': 'Old', 'goal': 'Goal', 'criteria': ['Labels'], 'technical_skill': 'wizard'},
                     {**profile(), 'engine': {}},
                     {'name': 'Old', 'goal': 'Goal', 'criteria': ['Labels'], 'schema_version': '9'}]:
            with self.subTest(body=body):
                self.assertEqual(self.post('/api/personas', body).status_code, 422)
        self.assertEqual(db.personas(), [])

    def test_validation_does_not_save_and_reports_unsupported(self):
        response = self.post('/api/personas/validate', profile(accessibility={'screen_reader_required': True}))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['unsupported_capabilities'])
        self.assertEqual(db.personas(), [])

    def test_unsupported_live_run_rejected_before_provider_or_browser(self):
        person = self.post('/api/personas', profile(environment={'input_method': 'keyboard_only'})).json()
        plan = self.post('/api/plans', {'url': 'https://example.com', 'instructions': 'Find help',
                                      'method': 'live', 'persona_id': person['id']}).json()
        with patch('Backend.app.server.EXECUTOR.submit') as submit:
            result = self.post('/api/runs', {'plan_id': plan['id']})
        self.assertEqual(result.status_code, 422, result.text)
        self.assertIn('keyboard-only', result.text)
        submit.assert_not_called()

    def test_listing_does_not_rewrite_legacy_files(self):
        path = db.safe_file('personas', 'old')
        db.write(path, {'name': 'Legacy', 'technical_level': 'low'})
        before = path.read_bytes()
        person = self.client.get('/api/personas').json()[0]
        self.assertEqual(person['id'], 'old')
        self.assertEqual(path.read_bytes(), before)

    def test_live_snapshot_records_canonical_runtime(self):
        from Backend.app.live import run_live
        config = profile(technical_experience='advanced')
        plan = {'persona': compatibility_record(config), 'instructions': 'Find help',
                'cases': [], 'url': 'https://example.com', 'persona_id': 'visitor',
                'project_id': None, 'max_actions': 1}
        with patch('Backend.app.live.sync_playwright', side_effect=RuntimeError('browser unavailable')):
            run_live('snapshot', plan, Mock())
        snapshot = db.read(db.directory('results') / 'exploration_snapshot' / 'persona.json')
        self.assertEqual(snapshot['runtime_profile'], resolve_persona(config, 'Find help').model_dump())
        self.assertEqual(snapshot['task'], 'Find help')

    def test_screenshot_entrypoint_projects_canonical_profile(self):
        from Backend.agents.persona_agent import evaluate_ux
        image = db.ROOT / 'image.png'
        image.write_bytes(b'test-fixture')
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test'}), \
             patch('Backend.agents.persona_agent.generate_json', return_value={'findings': []}) as request:
            result = evaluate_ux(profile(), 'Review labels', image)
        self.assertEqual(result['persona'], 'Visitor')
        self.assertNotIn('active_calibration_ids', request.call_args.args[0][0])

    def test_canonical_put_replaces_profile_and_preserves_id(self):
        person = self.post('/api/personas', profile(description='Original')).json()
        response = self.client.put('/api/personas/' + person['id'],
                                   json=profile(name='Replacement'), headers=HEADERS)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['id'], person['id'])
        self.assertEqual(response.json()['description'], '')
        self.assertEqual(response.json()['universal_persona']['profile']['name'], 'Replacement')


if __name__ == '__main__':
    unittest.main()
