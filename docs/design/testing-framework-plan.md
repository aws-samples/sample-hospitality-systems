# Testing Framework Plan

## Status

This document is the design for the project's comprehensive test framework,
implemented in tranches (see "Sequencing"). The contract layer is the
regression net that proves API changes are non-breaking.

## Goals (from planning conversation)

- **Comprehensive coverage** across four layers: backend unit, backend
  integration, API contract/E2E, frontend (component + browser E2E).
- **Backend unit:** all ~60 handlers + full shared `utils` layer.
- **Backend integration:** runs against the **real dev stack**
  (`anycompany-booking`) — RDS Data API for DB assertions, live API Gateway
  for calls.
- **Contract baseline:** both auto-captured golden snapshots (from the
  deployed API) **and** hand-authored curated specs.
- **Frontend:** vitest + React Testing Library for components/hooks, plus
  Playwright browser E2E for critical journeys.
- **Test data:** dedicated `testsuite-`-prefixed records, isolated from
  demo/simulator data.
- **Auth:** dedicated test users per Cognito role.
- **Cleanup:** pytest fixtures (teardown on failure) **plus** a standalone
  sweeper script for orphans.
- **Coverage:** measured **and** enforced with thresholds.
- **CI:** out of scope for now — everything must run cleanly via a single
  local command per layer. CI wiring is a later piece of work.

## Current state (baseline)

- **Backend:** 3 unit files in `tests/unit/` (`test_tenant.py`,
  `test_tenant_properties.py`, `test_loyalty.py`). Pure-logic, mocked API
  Gateway events, no DB/AWS. They import `utils.*` directly and rely on an
  externally-set `PYTHONPATH` (no `conftest.py`, no `pytest.ini`/`pyproject.toml`).
- **Frontend:** zero tests in either app. No test runner wired up. Both use
  Vite + React 18 + TS, so vitest is the natural fit.
- **CI:** none.
- **Untested today:** all 61 Lambda handlers, both API Gateways, both state
  machines, all event/SQS flows, both React apps.

Handler inventory (unit-test targets), 61 total:

| Domain | Files | Domain | Files |
|---|---|---|---|
| property | 4 | pms/checkinout | 5 |
| crs | 6 | pms/housekeeping | 8 |
| guest | 5 | pms/billing | 6 |
| payment | 7 | pms/loyalty | 5 |
| booking | 6 | pms/night_audit | 3 |
| reporting | 5 | pms/notifications | 1 |

Shared `utils` layer (9 modules): `auth`, `database`, `events`, `loyalty`,
`response`, `stripe_client`, `tenant`, `validation` + `models/enums`.

## Directory & tooling layout

```
hospitality-systems/
├── pyproject.toml                 # NEW — pytest, coverage, markers config
├── Makefile                       # NEW — single entry point per layer
├── tests/                         # backend tests
│   ├── conftest.py                # NEW — PYTHONPATH wiring, shared fixtures
│   ├── unit/                      # existing 3 files + ~60 new
│   │   ├── utils/                 #   one file per utils module
│   │   ├── property/ crs/ guest/ payment/ booking/ ...
│   │   └── pms/...
│   ├── integration/               # NEW — real dev-stack tests
│   │   ├── conftest.py            #   stack-output discovery, DB Data API client
│   │   └── ...
│   ├── contract/                  # NEW — API contract regression net
│   │   ├── baseline/              #   captured golden snapshots (JSON, committed)
│   │   ├── specs/                 #   hand-authored curated contract specs
│   │   ├── capture.py             #   records baseline from a deployed API
│   │   └── verify.py              #   replays + diffs against a target API
│   ├── e2e/                       # NEW — full-flow backend journeys
│   ├── fixtures/                  # NEW — shared data builders, test-user mgmt
│   └── sweeper.py                 # NEW — deletes all testsuite-* orphans
├── frontend/
│   ├── vitest.config.ts           # NEW
│   └── src/**/__tests__/          # NEW — co-located component/hook tests
├── pms-frontend/
│   ├── vitest.config.ts           # NEW
│   └── src/**/__tests__/          # NEW
└── e2e/                           # NEW — Playwright browser E2E (both apps)
    ├── playwright.config.ts
    ├── crs/                       #   guest booking journeys
    └── pms/                       #   staff dashboard journeys
```

### Why this structure

