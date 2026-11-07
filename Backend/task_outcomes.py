"""Deterministic browser endpoint checks. Never consume model decisions or claims."""
from datetime import datetime, timezone
import re
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Outcome = Literal['verified_complete', 'verified_incomplete', 'unknown', 'unsupported']
ExecutionStatus = Literal['finished', 'partial', 'failed', 'cancelled']
ReviewStatus = Literal['completed', 'partial', 'unavailable']


class Endpoint(BaseModel):
    model_config = ConfigDict(extra='forbid')
    strategy: Literal['product_listing', 'product_search', 'cart_product']
    expected_url: Text
    container_selector: Text
    ready_selector: Text
    item_selector: Text
    name_selector: Text
    product_name: Text | None = None
    query_selector: Text | None = None
    query_value: Text | None = None
    quantity_selector: Text | None = None
    expected_quantity: Literal[1] = 1
    empty_selector: Text | None = None
    complete_collection: bool = False
    only_requested_product: bool = True

    @field_validator('expected_url')
    @classmethod
    def http_url(cls, value):
        url = urlsplit(value)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
            raise ValueError('Expected endpoint must be an HTTP(S) URL without credentials.')
        return value

    @model_validator(mode='after')
    def strategy_fields(self):
        if self.strategy in ('product_search', 'cart_product') and not self.product_name:
            raise ValueError('Search/cart verification requires an exact product_name.')
        if self.strategy == 'product_search' and not (self.query_selector and self.query_value):
            raise ValueError('Search verification requires query_selector and query_value.')
        if self.strategy == 'cart_product' and not self.quantity_selector:
            raise ValueError('Cart verification requires quantity_selector scoped to each item.')
        return self


