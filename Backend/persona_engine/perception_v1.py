"""OMNI pilot-v1 persona perception boundary (uncalibrated scenario policy).

This module is pure Python, provider-independent, and does not alter Playwright.
Original observations and element handles must remain on the trusted execution side.
No human-data calibration or psychological accuracy is claimed here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
import hashlib
import json
import math
from typing import Any

TARGET_ACTIONS = frozenset({'click', 'fill', 'select', 'check', 'hover'})
NO_TARGET_ACTIONS = frozenset({'scroll', 'back', 'home', 'wait', 'stop'})

# Candidate budgets are *scenario hypotheses*, not inferred human probabilities.
PROVISIONAL_BUDGETS = {'beginner': 16, 'intermediate': 24, 'advanced': 32}
ATTENTION_OFFSETS = {'focused': -8, 'standard': 0, 'broad': 8}
CONTROL_FIELDS = ('id', 'tag', 'type', 'name', 'disabled', 'checked', 'options',
                  'bounding_box', 'viewport_position', 'style', 'visibility', 'label_metadata')
POLICY_VERSION = 'stage-a-1.1'


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _clip(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def extract_features(observation: dict) -> list[dict]:
    """Derive stable normalized geometry with explicit unknown-quality markers.

    Features are suitable for a future external, validated calibration artifact.
    They must *not* be described as measured human attention.
    """
    viewport = observation.get('viewport') or {}
    width, height = _number(viewport.get('width')), _number(viewport.get('height'))
    valid_viewport = bool(width and height and width > 0 and height > 0)
    output = []
    for control in observation.get('controls', []):
        cid = control.get('id')
        if isinstance(cid, bool) or not isinstance(cid, int):
            continue
        rect = control.get('bounding_box') or {}
        x, y = _number(rect.get('x')), _number(rect.get('y'))
        w, h = _number(rect.get('width')), _number(rect.get('height'))
        flags = []
        normalized = None
        area = None
        if valid_viewport and None not in (x, y, w, h) and w > 0 and h > 0:
            left, top = _clip(x / width), _clip(y / height)
            right, bottom = _clip((x+w) / width), _clip((y+h) / height)
            if right > left and bottom > top:
                normalized = {'left': left, 'top': top, 'right': right, 'bottom': bottom}
                area = (right-left)*(bottom-top)
            else:
                flags.append('outside_viewport')
        else:
            flags.append('missing_or_invalid_geometry')
        label = control.get('name')
        font_value = (control.get('style') or {}).get('font_size')
        font = None
        if isinstance(font_value, str) and font_value.endswith('px'):
            font = _number(float(font_value[:-2])) if _is_number(font_value[:-2]) else None
        if font is None:
            flags.append('unknown_font_size')
        output.append({'id': cid, 'normalized_rect': normalized, 'visible_area_fraction': area,
                       'font_size_px': font, 'label_present': bool(isinstance(label, str) and label.strip()),
                       'disabled': bool(control.get('disabled')), 'quality_flags': flags})
    return output


def _is_number(value: str) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _fingerprint(control: dict) -> str:
    """Cross-step *memory* identity only; never use as a Playwright locator."""
    sample = {'tag': control.get('tag'), 'type': control.get('type'),
              'name': control.get('name'),
              'dom_id': (control.get('label_metadata') or {}).get('dom_id', ''),
              'role': (control.get('label_metadata') or {}).get('role', '')}
    return hashlib.sha256(json.dumps(sample, sort_keys=True, default=str).encode()).hexdigest()


def _view_key(observation: dict) -> str:
    """Cache stable view selection so observing again does not reveal more by chance."""
    sample = {'url': observation.get('url'), 'scroll': observation.get('scroll'),
              'viewport': observation.get('viewport'),
              'controls': [(c.get('id'), _fingerprint(c), c.get('disabled'), c.get('bounding_box'), c.get('style'))
                           for c in observation.get('controls', [])]}
    return hashlib.sha256(json.dumps(sample, sort_keys=True, default=str).encode()).hexdigest()


def _score(feature: dict) -> float:
    """Provisional engineering heuristic; NOT a calibrated attention probability."""
    rect = feature['normalized_rect']
    if rect is None:
        centrality, area = 0.0, 0.0
    else:
        cx, cy = (rect['left']+rect['right']) / 2, (rect['top']+rect['bottom']) / 2
        centrality = 1.0 - _clip(math.hypot(cx-0.5, cy-0.42) / 0.8)
        area = _clip((feature['visible_area_fraction'] or 0.0)*30)
    font = _clip((feature['font_size_px'] or 0) / 24)
    return 0.40*centrality + 0.30*area + 0.20*float(feature['label_present']) + 0.10*font


@dataclass(frozen=True)
class PerceivedStep:
    model_observation: dict
    allowed_targets: frozenset[int]
    provenance: dict
    diagnostics: dict


@dataclass
class PilotPerception:
    """Same code path for every canonical built-in or custom profile."""
    profile: dict
    mode: str = 'provisional_pilot_v1'  # or neutral_passthrough
    _view_cache: dict[str, tuple[int, ...]] = field(default_factory=dict)
    noticed_fingerprints: set[str] = field(default_factory=set)

    def __post_init__(self):
        if self.mode not in ('provisional_pilot_v1', 'neutral_passthrough'):
            raise ValueError('Unsupported perception policy mode')
        self.profile = deepcopy(self.profile)
        level = self.profile.get('technical_experience', 'intermediate')
        focus = (self.profile.get('perception') or {}).get('attention', 'standard')
        if level not in PROVISIONAL_BUDGETS or focus not in ATTENTION_OFFSETS:
            raise ValueError('Persona must be resolved by the universal schema first')

    def parameters(self):
        level = self.profile.get('technical_experience', 'intermediate')
        focus = (self.profile.get('perception') or {}).get('attention', 'standard')
        return {'technical_experience':level, 'attention':focus,
                'candidate_budget':max(8, PROVISIONAL_BUDGETS[level] + ATTENTION_OFFSETS[focus]) if self.mode == 'provisional_pilot_v1' else None,
                'score_weights':{'centrality':0.40, 'area':0.30, 'label_present':0.20, 'font_size':0.10} if self.mode == 'provisional_pilot_v1' else {},
                'centrality_center':[0.5, 0.42], 'distance_scale':0.8, 'area_scale':30, 'font_scale_px':24,
                'flat_text_policy':'blank' if self.mode == 'provisional_pilot_v1' else 'passthrough'}

    def provenance(self):
        data = {'version':POLICY_VERSION, 'mode':self.mode, 'profile':self.profile}
        return {'version':POLICY_VERSION, 'mode':self.mode,
                'policy_key':hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(),
                'parameter_status':'provisional' if self.mode == 'provisional_pilot_v1' else 'unfiltered_baseline',
                'human_calibrated':False, 'active_dataset_ids':[], 'parameters':self.parameters()}

    def perceive(self, observation: dict) -> PerceivedStep:
        controls = observation.get('controls') or []
        raw_by_id = {c['id']: c for c in controls if isinstance(c.get('id'), int)
                     and not isinstance(c.get('id'), bool) and c['id'] >= 0}
        keys = set(raw_by_id)
        if len(keys) != len(controls):
            raise ValueError('Snapshot contains invalid or duplicate control IDs')
        if self.mode == 'neutral_passthrough':
            selected = tuple(c['id'] for c in controls)
            text = observation.get('visible_text', '')
        else:
            view_key = _view_key(observation)
            if view_key not in self._view_cache:
                level = self.profile.get('technical_experience', 'intermediate')
                focus = (self.profile.get('perception') or {}).get('attention', 'standard')
                if level not in PROVISIONAL_BUDGETS or focus not in ATTENTION_OFFSETS:
                    raise ValueError('Persona must be resolved by the universal schema first')
                budget = max(8, PROVISIONAL_BUDGETS[level] + ATTENTION_OFFSETS[focus])
                rank = sorted(extract_features(observation), key=lambda f: (-_score(f), f['id']))
                chosen = {f['id'] for f in rank[:budget]}
                selected = tuple(c['id'] for c in controls if c['id'] in chosen)
                self._view_cache[view_key] = selected
            selected = self._view_cache[view_key]
            # Raw flat text may expose filtered-out control labels. With no
            # text-to-element geometry, fail closed. Future version can add safe spans.
            text = ''
        allowed = frozenset(cid for cid in selected if not raw_by_id[cid].get('disabled'))
        self.noticed_fingerprints.update(_fingerprint(raw_by_id[i]) for i in selected)
        view = sanitize_view({**observation, 'visible_text':text,
                              'controls':[c for c in controls if c['id'] in selected]})
        return PerceivedStep(model_observation=view, allowed_targets=allowed,
              provenance=self.provenance(),
              diagnostics={'observed_controls': len(controls), 'projected_controls': len(selected),
                           'actionable_controls': len(allowed)})


def validate_action(decision: dict, step: PerceivedStep) -> str | None:
    """Independent candidate guard; call before dispatch or journal.execute.

    This supplements, never replaces, existing action_safety.execute_validated.
    """
    if not isinstance(decision, dict):
        return 'blocked: invalid model decision'
    action, target, value = decision.get('action'), decision.get('target'), decision.get('value')
    if not isinstance(action, str) or type(target) is not int:
        return 'blocked: invalid action or non-integer target'
    if action in TARGET_ACTIONS or (action == 'press' and value == 'Enter'):
        if type(target) is not int or target not in step.allowed_targets:
            return 'blocked: target outside persona-permitted current observation'
    elif action == 'press' and value == 'Escape':
        if target != -1:
            return 'blocked: Escape must not target a control'
    elif action in NO_TARGET_ACTIONS:
        if target != -1:
            return 'blocked: non-target action has an unexpected target'
    else:
        return 'blocked: action not allowed by persona execution contract'
    return None


def sanitize_view(view: dict) -> dict:
    """Allowlist nested metadata too; never expose values or internal target state."""
    nested = {'bounding_box':('x','y','width','height'),
              'viewport_position':('center_x','center_y','visible_fraction'),
              'style':('font_size','color','background_color'),
              'visibility':('css_visibility','display','effective_opacity','intersects_viewport','fully_in_viewport'),
              'label_metadata':('dom_id','role','aria_label','aria_labelledby','labelledby_text','associated_labels','placeholder','title')}
    controls = []
    for c in view.get('controls') or []:
        safe = {k:deepcopy(c[k]) for k in CONTROL_FIELDS if k in c and k not in nested and k != 'options'}
        for key, fields in nested.items():
            if isinstance(c.get(key), dict):
                safe[key] = {k:deepcopy(c[key][k]) for k in fields if k in c[key]}
        if isinstance(c.get('options'), list):
            safe['options'] = [{k:deepcopy(o[k]) for k in ('text','value') if k in o} for o in c['options'] if isinstance(o, dict)]
        if c.get('tag') in ('input','textarea'):
            safe['filled'] = bool(c.get('filled', c.get('value')))
        controls.append(safe)
    return {'url':view.get('url'), 'title':view.get('title'),
            'visible_text':view.get('visible_text', ''), 'controls':controls,
            'viewport':{k:v for k,v in (view.get('viewport') or {}).items() if k in ('width','height')},
            'scroll':{k:v for k,v in (view.get('scroll') or {}).items() if k in ('x','y','height')}}


def project_history(history: list[dict], policy_key: str | None = None) -> list[dict]:
    """Provide the LLM with only previously permitted views, not evidence records."""
    projected = []
    for row in history:
        provenance = row.get('perception_policy') or {}
        known = (provenance.get('version') == POLICY_VERSION and
                 (policy_key is None or provenance.get('policy_key') == policy_key))
        before = sanitize_view(row.get('model_before') or {}) if known else sanitize_view({})
        after = sanitize_view(row.get('model_after') or {}) if known else sanitize_view({})
        if known and not row.get('model_after'):
            after = {}  # An unavailable after-sample is not an observed empty page.
        # No raw error strings, selected values, reasons, arbitrary model keys,
        # old unfiltered views, or change flags computed over excluded content.
        decision = row.get('decision') or {}
        action = decision.get('action')
        if not isinstance(action, str) or action not in TARGET_ACTIONS | NO_TARGET_ACTIONS | {'press'}:
            action = 'unavailable'
        result = row.get('result') or 'unavailable'
        if not known:
            result = 'unverified_history'
        elif result not in ('executed', 'agent_stopped', 'outcome_unknown'):
            result = 'blocked: action rejected' if row.get('action_status') == 'blocked' else 'automation_error'
        projected.append({'step': row.get('step'), 'before': before,
                          'journal_version':1 if known and row.get('journal_version') == 1 else None,
                          'after': after, 'decision':{'action':action, 'target':decision.get('target') if known and type(decision.get('target')) is int else -1},
                          'result':result, 'action_status':row.get('action_status') if known else 'unavailable',
                          'automation_error':'Browser action unavailable.' if result == 'automation_error' else None,
                          'observed_change': {k:before[k] != after[k] for k in ('url','visible_text','controls')}
                              if known and row.get('model_after') else {}})
    return projected