- **Layered backend dirs** (`unit`/`integration`/`contract`/`e2e`) make the
  "run only fast tests" vs "run the expensive real-stack tests" split obvious
  and let the Makefile expose one target per layer.
- **Co-located frontend component tests** (`src/**/__tests__/`) match the
  React community default and keep tests next to the code they cover.
- **Top-level `e2e/`** for Playwright because browser E2E spans both apps and
  isn't owned by either frontend package.
- **A Makefile** is the single discoverable entry point — important for an
  open-source sample where contributors shouldn't have to reverse-engineer
  invocation. pytest markers are *also* configured (for fine-grained
  selection), but the Makefile is the front door.

### Runner choices

| Layer | Runner | Rationale |
|---|---|---|
| Backend unit | pytest | Already in use; fast; rich fixtures |
| Backend integration | pytest (markered `integration`) | Same toolchain; gated behind a marker so it never runs by accident |
| Contract | pytest (markered `contract`) | Capture/verify are pytest-driven |
| Backend E2E | pytest (markered `e2e`) | Same toolchain |
| Frontend component | vitest + React Testing Library | Native Vite integration; near-zero config |
| Browser E2E | Playwright | Best-in-class, multi-browser, trace viewer |

## Makefile targets

```
make install-test     # install pytest, moto-free deps, playwright browsers, vitest
make test-unit        # backend unit (fast, no AWS, no creds) — default for inner loop
make test-integration # backend integration against dev stack (needs creds)
make test-contract    # capture/verify API contract (needs creds + deployed API)
make test-e2e         # backend E2E journeys (needs creds)
make test-frontend    # vitest component tests for both apps
make test-browser     # Playwright browser E2E
make test-all         # everything (unit + frontend first, then stack-dependent)
make coverage         # aggregate coverage report across backend + frontend
make sweep            # run tests/sweeper.py to delete orphan testsuite-* data
```

## Layer 1 — Backend unit (all handlers + all utils)

**Scope:** every handler's core logic paths + complete `utils` coverage.

**Mechanics:**
- `pyproject.toml` sets `pythonpath = ["src/layers/common"]` so `import utils.*`
  resolves without an externally-set `PYTHONPATH` (fixes the current implicit
  dependency). Handler imports resolve via per-domain path entries or a
  `conftest.py` that appends the handler's `CodeUri` dir.
- **No AWS, no DB.** Boto3 clients and `get_conn()` are patched. DB cursors
  are mocked to return canned rows. This keeps unit tests sub-second and
  creds-free — they're the inner-loop suite.
- Handler tests assert: status code, response envelope shape
  (`{success, data, metadata}` / error envelope), claim/authz branching,
  input-validation rejection paths, and event-publish calls (mocked
  `publish_event` asserted with expected payload).
- `utils` tests cover every public function — `auth.get_claims`, `tenant`
  authz matrix, `validation` parsers, `events.publish_event` (incl. the
  no-`event_bus_name`-kwarg gotcha), `response` envelope builders,
  `loyalty` tier math, `stripe_client` with a stubbed Stripe SDK.

**Effort:** largest layer. ~60 handler files + 9 utils modules. Estimate
2-3 days. Done domain-by-domain so it's reviewable in chunks.

## Layer 2 — Backend integration (real dev stack)

**Scope:** handlers exercised against live AWS — DB writes verified via the
RDS Data API, events verified via EventBridge/SQS, state-machine flows
verified via Step Functions executions.

**Mechanics:**
- `tests/integration/conftest.py` discovers stack outputs via
  `cloudformation describe-stacks` (DBClusterArn, DBSecretArn, ApiUrl,
  PmsApiUrl, etc.) once per session and exposes them as fixtures.
- DB assertions use `aws rds-data execute-statement` (the Data API —
  already enabled, see [[data-api]]) rather than spinning up a VPC Lambda.
- All created records use the `testsuite-` prefix (guests
  `testsuite-<uuid>@example.test`, etc.) so the sweeper can find them and
  they never collide with `simguest-` or demo data.
- Marked `@pytest.mark.integration`; excluded from the default `test-unit`
  run; require AWS creds (`--profile <your-profile> --region us-east-1`).

**Coverage targets:** the write paths and cross-service flows that unit tests
can't prove — booking completion writing a reservation + decrementing
availability + emitting `reservation.created`; checkout driving the
CheckoutBilling state machine; housekeeping task-token transitions; loyalty
earn-on-checkout.

