# Independent Task Outcome Verification

`task_outcomes.py` supplies a versioned `TaskContract`, validated endpoint
configuration, DOM sampler, deterministic evaluator and evidence result.
No decision model chooses the contract or writes the outcome. A model's `stop`,
successful action or generic DOM change is never evidence of task completion.

## Configuration

POST `/api/plans` accepts optional `task_contract`. Its description must equal
the plan's instructions. Existing requests need no changes and remain `unknown`.
The CLI accepts `--task-contract path/to/contract.json`; the description becomes
its task. Resume uses the saved contract unless explicitly replaced. Endpoint
conditions are not sent to the decision model. Review receives the independent
result as context but cannot overwrite its saved fields.

Example (selectors belong to the developer's site, not a global catalog):

```json
{
  "version": "1.0",
  "description": "Add exactly one requested lamp and verify the cart",
  "endpoint": {
    "strategy": "cart_product",
    "expected_url": "https://development.example/cart",
    "container_selector": "[data-cart]",
    "ready_selector": "[data-cart-state='settled']",
    "item_selector": ".cart-row",
    "name_selector": ".product-name",
    "quantity_selector": "input.quantity",
    "product_name": "Requested lamp",
    "complete_collection": true,
    "only_requested_product": true,
    "empty_selector": ".empty-cart"
  }
}
```

Selectors are CSS only. Container and readiness selectors are document-scoped;
item and empty-state selectors are container-scoped; name and quantity selectors
are item-scoped. Search query selector is document-scoped. Names compare exactly
after whitespace normalization (case-sensitive); quantities must be integer text
or input values. URLs match exactly excluding fragments, including query string
encoding/order. Configure the URL the application actually produces.

## Supported strategies

- `product_listing`: intended URL, one rendered collection, visible readiness
  marker, and at least one inspectable named product row.
- `product_search`: listing checks plus exact observed query value and requested
  product name in the result rows. This establishes the search endpoint state,
  not the causal history of how the query was entered.
- `cart_product`: intended cart URL and a declared complete collection containing
  exactly one matching product row with quantity one. By default no other products
  may be present. `only_requested_product: false` permits other products but never
  duplicate matching rows or a different quantity of the requested product.

The developer must choose selectors that actually represent products/results/cart
items. `ready_selector` must identify settled data, not merely the existence of a
page shell. `complete_collection` is an explicit assertion that the DOM collection
is complete (not paginated, virtualized, or still loading). It defaults to false.
Without that assertion exact cart quantity cannot be verified. An incorrect
contract can describe the wrong endpoint; OMNI does not infer contract semantics.

The sampler reads URL, ready state, names, query and quantities in one synchronous
DOM evaluation. It reads rendered elements including offscreen rows, but does not
traverse iframes/shadow roots or prove occlusion-free perceptual visibility. More
than 200 rows, ambiguous/missing values, hidden rows or busy collections return
unknown. This is read-only; verification does not scroll, fill or navigate.

## Status and evidence

- `execution_status`: `finished`, `partial`, `failed`, `cancelled`. A model stop
  may finish execution while the task outcome remains unknown. Budget/loop/boundary
  endings are partial; failures after recorded steps preserve partial status.
- `task_outcome`: `verified_complete`, `verified_incomplete`, `unknown`,
  `unsupported`. Positive outcomes require all conditions. Negative outcomes
  require a final ready inspection of a declared complete collection contradicting
  the expectation. Empty collections also require an explicit empty-state marker.
  Wrong pages, timeouts, missing selectors, unknown readiness, model errors or
  inability to inspect are unknown, not verified incomplete. Screenshot reviews
  with live endpoint contracts are unsupported. Unsupported strategy names are
  rejected at configuration time with validation errors.
- `review_status`: `completed`, `partial`, `unavailable` for newly produced
  reviews. Rejected review items can make a review partial without altering task
  outcome. A failed review cannot erase independent verification.

The legacy `run_status` and run API lifecycle remain available. Historical
`review_status: not_completed` values remain readable. Legacy reports without a
verifier result receive an unknown outcome on read; files are not rewritten.
Model-generated flow completion is always downgraded to an unverified attempt.

Saved `outcome_verification` includes verifier version, outcome, reason,
limitations and evidence records with IDs, timestamps, step references, conditions
and observed values. Evidence is linked by ID in the report's verification detail
panel and is preserved in JSON export. The DOM inspection has its own timestamp;
it is not claimed to be simultaneous with an earlier screenshot. After the loop,
the final inspection supersedes intermediate results. Errors invalidate final-state
certainty. This milestone does not prove persistence, backend correctness, that an
item was absent before the run, or general user-intent completion.

## Fixtures and validation

`tests/fixtures/testlab_outcomes.json` holds TestLab-specific examples. Select one
object for CLI input or place it in an API plan. These are benchmark configuration
fixtures, not claims that full model-driven TestLab benchmarks have passed.
`tests/test_task_outcomes.py` uses inert browser HTML, pure adversarial samples,
API round trips and stubbed model integration. The full Python and frontend
regressions remain required.

Next P0: durable pre-action journaling and execution-time target revalidation.
An action can still occur before a failing after-observation is journaled; a
control can change meaning during model latency. Independent outcome checks do
not fix either execution-integrity issue.
