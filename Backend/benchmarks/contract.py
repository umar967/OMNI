"""Evaluator-only manifest; never pass this object to a decision provider."""
from typing import Literal
from pydantic import Field, model_validator
from Backend.persona_engine.schema import Contract, UniversalPersona
from Backend.task_outcomes import TaskContract


class TargetAnnotation(Contract):
    target_id: str
    selector: str
    critical: bool = True


class BenchmarkCase(Contract):
    interface_id: str
    task_id: str
    family_id: str
    split: Literal['development', 'validation', 'test']
    fixture: Literal['clean', 'dense', 'below_fold', 'disabled', 'error_message']
    task: TaskContract
    targets: list[TargetAnnotation] = Field(min_length=1)

    @model_validator(mode='after')
    def unique_targets(self):
        if len({t.target_id for t in self.targets}) != len(self.targets):
            raise ValueError('Target IDs must be unique within a task.')
        return self


class BenchmarkSuite(Contract):
    version: Literal['retention-1'] = 'retention-1'
    suite_id: str
    policy_version: str
    modes: list[Literal['neutral_passthrough','provisional_pilot_v1']] = Field(min_length=1)
    personas: dict[str, UniversalPersona] = Field(min_length=1)
    cases: list[BenchmarkCase] = Field(min_length=1)
    max_actions: int = Field(default=8, ge=1, le=20)
    purpose: Literal['engineering_regression', 'frozen_holdout'] = 'engineering_regression'

    @model_validator(mode='after')
    def split_isolation(self):
        groups, identities = {}, set()
        for case in self.cases:
            identity = (case.interface_id, case.task_id)
            if identity in identities:
                raise ValueError('Duplicate interface/task case.')
            identities.add(identity)
            for key in ('family:' + case.family_id, 'interface:' + case.interface_id,
                        'fixture:' + case.fixture):
                if key in groups and groups[key] != case.split:
                    raise ValueError('Interface families and fixture variants cannot cross evaluation splits.')
                groups[key] = case.split
        return self
