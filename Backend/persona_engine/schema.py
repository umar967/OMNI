"""Single source of truth for presets, API profiles, and a future form builder."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Status = Literal['calibrated', 'research-informed', 'provisional']


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_default=True, allow_inf_nan=False)


class Viewport(Contract):
    width: int = Field(default=1366, ge=320, le=7680, strict=True)
    height: int = Field(default=768, ge=240, le=4320, strict=True)


class Environment(Contract):
    device: Literal['desktop', 'tablet', 'mobile'] = 'desktop'
    viewport: Viewport = Field(default_factory=Viewport)
    input_method: Literal['mouse_keyboard', 'keyboard_only', 'touch'] = 'mouse_keyboard'

    @model_validator(mode='after')
    def compatible_input(self):
        if self.device in ('tablet', 'mobile') and self.input_method != 'touch':
            raise ValueError('Mobile/tablet profiles require touch input in schema v1.')
        if self.device == 'desktop' and self.input_method == 'touch':
            raise ValueError('Desktop touch input is not modeled in schema v1; use mouse_keyboard or keyboard_only.')
        return self


class Accessibility(Contract):
    screen_reader_required: bool = False
    reduced_motion_required: bool = False
    visual_requirements: list[Literal['large_text', 'high_contrast', 'non_color_cues']] = Field(default_factory=list)
    notes: str = Field(default='', max_length=2000)


class Perception(Contract):
    attention: Literal['standard', 'focused', 'broad'] = 'standard'
    label_preference: Literal['neutral', 'explicit'] = 'neutral'
    text_budget: int = Field(default=80, ge=0, le=256, strict=True,
                             description='Provisional maximum text fragments per scan window; zero withholds text.')
    scanning: Literal['progressive', 'disabled'] = 'progressive'
    max_scan_passes: int = Field(default=3, ge=0, le=16, strict=True,
                                description='Provisional additional scan passes per observed layout, bounded by run action limit.')


class Navigation(Contract):
    strategy: Literal['neutral', 'search_first', 'browse_first'] = 'neutral'
    preferred_actions: list[Literal['click', 'fill', 'select', 'check', 'hover', 'scroll', 'back']] = Field(default_factory=list, max_length=7)
    notes: list[Text] = Field(default_factory=list, max_length=30)


class Recovery(Contract):
    approach: Literal['standard', 'cautious', 'persistent'] = 'standard'
    retry_limit: int | None = Field(default=None, ge=0, le=10, strict=True,
                                   description='Requested policy, inactive in Milestone 3; null means unspecified.')


class TaskContext(Contract):
    default_goal: Text | None = None
    domain: str = Field(default='', max_length=100)
    criteria: list[Text] = Field(default_factory=lambda: ['Clarity of labels and feedback'], min_length=1, max_length=30)


class Profile(Contract):
    name: ShortText
    description: str = Field(default='', max_length=2000)
    technical_experience: Literal['beginner', 'intermediate', 'advanced'] = 'intermediate'
    website_familiarity: Literal['unspecified', 'first_visit', 'occasional', 'frequent'] = 'unspecified'
    environment: Environment = Field(default_factory=Environment)
    accessibility: Accessibility = Field(default_factory=Accessibility)
    perception: Perception = Field(default_factory=Perception)
    navigation: Navigation = Field(default_factory=Navigation)
    recovery: Recovery = Field(default_factory=Recovery)
    task_context: TaskContext = Field(default_factory=TaskContext)


class Evaluation(Contract):
    split: Text
    metrics: dict[ShortText, float] = Field(min_length=1)
    report_source: Text
    leakage_controls: Text


class CalibrationArtifact(Contract):
    """Evidence declaration, not independent verification of a calibration claim."""
    artifact_id: ShortText
    dataset: ShortText
    dataset_version: ShortText
    source: Text
    license: Text
    fitting_method: Text
    parameter_paths: list[Text] = Field(min_length=1)
    status: Status = 'provisional'
    fit_split: Text | None = None
    evaluation: Evaluation | None = None
    artifact_sha256: Annotated[str, StringConstraints(pattern=r'^[a-f0-9]{64}$')] | None = None
    limitations: list[Text] = Field(default_factory=list)

    @model_validator(mode='after')
    def evidence_required(self):
        if self.status == 'calibrated':
            if not self.fit_split or not self.evaluation or not self.artifact_sha256:
                raise ValueError('Calibrated artifacts require fit_split, held-out evaluation, and artifact_sha256.')
            if self.fit_split == self.evaluation.split:
                raise ValueError('Evaluation split must differ from the fitting split.')
        return self


class Provenance(Contract):
    origin: Literal['built_in', 'custom', 'legacy'] = 'custom'
    source: Text = 'User-defined profile'
    notes: list[Text] = Field(default_factory=list)


class UniversalPersona(Contract):
    schema_version: Literal['1.0'] = '1.0'
    profile: Profile
    calibration: list[CalibrationArtifact] = Field(default_factory=list, max_length=50)
    provenance: Provenance = Field(default_factory=Provenance)

    @model_validator(mode='after')
    def unique_artifacts(self):
        ids = [a.artifact_id for a in self.calibration]
        if len(ids) != len(set(ids)):
            raise ValueError('Calibration artifact IDs must be unique.')
        # Every reference must address an actual profile leaf, not arbitrary text.
        data = self.model_dump()['profile']
        for artifact in self.calibration:
            for path in artifact.parameter_paths:
                parts = path.split('.')
                value = data
                if parts[0] != 'profile':
                    raise ValueError('Calibration parameter paths must start with profile.')
                for part in parts[1:]:
                    if not isinstance(value, dict) or part not in value:
                        raise ValueError(f'Unknown calibration parameter path: {path}')
                    value = value[part]
                if isinstance(value, dict):
                    raise ValueError(f'Calibration must reference a profile field: {path}')
        return self