class TaskContract(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal['1.0'] = '1.0'
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
    endpoint: Endpoint | None = None
    limitations: list[Text] = Field(default_factory=list)


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    verifier: Literal['dom-endpoint-v1'] = 'dom-endpoint-v1'
    task_outcome: Outcome = 'unknown'
    reason: str
    evidence: list[dict] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


LIMITATIONS = [
    'Verifies only configured observable DOM conditions at the sampled time, not general task correctness.',
    'Selectors and readiness/completeness declarations are supplied by the developer, not inferred or validated by the model.',
    'A matching endpoint does not prove causality, persistence, backend correctness, or a human experience.',
]


def unverified(reason='No supported endpoint was configured.', *, unsupported=False):
    return VerificationResult(task_outcome='unsupported' if unsupported else 'unknown',
                              reason=reason, limitations=LIMITATIONS.copy())


# One synchronous DOM read prevents mixing names/quantities from different page states.
# CSS selectors only; no executable expressions supplied by clients.
SAMPLE = r"""c => {
    const visible = el => {
        if (!el) return false;
        const r = el.getBoundingClientRect(), s = getComputedStyle(el);
        if (!r.width || !r.height || s.visibility !== 'visible' || s.display === 'none') return false;
        for (let n = el; n; n = n.parentElement) if (Number(getComputedStyle(n).opacity) === 0) return false;
        return true;
    };
    const single = (root, selector) => {
        const nodes = [...root.querySelectorAll(selector)];
        return nodes.length === 1 && visible(nodes[0]) ? nodes[0] : null;
    };
    const text = el => el && String(el.value === undefined ? el.innerText : el.value).trim();
    const containers = [...document.querySelectorAll(c.container_selector)].filter(visible);
    const root = containers.length === 1 ? containers[0] : null;
    const ready = single(document, c.ready_selector);
    const busy = root && (root.matches('[aria-busy="true"]') || root.querySelector('[aria-busy="true"]'));
    const nodes = root ? [...root.querySelectorAll(c.item_selector)] : [];
    const rows = nodes.slice(0, 200).map(el => {
        const name = single(el, c.name_selector);
        const quantity = c.quantity_selector ? single(el, c.quantity_selector) : null;
        return {visible: visible(el), name: text(name), quantity: text(quantity)};
    });
    const query = c.query_selector ? single(document, c.query_selector) : null;
    return {url: location.href, container: !!root, ready: !!ready && !busy,
        rows, truncated: nodes.length > 200, query: text(query),
        empty: !!(root && c.empty_selector && single(root, c.empty_selector))};
}"""


def verify(page, contract: TaskContract, *, step=None, final=False):
    if contract.endpoint is None:
        return unverified()
    endpoint = contract.endpoint
    try:
        sample = page.evaluate(SAMPLE, endpoint.model_dump())
        return evaluate_sample(contract, sample, step=step, final=final)
    except Exception:
        # Invalid CSS, detached/closed pages and timeouts are not negative evidence.
        return unverified('Endpoint inspection was unavailable; no failure expectation was established.')


def evaluate_sample(contract, sample, *, step=None, final=False):
    """Pure evaluator over verifier-owned samples; never called with LLM output."""
    c = contract.endpoint
    if c is None:
        return unverified()
    evidence = {'id': uuid4().hex, 'at': datetime.now(timezone.utc).isoformat(),
                'step': step, 'phase': 'endpoint_inspection', 'final': final,
                'conditions': c.model_dump(), 'observed': sample}
    result = VerificationResult(reason='The configured endpoint could not be established.',
                                evidence=[evidence], limitations=LIMITATIONS + contract.limitations)
    if sample['url'].split('#')[0] != c.expected_url.split('#')[0]:
        result.reason = 'The intended endpoint URL was not observed.'
        return result
    if not sample['container'] or not sample['ready'] or sample['truncated']:
        result.reason = 'The endpoint was missing, ambiguous, busy, or incompletely inspected.'
        return result
    rows = sample['rows']
    if any(not r['visible'] or not r['name'] for r in rows):
        result.reason = 'One or more item rows could not be inspected unambiguously.'
        return result
    normalize = lambda value: ' '.join(value.split())
    matched = [r for r in rows if c.product_name and normalize(r['name']) == normalize(c.product_name)]
    if c.strategy == 'product_listing':
        success = bool(rows)
    elif c.strategy == 'product_search':
        if sample['query'] is None:
            result.reason = 'The search query could not be inspected.'
            return result
        success = normalize(sample['query']) == normalize(c.query_value) and bool(matched)
    else:
        if not c.complete_collection:
            result.reason = 'Exact cart quantity requires a declared complete cart collection.'
            return result
        if any(not isinstance(r['quantity'], str) or not re.fullmatch(r'\d+', r['quantity']) for r in rows):
            result.reason = 'Item quantities were missing or ambiguous; no quantity assertion was made.'
            return result
        success = len(matched) == 1 and int(matched[0]['quantity']) == c.expected_quantity
        success = success and (not c.only_requested_product or len(rows) == 1)
    # An empty DOM without an explicit empty-state marker may simply be loading.
    if not rows and not sample['empty']:
        result.reason = 'No products or explicit empty-state evidence were inspectable.'
        return result
    if success:
        result.task_outcome = 'verified_complete'
        result.reason = 'All configured observable endpoint conditions matched.'
    elif final and c.complete_collection:
        result.task_outcome = 'verified_incomplete'
        result.reason = 'The final ready, complete collection contradicted the configured expectation.'
    else:
        result.reason = 'The expected match was not established; absence is not conclusive failure evidence.'
    return result


def attach_verification(report, contract, result):
    report['task_contract'] = contract.model_dump()
    report['outcome_verification'] = result.model_dump()
    report['task_outcome'] = result.task_outcome


def outcome_view(report):
    """Old reports and AI-only status fields never gain verified outcomes on read."""
    result = report.get('outcome_verification', {})
    if result.get('verifier') != 'dom-endpoint-v1':
        return 'unknown', 'Legacy or unconfigured report: completion was not independently verified.'
    return result.get('task_outcome', 'unknown'), result.get('reason', '')
