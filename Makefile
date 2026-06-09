# AnyCompany Hotels — test entry points.
#
# The test suite is layered (see docs/design/testing-framework-plan.md):
#   - unit:        fast, offline, no AWS/DB — the inner loop
#   - integration: against the real dev stack (needs AWS creds)
#   - contract:    API contract capture/verify (needs creds + deployed API)
#   - e2e:         full-flow backend journeys (needs creds)
#   - frontend:    vitest component tests for both React apps
#   - browser:     Playwright browser E2E
#
# A Python 3.12 venv (matching the Lambda runtime) lives at .venv-test.

VENV        := .venv-test
PY          := $(VENV)/bin/python
PIP         := $(VENV)/bin/pip
PYTEST      := $(VENV)/bin/pytest
# Override with your own profile: `make test-integration AWS_PROFILE=my-profile`
# or `export AWS_PROFILE=my-profile` in your shell. `?=` leaves an inherited
# AWS_PROFILE untouched.
AWS_PROFILE ?= default
STACK_NAME  := anycompany-booking
# Force us-east-1 with `override`: the dev stack is in us-east-1, but a shell
# commonly exports AWS_REGION=us-west-2. A plain assignment can't beat an
# inherited environment variable in make; `override` does.
override AWS_REGION := us-east-1

# The contract + integration suites read the stack's ApiUrl / PmsApiUrl
# outputs directly.

.PHONY: help install-test test-unit test-integration test-contract test-e2e \
        test-frontend test-browser test-all coverage sweep clean-test

help:
	@echo "Test targets:"
	@echo "  make install-test      Create .venv-test (py3.12) + install test & layer deps"
	@echo "  make test-unit         Backend unit tests (fast, offline, no creds)"
	@echo "  make test-integration  Backend integration vs dev stack (needs AWS creds)"
	@echo "  make test-contract     API contract capture/verify (needs creds)"
	@echo "  make test-e2e          Backend E2E journeys (needs creds)"
	@echo "  make test-frontend     vitest component tests (both apps)"
	@echo "  make test-browser      Playwright browser E2E"
	@echo "  make test-all          unit + frontend, then stack-dependent layers"
	@echo "  make coverage          Backend coverage report with thresholds"
	@echo "  make sweep             Delete orphan testsuite-* data from the dev stack"

# ── Setup ────────────────────────────────────────────────────────────────────
install-test:
	python3.12 -m venv $(VENV)
	$(PIP) install --upgrade pip >/dev/null
	$(PIP) install -r tests/requirements-test.txt
	$(PIP) install -r src/layers/common/requirements.txt
	@echo "Test venv ready at $(VENV)"

# ── Backend layers ─────────────────────────────────────────────────────────
# Default pytest run is already filtered to -m unit via pyproject.toml addopts.
test-unit:
	$(PYTEST)

test-integration:
	AWS_PROFILE=$(AWS_PROFILE) AWS_REGION=$(AWS_REGION) $(PYTEST) -m integration -o addopts=""

test-contract:
	AWS_PROFILE=$(AWS_PROFILE) AWS_REGION=$(AWS_REGION) $(PYTEST) -m contract -o addopts=""

test-e2e:
	AWS_PROFILE=$(AWS_PROFILE) AWS_REGION=$(AWS_REGION) $(PYTEST) -m e2e -o addopts=""

# ── Frontend ───────────────────────────────────────────────────────────────
test-frontend:
	cd frontend && npm run test --if-present
	cd pms-frontend && npm run test --if-present

test-browser:
	cd e2e && npm test

# ── Aggregate ────────────────────────────────────────────────────────────────
test-all: test-unit test-frontend test-integration test-contract test-e2e

# ── Coverage ─────────────────────────────────────────────────────────────────
# Per-layer thresholds:
#   - utils: 90% (small, pure, critical — high bar is cheap)
#   - handlers: 50% at the UNIT layer. Read/query handlers reach ~80%+, but
#     write handlers have deep multi-step DB transaction flows that are
#     covered meaningfully by the INTEGRATION layer (tranche 4) against the
#     real database rather than by brittle mock choreography. The 50% unit
#     floor reflects that split; integration coverage closes the gap.
coverage: coverage-utils coverage-handlers

coverage-utils:
	$(PYTEST) --cov=src/layers/common/utils --cov-report=term-missing \
		--cov-fail-under=90

coverage-handlers:
	$(PYTEST) --cov=src --cov-report=term-missing --cov-report=html \
		--cov-fail-under=50 \
		--cov-config=pyproject.toml \
		$(shell [ -d tests/unit ] && echo tests/unit)

# ── Maintenance ────────────────────────────────────────────────────────────
sweep:
	AWS_PROFILE=$(AWS_PROFILE) AWS_REGION=$(AWS_REGION) $(PY) tests/sweeper.py

clean-test:
	rm -rf $(VENV) .pytest_cache htmlcov .coverage
	find tests -type d -name __pycache__ -prune -exec rm -rf {} +