**Effort:** ~2 days.

## Layer 3 — API contract (the regression net)

This is the layer that most directly catches unintended changes to the API's
externally-observable contract.

**Two complementary pieces:**

1. **Captured golden baseline (`tests/contract/baseline/`).**
   - `capture.py` authenticates as each test role, hits every endpoint with
     representative inputs (including auth-failure and validation-failure
     cases), and records `{request, status, headers-of-interest, response-body}`
     as committed JSON snapshots, normalized to strip volatile fields
     (timestamps, generated IDs, request IDs).
   - `test_contract.py` replays the same requests against the deployed API and
     diffs against the baseline. Any shape, status, or auth-behavior drift
     fails the run.

2. **Curated contract specs (`tests/contract/specs/`).**
   - Hand-authored per-endpoint assertions describing *intended* behavior
     (not just current behavior): required fields, status codes, auth
     requirements, pagination envelope, error codes. Documents the contract
     and catches cases where current behavior is itself wrong.

**Normalization matters:** the diff must ignore legitimate run-to-run and
cross-environment differences (e.g. `requestContext` internals never appear in
responses, but header casing and a few gateway-injected fields can differ).
The engine normalizes to a structural skeleton so only meaningful drift fails.

**Effort:** ~2 days.

## Layer 4 — Frontend

**Component (vitest + React Testing Library):**
- Wire `vitest.config.ts` into both apps (Vite already present — minimal config).
- Cover: `usePropertyScope` hook (the JWT-claim → property resolution logic),
  the shared `<Pagination>` and `<PropertySelector>` components, form
  validation, the API client error handling, and the auth context's
  token/claim parsing.
- Mock the API layer (`axios`) so component tests are deterministic and offline.

**Browser E2E (Playwright):**
- `playwright.config.ts` at repo root; projects for CRS and PMS.
- Critical journeys only (not exhaustive):
  - **CRS:** search → select room → cart → complete booking (Stripe test card)
    → see confirmation.
  - **PMS:** staff sign-in → view stays → check-in a guest → housekeeping
    task → checkout → folio.
- Runs against the deployed dev frontends (CloudFront URLs from stack
  outputs). Uses dedicated test users.

**Effort:** ~2-3 days (component + E2E).

## Test users & auth

Seed one Cognito user per role, with credentials in a single Secrets Manager
secret (`anycompany-booking-testsuite-creds-dev`):

| Test user | Group | Exercises |
|---|---|---|
| `testsuite-admin@example.test` | Admin | chain-level access, all bypass paths |
| `testsuite-manager@example.test` | Manager | chain-level management |
| `testsuite-regional@example.test` | RegionalManager | region-scoped access |
| `testsuite-frontdesk@example.test` | FrontDesk | property-pinned access |
| `testsuite-housekeeping@example.test` | Housekeeping | property-pinned, limited |
| `testsuite-guest@example.test` | (none / guest) | guest-facing CRS flows |

- A new `scripts/seed_test_users.py` provisions these (idempotent, same pattern
  as `seed_cognito_users.py`).
- Integration/contract/E2E harnesses authenticate via the same
  `AdminInitiateAuth` flow the simulator uses, scoped to the role each test
  needs — this is what lets us actually test **tenant isolation and authz**,
  not just happy-path-as-Admin.
- Note: if MFA is added later, these test users either get MFA pre-enrolled
  by the seeding script or are exempted via the same client-scoping
  mechanism.

## Test data & cleanup

