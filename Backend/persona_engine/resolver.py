"""Normalize all persona sources without interpreting demographics as abilities."""
from copy import deepcopy
from typing import Literal

from pydantic import Field

from .schema import Contract, UniversalPersona

SKILLS = {'low': 'beginner', 'basic': 'beginner', 'beginner': 'beginner',
          'moderate': 'intermediate', 'intermediate': 'intermediate',
          'high': 'advanced', 'advanced': 'advanced', 'expert': 'advanced'}


def migrate_legacy(data):
    """Pure migration; historical files and unsupported legacy extras stay untouched."""
    skill = data.get('technical_skill', data.get('technical_level', 'moderate'))
    familiarity = data.get('website_familiarity', 'unspecified')
    if familiarity == 'Has never used this website':
        familiarity = 'first_visit'
    notes = []
    if familiarity not in ('unspecified', 'first_visit', 'occasional', 'frequent'):
        notes.append(f'Legacy familiarity retained as text: {familiarity}')
        familiarity = 'unspecified'
    return UniversalPersona.model_validate({
        'profile': {'name': data.get('name'), 'description': data.get('description', ''),
                    'technical_experience': SKILLS.get(skill, skill),
                    'website_familiarity': familiarity,
                    'navigation': {'notes': data.get('behavior_preferences', [])},
                    'task_context': {'default_goal': data.get('goal'),
                                     'criteria': data.get('criteria', ['Clarity of labels and feedback'])}},
        'provenance': {'origin': 'legacy', 'source': 'Legacy OMNI persona', 'notes': notes}})


class CapabilityIssue(Contract):
    path: str
    message: str


class EngineParameters(Contract):
    version: Literal['foundation-1'] = 'foundation-1'
    policy_mode: Literal['legacy_passthrough'] = 'legacy_passthrough'
    parameter_status: Literal['provisional'] = 'provisional'
    behavioral_simulation_enabled: Literal[False] = False
    # No client-supplied artifact is trusted or activated by this foundation.
    active_calibration_ids: list[str] = Field(default_factory=list, max_length=0)


class RuntimeProfile(Contract):
    persona: UniversalPersona
    task: str | None = None
    engine: EngineParameters = Field(default_factory=EngineParameters)
    unsupported_capabilities: list[CapabilityIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def require_supported(self):
        if self.unsupported_capabilities:
            raise ValueError('; '.join(f'{x.path}: {x.message}' for x in self.unsupported_capabilities))
        return self


def resolve_persona(data, task=None):
    if isinstance(data, UniversalPersona):
        persona = UniversalPersona.model_validate(data.model_dump())
    elif 'universal_persona' in data:
        persona = UniversalPersona.model_validate(data['universal_persona'])
    elif 'schema_version' in data or 'profile' in data:
        persona = UniversalPersona.model_validate(data)
    else:
        persona = migrate_legacy(data)
    profile = persona.profile
    issues = []
    def unsupported(path, message):
        issues.append(CapabilityIssue(path=path, message=message))
    env = profile.environment
    if env.device != 'desktop':
        unsupported('profile.environment.device', 'The current runner supports desktop only; device emulation is not implemented.')
    if env.input_method != 'mouse_keyboard':
        unsupported('profile.environment.input_method', 'The current runner requires mouse_keyboard; touch and keyboard-only execution are not implemented.')
    if env.viewport.width != 1366 or env.viewport.height != 768:
        unsupported('profile.environment.viewport', 'The current live runner uses 1366x768; configurable viewports are not implemented.')
    access = profile.accessibility
    if access.screen_reader_required:
        unsupported('profile.accessibility.screen_reader_required', 'Screen-reader execution is not implemented.')
    if access.reduced_motion_required:
        unsupported('profile.accessibility.reduced_motion_required', 'Reduced-motion emulation is not implemented.')
    if access.visual_requirements:
        unsupported('profile.accessibility.visual_requirements', 'Visual requirements can be recorded but are not enforced by the current runner.')
    if task is not None and (not isinstance(task, str) or not task.strip() or len(task) > 10000):
        raise ValueError('Task override must be nonblank text of at most 10000 characters.')
    return RuntimeProfile(persona=persona, task=task.strip() if task else profile.task_context.default_goal,
                          unsupported_capabilities=issues,
                          warnings=['Attention, navigation and recovery settings are descriptive only in Milestone 3.',
                                    'Calibration references are declarations, not verified or active human calibration.'])


def compatibility_record(data, item_id=None):
    """Flat fields keep the current UI/agents working; canonical data is authoritative."""
    runtime = resolve_persona(data)
    p = runtime.persona.profile
    legacy = deepcopy(data) if isinstance(data, dict) and 'profile' not in data else {}
    legacy.update(name=p.name, description=p.description,
                  technical_skill={'beginner': 'basic', 'intermediate': 'moderate', 'advanced': 'advanced'}[p.technical_experience],
                  goal=p.task_context.default_goal or 'Explore the website', criteria=p.task_context.criteria,
                  universal_persona=runtime.persona.model_dump(),
                  persona_validation={'runtime_supported': not runtime.unsupported_capabilities,
                                      'unsupported_capabilities': [i.model_dump() for i in runtime.unsupported_capabilities],
                                      'warnings': runtime.warnings})
    if item_id is not None:
        legacy['id'] = item_id
    return legacy


def agent_persona(data, task=None):
    """Legacy prompt projection; internal contracts must not activate policies by prompt."""
    runtime = resolve_persona(data, task)
    result = compatibility_record(data)
    result.pop('universal_persona', None)
    result.pop('persona_validation', None)
    result.pop('runtime_profile', None)
    if runtime.task:
        result['task'] = runtime.task
    result.setdefault('behavior_preferences', runtime.persona.profile.navigation.notes)
    return result
