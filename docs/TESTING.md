# Testing

AnyCompany Hotels ships with a comprehensive, layered test suite. This
document is the reference for running it, understanding what each layer
covers, and extending it.

The framework's design rationale lives in
[`docs/design/testing-framework-plan.md`](./design/testing-framework-plan.md).

## TL;DR

```bash
make install-test     # one-time: build .venv-test (Python 3.12) + install deps
make test-unit        # fast, offline, no AWS — the inner loop
make test-all         # unit + frontend + integration + contract + e2e (needs AWS creds for stack layers)
```

> `make test-all` runs unit, frontend, integration, contract, and backend e2e. It does **not**
> run `make test-browser` (Playwright) — run that target separately.

Everything runs through the root `Makefile`. There is one target per layer.

## The layers

| Layer | Command | Needs AWS? | What it proves |
|---|---|---|---|
| Backend unit | `make test-unit` | no | Handler branch logic + full `utils` coverage, all mocked |
| Backend integration | `make test-integration` | yes | Handlers against the real dev stack (DB via Data API, live APIs) |
| API contract | `make test-contract` | yes | Endpoint status/shape/auth match the captured baseline (regression net) |
| Backend E2E | `make test-e2e` | yes | Full-flow backend journeys (reserved — no `@pytest.mark.e2e` tests yet) |
| Frontend component | `make test-frontend` | no | PMS hooks + components (vitest + React Testing Library) |
| Browser E2E | `make test-browser` | yes | Critical user journeys in a real browser (Playwright) |

`make test-unit` is the default fast loop: offline, credential-free, ~2s.
The stack-dependent layers (`integration`, `contract`, `e2e`, `browser`)
run against the deployed `anycompany-booking` dev stack and need AWS
credentials.

## Prerequisites

### Backend (Python)

```bash
make install-test
```

Creates `.venv-test/` using **Python 3.12** (matching the Lambda runtime)
and installs `tests/requirements-test.txt` plus the shared layer's
`requirements.txt`.

### Frontend (Node)

```bash
cd pms-frontend && npm install     # vitest + React Testing Library
cd e2e && npm install && npx playwright install chromium
```

### For the stack-dependent layers

1. AWS credentials for the deployed stack (set `AWS_PROFILE` to your profile;
   region `us-east-1`).
2. The seeded test users (one-time, idempotent):

   ```bash
   python scripts/seed_test_users.py \
       --user-pool-id <UserPoolId from stack outputs> \
       --profile <your-profile> --region us-east-1 \
       --property-id <a real active property id>
   ```

   This provisions six role-scoped Cognito users
   (`testsuite-{admin,manager,regional,frontdesk,housekeeping,guest}@example.test`)
   and stores their shared password in Secrets Manager
   (`anycompany-booking-testsuite-creds-dev`). Tests authenticate as the
   role they need to exercise real authorization, not just happy-path-as-Admin.

## Layer 1 — Backend unit

Fast, offline tests of every handler's branch logic plus complete coverage
of the shared `utils` layer. AWS clients, the database, and Stripe are all
mocked.

```bash
make test-unit             # ~2s, no creds
make coverage-utils        # enforces 90% on the utils layer
make coverage-handlers     # enforces 50% on handlers (see "Coverage" below)
```

Structure: `tests/unit/utils/` (one file per `utils` module) and
`tests/unit/<domain>/` (one file per handler domain — property, crs, guest,
booking, payment, pms_*).

Key fixtures in `tests/conftest.py`:

- **`load_handler("domain/file.py")`** — imports a handler by explicit path.
  This is required, not optional: several handler files share a name across
  domains (`list_properties.py` in both `property/` and `pms/reporting/`;
  `process_event.py` in three PMS domains; `sfn_actions.py` in two). A flat
  `sys.path` would make `import list_properties` resolve ambiguously. At
  runtime SAM isolates each function's `CodeUri`, so there's no collision in
  production — only in a flat test process. Always load handlers via this
  fixture; never `import` them by bare name.
- **`mock_db`** — a scripted mock connection. `mock_db.queue(fetchone=...,
  fetchall=...)` queues one result per `with conn.cursor()` block the handler
  opens. Supports both `get_conn()` and `with get_conn() as conn:` patterns.
- **`make_event(...)`** — builds an API Gateway event with the Cognito user
  pool authorizer shape (claims at `requestContext.authorizer.claims`), matching
  what handlers read via `utils.auth.get_claims`.
- **`lambda_context`** — a mock Lambda context. Handlers decorated with
  powertools' `@logger.inject_lambda_context` must be invoked with it as the
  second argument, or the decorator raises on a `None` context.

## Layer 2 — Backend integration

Tests that run against the **real dev stack**: DB assertions via the RDS Data
API, HTTP calls to the live API Gateways, authenticated per role.

```bash
make test-integration      # needs AWS creds + seeded test users
```

