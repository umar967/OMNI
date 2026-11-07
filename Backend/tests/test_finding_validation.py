"""Claim provenance and adversarial prose checks; no live provider calls."""
from copy import deepcopy
from contextlib import ExitStack
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, MagicMock, patch

from Backend.finding_validation import Finding, observations, validate_review, report_claim_view
from Backend.agents.exploration_agent import clean_review, apply_review, review_run
from Backend.agents.local_persona import experience
from Backend.task_outcomes import evaluate_sample, unverified
from Backend.tests.test_task_outcomes import contract, sample
from Backend.app import storage as db


def record(**changes):
    before = {'url':'https://shop.test/form', 'visible_text':'Email\nContinue',
              'controls':[{'id':0, 'name':'Continue', 'tag':'button', 'type':'button', 'disabled':False}]}
    after = {**deepcopy(before), 'visible_text':'Enter a valid email address.'}
    return dict(step=1, journal_version=1, action_status='executed', result='executed',
        decision={'action':'click', 'target':0, 'reason':'Try the form'}, before=before, after=after,
        observed_change={'visible_text':True}, screenshots={}, capture_metadata={}) | changes


def proposal(**changes):
    return dict(category='error_recovery', affected_page='https://shop.test/form',
        observation_ids=['step-1-text-0'], hypothesis='The message may need a concrete correction example.',
        expected_behavior='Offer an example near the relevant field.',
        potential_user_impact='A correction example could help a visitor recover.',
        suggested_improvement='Show an example email format next to the field.') | changes


def review(*proposals):
    return {'findings':list(proposals), 'persona_feedback':{}}


