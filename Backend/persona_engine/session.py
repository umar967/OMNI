"""Shared runner integration; full evidence stays outside the model boundary."""
from copy import deepcopy
import os
from pathlib import Path
from dotenv import load_dotenv

from .perception_v1 import PilotPerception, project_history, validate_action

DEFAULT_MODE = 'neutral_passthrough'


class PerceptionSession:
    def __init__(self, runtime, mode=None):
        runtime.require_supported()
        if mode is None:
            load_dotenv(Path(__file__).resolve().parents[1] / '.env')
        self.policy = PilotPerception(runtime.persona.profile.model_dump(),
                                      mode if mode is not None else os.getenv('OMNI_PERSONA_POLICY', DEFAULT_MODE))
        runtime.engine.policy_mode = self.policy.mode
        self.provenance = self.policy.provenance()

    def perceive(self, observation):
        return self.policy.perceive(observation)

    def history(self, history):
        return project_history(history, self.provenance['policy_key'])

    def decide(self, decide, persona, perceived, history):
        # Protect the guard and journal snapshot even if a provider adapter mutates
        # its arguments. The original browser observation is never passed here.
        return decide(persona, deepcopy(perceived.model_observation), self.history(history))

    def record_before(self, journal, row, perceived):
        journal.update(row, model_before=deepcopy(perceived.model_observation),
                       perception_policy=deepcopy(perceived.provenance),
                       perception_diagnostics=deepcopy(perceived.diagnostics),
                       permitted_target_ids=sorted(perceived.allowed_targets))

    def execute(self, journal, row, perceived, executor, page, handles, home):
        problem = validate_action(row['decision'], perceived)
        if not problem and row['decision']['action'] == 'scan':
            if self.policy.scan(perceived):
                journal.update(row, result='perception_scanned', action_status='executed',
                               action_kind='perception', dispatch_state='not_dispatched',
                               scan_pass=perceived.scan_pass+1)
                return 'perception_scanned'
            problem = 'blocked: scanning unavailable or exhausted for this profile/view'
        if problem:
            journal.update(row, result=problem, action_status='blocked', dispatch_state='not_dispatched',
                           perception_rejection=problem)
            return problem
        return journal.execute(row, executor, page, handles, home)

    def record_after(self, journal, row):
        after = self.perceive(row['after'])
        journal.update(row, model_after=deepcopy(after.model_observation),
                       after_perception_diagnostics=deepcopy(after.diagnostics))

    def report(self, history):
        return policy_report(self.provenance, history)


def policy_report(provenance, history):
    if not provenance or not provenance.get('policy_key'):
        return {'mode':'legacy_unrecorded', 'parameter_status':'unrecorded', 'parameters':{},
                'human_calibrated':False, 'active_dataset_ids':[], 'recorded_decisions':[],
                'limitations':['Historical report: no perception boundary or parameters were recorded.']}
    steps = [{'step':r['step'], 'mode':r.get('perception_policy', {}).get('mode', 'legacy_unrecorded'),
                  **r.get('perception_diagnostics', {}), 'rejected':bool(r.get('perception_rejection'))}
                 for r in history]
    return {**deepcopy(provenance), 'default_mode':DEFAULT_MODE,
                'human_calibrated':False, 'active_dataset_ids':[],
                'recorded_decisions':steps,
                'policy_rejections':sum(s['rejected'] for s in steps),
                'mixed_policy_history':any(r.get('perception_policy', {}).get('policy_key') != provenance['policy_key'] for r in history),
                'review_evidence_scope':'Persona-permitted projections; full evidence used only by deterministic validation.',
                'limitations':['Scenario budgets and geometry/label ranking are engineering hypotheses, not measured human attention.',
                    'Geometry-linked text is bounded and conservatively filtered; partial, sensitive or ambiguous associations may be withheld.',
                    'Scanning is explicit and provisional; configured pass and run limits can leave controls undiscovered.',
                    'Navigation, recovery, familiarity and accessibility simulation are not activated by this policy.',
                    'No active human calibration artifacts or empirically validated expertise-group differences.']}