`tests/integration/conftest.py` provides: `stack_outputs` (CloudFormation
output discovery), `db` (Data API query/execute helper), `token_for(role)`
(mints a Cognito ID token per test role), `api` / `pms_api` (authenticated
HTTP clients), and `track` (registers created records for guaranteed
teardown).

Covered here: the transactional flows the unit layer intentionally defers —
the end-to-end booking flow writing a real reservation + decrementing
availability, and the tenant-isolation authorization matrix enforced live
across every role.

## Layer 3 — API contract (the regression net)

Captures golden response **shape** snapshots from the deployed API, then
replays the same request matrix and diffs against the baseline — catching any
drift in endpoint status, response shape, or auth behavior.

```bash
# Capture / re-capture the baseline (only when the contract deliberately changes):
AWS_PROFILE=<your-profile> AWS_REGION=us-east-1 \
    python tests/contract/capture.py

# Verify the current API still matches the baseline:
make test-contract
```

- `tests/contract/matrix.py` — the declarative request matrix (public reads,
  auth-required 401s, the role-based 403 matrix, pagination envelopes,
  not-found/bad-uuid shapes).
- `tests/contract/engine.py` — normalizes each response to its structural
  skeleton (keys + type tokens, volatile fields like ids/timestamps stripped,
  list element-shapes preserved), so the diff catches structural drift while
  ignoring data values that legitimately change.
- `tests/contract/baseline/contract.json` — the committed golden baseline.

Any difference in status code, response shape, or auth behavior surfaces as a
test failure. **Do not re-capture the baseline to make a failing test pass** —
that erases the comparison. Only re-capture for a deliberate, documented
contract change.

## Layer 4 — Frontend component

vitest + React Testing Library for the PMS app's shared logic.

```bash
make test-frontend                       # both apps (runs whatever has a test script)
cd pms-frontend && npm run test:coverage # PMS coverage report
```

Covered: `usePropertyScope` (the JWT-claim → property-scope resolution hook —
the frontend half of tenant isolation) and the shared `<Pagination>`
component. The CRS frontend's flows are covered at the browser-E2E layer
instead, as it has no comparable shared pure-logic units.

## Layer 5 — Browser E2E

Playwright against the **deployed** frontends. URLs and the test-user password
are resolved at run time from CloudFormation outputs and Secrets Manager
(`e2e/global-setup.ts`) — nothing hardcoded.

```bash
make test-browser          # needs AWS creds + seeded test users
cd e2e && npm run report   # open the HTML report after a run
```

Covered: the full PMS staff journey (real Cognito SRP login → dashboard →
stays → sign out), bad-credential rejection, and a CRS guest-site smoke test.

## Test data + cleanup

Every record the suite creates is **`testsuite-` prefixed** (guest emails like
`testsuite-<uuid>@example.test`), keeping it isolated from `simguest-`
(activity simulator) and demo data.

- Integration fixtures clean up what they create on teardown.
- **`make sweep`** (`tests/sweeper.py`) is the backstop: it deletes all
  `testsuite-` data in FK-safe order. Run it any time to clear orphans left by
  a crashed run. It is strictly scoped to `testsuite-` guests and never touches
  `simguest-`/demo data. (It does not delete the seeded Cognito test users or
  their secret — those are durable; re-run `seed_test_users.py` to reset them.)

## Coverage

Per-layer thresholds, enforced by the Makefile:

- **`utils`: 90%** (`make coverage-utils`) — small, pure, critical; ~99% today.
- **Handlers: 50% at the unit layer** (`make coverage-handlers`). Read/query
  handlers reach 75-100%, but write handlers are unit-tested only on their
  auth/validation/not-found **gates** — their deep multi-step DB transaction
  flows are covered by the integration layer against the real database, not by
  mock choreography that would only assert the mocks. Combined unit +
  integration coverage is the real measure of handler safety.
- **Frontend: 70%** is the design target, but it is **not yet enforced** — the
  `thresholds` block in `pms-frontend/vitest.config.ts` is currently empty while
  per-file coverage is built out.

CI is not wired yet (deferred). The Python thresholds live in `pyproject.toml`
and are enforced by the Makefile today; the frontend threshold is documented
here but not yet wired into `vitest.config.ts`.

## Gotchas

- **Region override.** A shell may export `AWS_REGION=us-west-2`. The Makefile
  forces `override AWS_REGION := us-east-1` for the AWS-targeting targets so
  they can't misroute. If you run a test script directly, pass
  `AWS_REGION=us-east-1` explicitly.
- **First-hit blip.** A warm Lambda whose cached DB connection was reaped by
  the 30s `idle_in_transaction_session_timeout` used to 500 on the next call;
  `get_conn()` now does a liveness probe and reconnects. Integration/contract/
  browser layers also carry a retry to absorb cold-start latency.
- **`make test-unit` is the only fully offline target.** Everything else needs
  AWS credentials and the seeded test users.