- **Convention:** every record a test creates carries a `testsuite-` marker
  (email prefix, or a `notes`/`tags` field where email isn't available).
- **Fixture teardown:** pytest fixtures delete what they create in
  `finally`/teardown, so a normal failure still cleans up.
- **Sweeper (`tests/sweeper.py`):** standalone script that deletes *all*
  `testsuite-`-marked data across guests, reservations, folios, charges,
  loyalty, housekeeping tasks, checkinout records, and the corresponding
  Cognito test-data users created ad hoc. Runnable any time via `make sweep`
  to catch orphans from killed runs. Idempotent and safe (only ever touches
  `testsuite-` data — never `simguest-` or demo data).
- The sweeper double-checks its WHERE clauses against the prefix before any
  DELETE, and runs against the Data API so it's auditable.

## Coverage measurement & enforcement

- **Backend:** `pytest-cov` over `src/`. Thresholds:
  - `utils` layer: **90%** (it's small, critical, and pure — high bar is cheap).
    Achieved in tranche 2 (~99%).
  - handlers, UNIT layer: **50%**. Read/query handlers reach ~80%+ at the unit
    layer, but write handlers have deep multi-step DB transaction flows
    (150+ line happy paths with many sequential cursor calls). Those flows are
    covered meaningfully by the INTEGRATION layer (tranche 4) against the real
    database, not by brittle mock choreography that would only assert the mocks
    return what they were told. Unit tests for write handlers therefore target
    the deterministic, high-value branches — auth gates, input validation,
    not-found/forbidden, guest-not-found — leaving the transactional happy
    path to integration. The 50% unit floor reflects this deliberate split.
- **Frontend:** vitest `--coverage` (v8 provider). Threshold **70%** on
  `src/` excluding generated/config files.
- Enforcement: the relevant `make` target fails below threshold. Because CI
  isn't wired yet, enforcement is local — but the thresholds live in
  `pyproject.toml` / `vitest.config.ts` so they transfer directly when CI lands.
- **Combined coverage** (unit + integration) is the real measure of handler
  safety. The split exists because the two layers test different things: unit
  proves the branch logic, integration proves the transactional behavior.

## Sequencing (implementation tranches)

Each tranche is independently reviewable and leaves the suite runnable.

1. **Tranche 1 — Foundation.** `pyproject.toml`, `conftest.py` (fix the
   implicit `PYTHONPATH`), `Makefile`, migrate the 3 existing unit files into
   the new layout, coverage config. Outcome: `make test-unit` works cleanly.
2. **Tranche 2 — utils unit coverage.** All 9 utils modules to 90%. Highest
   value-per-effort; locks the shared foundation every handler depends on.
3. **Tranche 3 — handler unit coverage.** Domain-by-domain (property → crs →
   guest → booking → payment → pms/*). One commit per domain.
4. **Tranche 4 — test users + integration harness.** `seed_test_users.py`,
   `tests/integration/conftest.py`, sweeper, then integration tests for the
   write/flow paths.
5. **Tranche 5 — contract baseline.** `capture.py`/`test_contract.py`, capture
   the golden baseline from the deployed API, author curated specs.
6. **Tranche 6 — frontend component tests.** vitest wiring + component/hook
   coverage for both apps.
7. **Tranche 7 — browser E2E.** Playwright config + critical journeys.

Tranches 1-2 are the inner-loop foundation; tranche 5 (the contract net) is the
highest-leverage guard against unintended API changes.

## Dependencies to add

- **Backend (`tests/requirements-test.txt`, NEW):** `pytest`, `pytest-cov`,
  `pytest-mock`. No `moto` (we use the real stack). `boto3` already available.
- **Frontend (devDependencies):** `vitest`, `@testing-library/react`,
  `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`,
  `@vitest/coverage-v8`.
- **E2E:** `@playwright/test` (+ `npx playwright install` for browsers).

## Risks & considerations

| Risk | Mitigation |
|---|---|
| Integration tests mutate the live dev stack | `testsuite-` prefix isolation + fixture teardown + sweeper; never touch `simguest-`/demo data |
| Tests interfere with the 4-hourly simulator run | Distinct data prefix; tests tolerate concurrent simulator activity (assert on own records only) |
| Contract baseline captures buggy current behavior as "correct" | Curated specs layer asserts *intended* behavior to catch this; baseline is for drift-detection, specs for correctness |
| Handler import resolution is messy (per-domain CodeUri) | `conftest.py` centralizes path setup; documented in the test README |
| Test users + future MFA conflict | Seeding script pre-enrolls or exempts test users |
| Coverage thresholds slow iteration | Start conservative (75% handlers), ratchet up; thresholds are per-layer not global |
| Real-stack tests need creds → can't run fully offline | `make test-unit` + `make test-frontend` are the offline inner loop; stack-dependent layers are explicitly separate targets |

## Open questions deferred to implementation

- Exact coverage thresholds may need tuning once we see real numbers.
- Whether to add `pytest-xdist` for parallel test execution (speeds the suite
  but complicates the shared dev-stack data story — probably defer).
- Playwright against deployed frontends vs `vite preview` locally — leaning
  deployed for fidelity, revisit if flakiness appears.