class FindingValidationTests(unittest.TestCase):
    def test_genuine_observable_symptom_has_canonical_contract_and_reproduction(self):
        result = clean_review(review(proposal()), [record()])
        self.assertEqual(len(result['findings']), 1)
        finding = Finding.model_validate(result['findings'][0])
        self.assertEqual(finding.classification, 'ux_hypothesis')
        self.assertEqual(finding.validation_status, 'requires_developer_review')
        self.assertIn('Enter a valid email address.', finding.observed_symptom[0])
        self.assertEqual(finding.reproduction_steps[0]['action'], 'click')
        self.assertEqual(finding.reproduction_steps[0]['control'], 'Continue')
        self.assertEqual({e.phase for e in finding.supporting_evidence}, {'before','after'})
        self.assertFalse(result['review_validation']['semantic_accuracy_proven'])

    def test_correct_quote_cannot_validate_unrelated_conclusion(self):
        raw = {'issue':'The database corrupted every order', 'steps':[1], 'evidence':'Continue',
               'explanation':'Users were frustrated', 'recommendation':'Rebuild the database'}
        result = clean_review(review(raw), [record()])
        self.assertEqual(result['findings'], [])
        self.assertEqual(result['unsupported_claims'][0]['classification'], 'unsupported_assertion')

    def test_model_cannot_supply_verified_symptom_or_status(self):
        for extra in [{'observed_symptom':['Users were confused']}, {'classification':'observed_browser_event'},
                      {'validation_status':'verified'}, {'reproduction_steps':[{'action':'pay'}]}]:
            with self.subTest(extra=extra):
                self.assertEqual(clean_review(review(proposal(**extra)), [record()])['findings'], [])

    def test_fabricated_emotions_and_measurements_are_rejected_in_all_prose_fields(self):
        for field in ('hypothesis','expected_behavior','potential_user_impact','suggested_improvement'):
            for text in ('Users were frustrated.', 'I felt confused.', 'Satisfaction was 98%.',
                         'The task took 12 seconds.', 'The page is WCAG compliant.'):
                with self.subTest(field=field, text=text):
                    result = clean_review(review(proposal(**{field:text})), [record()])
                    self.assertEqual(result['findings'], [])

    def test_explicitly_hypothetical_impact_is_kept_without_claiming_emotion_measurement(self):
        result = clean_review(review(proposal(potential_user_impact='Visitors might feel confused about the next edit.')), [record()])
        self.assertEqual(result['findings'][0]['impact_status'], 'interpretation_not_measurement')

    def test_proposed_completion_feedback_is_not_an_actual_completion_claim(self):
        p = proposal(suggested_improvement='Display clear completion feedback for the configured flow.')
        self.assertEqual(len(clean_review(review(p), [record()])['findings']), 1)
        p['suggested_improvement'] = 'Display that the task was completed.'
        self.assertEqual(clean_review(review(p), [record()])['findings'], [])

    def test_unsupported_causes_rejected_even_with_valid_observation_id(self):
        for text in ('This caused frustration.', 'The bug is due to a race condition.',
                     'The backend is broken because the database lost the value.'):
            with self.subTest(text=text):
                result = clean_review(review(proposal(hypothesis=text)), [record()])
                self.assertEqual(result['findings'], [])
                self.assertTrue(result['unsupported_claims'])

    def test_wrong_page_control_and_category_are_rejected(self):
        for change in [{'affected_page':'https://elsewhere.test/'}, {'affected_control_id':999},
                       {'category':'navigation_clarity'}, {'observation_ids':['step-99-text-0']},
                       {'observation_ids':['step-1-text-0','step-1-text-0']}]:
            with self.subTest(change=change):
                self.assertEqual(clean_review(review(proposal(**change)), [record()])['findings'], [])

    def test_empty_control_name_is_a_narrow_observation_not_accessibility_compliance(self):
        row = record()
        row['after']['controls'][0]['name'] = ''
        p = proposal(category='control_labelling', affected_control_id=0,
                     observation_ids=['step-1-after-control-0'], hypothesis='An explicit label could clarify the action.')
        f = clean_review(review(p), [row])['findings'][0]
        self.assertIn('empty DOM-derived name', f['observed_symptom'][0])
        self.assertIn('not a full accessible-name audit', f['observed_symptom'][0])

    def test_no_change_uses_observations_not_model_supplied_flags(self):
        row = record(observed_change={'visible_text':False})
        facts, _ = observations([row])
        self.assertIn('step-1-text-0', {f['id'] for f in facts})
        self.assertNotIn('step-1-unchanged', {f['id'] for f in facts})
        row['after'] = deepcopy(row['before'])
        row['observed_change'] = {'url':True}
        facts, _ = observations([row])
        self.assertIn('step-1-unchanged', {f['id'] for f in facts})
        result = clean_review(review(proposal(category='feedback_clarity', observation_ids=['step-1-unchanged'])), [row])
        self.assertIn('Delayed responses', result['findings'][0]['observed_symptom'][0])

    def test_browser_failure_and_safety_block_cannot_support_website_defect(self):
        for state, result in [('failed','automation_error'), ('blocked','blocked: payment'),
                              ('outcome_unknown','outcome_unknown'), ('attempted','attempted')]:
            with self.subTest(state=state):
                out = clean_review(review(proposal()), [record(action_status=state, result=result)])
                self.assertEqual(out['findings'], [])
                self.assertTrue(out['execution_limitations'])
                self.assertEqual(out['execution_limitations'][0]['scope'], 'execution_limitation')

    def test_partial_history_and_duplicate_steps_are_not_support(self):
        for rows in [[record(after={})], [record(), record()], [record(step=True)]]:
            with self.subTest(rows=rows):
                self.assertEqual(clean_review(review(proposal()), rows)['findings'], [])

    def test_screenshot_reference_alone_is_insufficient_even_when_file_exists(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path/'evidence').mkdir()
            (path/'evidence/step-1-after.png').write_bytes(b'fixture')
            row = record(screenshots={'after':'step-1-after.png'})
            p = proposal(observation_ids=['step-1-after.png'])
            self.assertEqual(clean_review(review(p), [row], folder=path)['findings'], [])

    def test_missing_capture_does_not_suppress_dom_grounded_recommendation(self):
        with tempfile.TemporaryDirectory() as folder:
            out = clean_review(review(proposal()), [record()], folder=Path(folder))
            self.assertEqual(len(out['findings']), 1)
            images = [r for r in out['findings'][0]['supporting_evidence'] if r['source']=='screenshot']
            self.assertTrue(all(r['availability']=='missing' for r in images))
            self.assertTrue(any('screenshot unavailable' in s for s in out['findings'][0]['limitations']))

    def test_capture_page_and_hash_are_checked_without_claiming_pixel_semantics(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path/'evidence').mkdir()
            capture = path/'evidence/step-1-after.png'
            capture.write_bytes(b'fixture-image')
            row = record(screenshots={'after':capture.name}, capture_metadata={'after':{
                'url':'https://shop.test/form', 'sha256':hashlib.sha256(capture.read_bytes()).hexdigest()}})
            def availability():
                f = clean_review(review(proposal()), [row], folder=path)['findings'][0]
                return next(r['availability'] for r in f['supporting_evidence'] if r['source']=='screenshot' and r['phase']=='after')
            self.assertEqual(availability(), 'available')
            row['capture_metadata']['after']['url'] = 'https://other.test/'
            self.assertEqual(availability(), 'mismatched')
            row['capture_metadata']['after']['url'] = 'https://shop.test/form'
            capture.write_bytes(b'replaced-image')
            self.assertEqual(availability(), 'mismatched')

    def test_model_outcome_claim_is_rejected_when_verifier_contradicts_it(self):
        verification = evaluate_sample(contract(), sample(rows=[{'visible':True,'name':'Other','quantity':'1'}]), step=1, final=True).model_dump()
        raw = review(proposal(hypothesis='The user successfully completed the task.'))
        raw.update(task_outcome='verified_complete', verified_observations=[{'statement':'Task succeeded'}])
        cleaned = clean_review(raw, [record()], verification)
        report = {'task_outcome':'verified_incomplete', 'outcome_verification':verification, 'execution_status':'partial'}
        apply_review(report, cleaned)
        self.assertEqual(report['task_outcome'], 'verified_incomplete')
        self.assertEqual(report['findings'], [])
        facts = [f for f in report['verified_observations'] if f['classification']=='independently_verified_task_outcome']
        self.assertEqual(len(facts), 1)
        self.assertIn('verified_incomplete', facts[0]['statement'])

    def test_endpoint_mismatch_can_ground_investigation_but_not_a_cause(self):
        verification = evaluate_sample(contract(), sample(rows=[{'visible':True,'name':'Other','quantity':'1'}]), step=1, final=True).model_dump()
        p = proposal(category='task_expectation', affected_page='https://shop.test/cart',
                     observation_ids=['endpoint-' + verification['evidence'][0]['id']],
                     hypothesis='The item mapping may need investigation.')
        f = clean_review(review(p), [record()], verification)['findings'][0]
        self.assertEqual(f['supporting_evidence'][0]['source'], 'outcome_verification')
        self.assertEqual(f['classification'], 'ux_hypothesis')

    def test_ai_only_or_inconsistent_endpoint_status_is_not_an_independent_fact(self):
        verification = evaluate_sample(contract(), sample(), step=1, final=True).model_dump()
        for changed in [{**verification, 'verifier':'model'}, {k:v for k,v in verification.items() if k!='verifier'},
                        {**verification,'task_outcome':'verified_incomplete'}, unverified().model_dump()]:
            with self.subTest(changed=changed):
                facts, _ = observations([record()], changed)
                self.assertFalse(any(f['classification']=='independently_verified_task_outcome' for f in facts))

    def test_completion_and_emotion_cannot_hide_in_feedback_summary_or_flow_prose(self):
        raw = review()
        raw['persona_feedback'] = {'overall_impression':{'comment':'I completed the task and felt satisfied.', 'steps':[1], 'evidence':'Continue'}}
        raw['experience_summary'] = {'comment':'Users were frustrated. '*80, 'steps':[1], 'evidence':'Continue'}
        raw['flow_assessments'] = [{'status':'completed', 'explanation':'The purchase succeeded'}]
        result = clean_review(raw, [record()])
        self.assertIsNone(result['experience_summary'])
        self.assertIsNone(result['persona_feedback']['overall_impression'])
        self.assertEqual(result['flow_assessments'][0]['status'], 'attempted')
        self.assertNotIn('purchase succeeded', result['flow_assessments'][0]['explanation'])

    def test_all_feedback_steps_must_match_quote(self):
        second = record(step=2)
        second['before']['controls'][0]['name'] = 'Unrelated'
        second['before']['visible_text'] = 'Unrelated'
        second['after']['visible_text'] = 'Unrelated'
        second['after']['controls'][0]['name'] = 'Unrelated'
        raw = review()
        raw['persona_feedback'] = {'overall_impression':{'comment':'This could help navigation.', 'steps':[1,2], 'evidence':'Continue'}}
        self.assertIsNone(clean_review(raw, [record(),second])['persona_feedback']['overall_impression'])

    def test_clean_interface_does_not_force_findings_or_make_review_unavailable(self):
        row = record()
        row['after']['visible_text'] = 'Welcome'
        cleaned = clean_review(review(), [row])
        report = {'actions_recorded':1}
        apply_review(report, cleaned)
        self.assertEqual(report['findings'], [])
        self.assertEqual(report['review_status'], 'completed')
        self.assertTrue(report['verified_observations'])

    def test_reproduction_comes_from_history_and_omits_entered_values(self):
        first = record(decision={'action':'fill','target':0,'value':'private-entered-value'})
        second = record(step=2)
        f = clean_review(review(proposal(observation_ids=['step-2-text-0'])), [first,second])['findings'][0]
        self.assertEqual([s['step'] for s in f['reproduction_steps']], [1,2])
        self.assertNotIn('private-entered-value', json.dumps(f))
        self.assertTrue(f['reproduction_steps'][0]['input_omitted'])

    def test_legacy_reports_are_marked_unverified_without_rewriting(self):
        raw = {'findings':[{'issue':'Users were frustrated', 'evidence':'Continue'}], 'experience_summary':{'comment':'It worked'}}
        original = deepcopy(raw)
        view = report_claim_view(raw, [record()])
        self.assertEqual(view['findings'][0]['validation_status'], 'legacy_unverified')
        self.assertEqual(raw, original)

    def test_saved_claims_are_rechecked_against_changed_history_and_missing_files(self):
        report = clean_review(review(proposal()), [record()])
        changed = record()
        changed['after']['visible_text'] = changed['before']['visible_text']
        view = report_claim_view(report, [changed])
        self.assertEqual(view['findings'], [])
        self.assertTrue(view['unsupported_claims'])

    def test_reports_api_exposes_contract_and_legacy_classification(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(db, 'ROOT', Path(folder)):
            run = Path(folder)/'results/exploration_claims'
            db.write(run/'history.json', [record()])
            db.write(run/'report.json', clean_review(review(proposal()), [record()]))
            self.assertEqual(db.reports()[0]['findings'][0]['version'], '1.0')
            db.write(run/'report.json', {'findings':[{'issue':'False claim'}]})
            self.assertEqual(db.reports()[0]['findings'][0]['classification'], 'unsupported_assertion')

    def test_gemini_and_ollama_request_same_finding_contract(self):
        raw = review(proposal())
        local_request = Mock(return_value=raw)
        local = experience({'name':'Visitor'}, [record()], local_request)
        with patch.dict('os.environ', {'OMNI_MODEL_PROVIDER':'gemini'}), patch('Backend.agents.exploration_agent.request_json', return_value=raw) as remote_request:
            remote = review_run({'name':'Visitor'}, [record()])
        self.assertEqual(local_request.call_args.args[1], remote_request.call_args.args[1])
        self.assertEqual(clean_review(local,[record()]), clean_review(remote,[record()]))

    def test_live_and_cli_save_same_validated_claims_and_reject_model_success(self):
        from Backend import explore_website as cli
        from Backend.app import live
        for runner in ('live','cli'):
            with self.subTest(runner=runner), tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                root = Path(folder)
                module = live if runner == 'live' else cli
                stack.enter_context(patch.object(db, 'ROOT', root))
                stack.enter_context(patch.object(cli, 'ROOT', root))
                db.write(root/'personas/first_time_user.json', {'name':'Visitor'})
                db.write(root/'flows.json', {'flows':[]})
                stack.enter_context(patch.object(module, 'sync_playwright', MagicMock()))
                row = record()
                stack.enter_context(patch.object(module, 'observe', side_effect=[(row['before'],{}),(row['after'],{})]))
                stack.enter_context(patch.object(module, 'capture_step', side_effect=RuntimeError('No screenshot')))
                def executor(*args, on_dispatch):
                    on_dispatch()
                    return 'executed'
                stack.enter_context(patch.object(module, 'execute', executor))
                prefix = 'Backend.app.live' if runner == 'live' else 'Backend.agents.exploration_agent'
                stack.enter_context(patch(prefix + '.explore_next', return_value={'action':'click','target':0}))
                raw = review(proposal(), proposal(hypothesis='The task was completed.'))
                raw['task_outcome'] = 'verified_complete'
                stack.enter_context(patch(prefix + '.review_run', return_value=raw))
                if runner == 'live':
                    live.run_live('claims', {'persona':{'name':'Visitor'},'instructions':'Inspect the form', 'cases':[],
                        'url':row['before']['url'], 'project_id':None,'persona_id':'visitor','max_actions':1}, Mock())
                else:
                    stack.enter_context(patch('sys.argv', ['explore','--url',row['before']['url'], '--max-actions','1','--flows',str(root/'flows.json')]))
                    cli.main()
                report = db.read(next((root/'results').glob('*/report.json')))
                self.assertEqual(report['finding_validation_version'], '1.0')
                self.assertEqual(report['task_outcome'], 'unknown')
                self.assertEqual(report['review_status'], 'partial')
                self.assertEqual(len(report['findings']), 1)
                self.assertEqual(report['findings'][0]['classification'], 'ux_hypothesis')
                self.assertEqual(report['unsupported_claims'][0]['classification'], 'unsupported_assertion')
