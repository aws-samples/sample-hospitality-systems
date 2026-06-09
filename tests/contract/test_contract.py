"""
Contract verification (the API regression net).

Replays the contract matrix against the deployed API and:
  1. Asserts each endpoint's behavior matches its declared contract
     (status code + required key paths).
  2. If a captured baseline exists (tests/contract/baseline/contract.json),
     diffs the normalized response structure against it — catching any drift
     in status code, response shape, or auth behavior.

Marked `contract`; needs AWS creds + seeded test users. Excluded from the
default unit loop.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from engine import ContractContext, normalize_response, get_key_path  # noqa: E402
from matrix import MATRIX  # noqa: E402

BASELINE_PATH = os.path.join(os.path.dirname(__file__), "baseline", "contract.json")


@pytest.fixture(scope="module")
def ctx():
    return ContractContext()


@pytest.fixture(scope="module")
def baseline():
    if not os.path.exists(BASELINE_PATH):
        return None
    with open(BASELINE_PATH) as f:
        return json.load(f)


@pytest.mark.parametrize("entry", MATRIX, ids=[e["name"] for e in MATRIX])
def test_contract_entry(ctx, baseline, entry):
    status, body = ctx.call(entry)

    # 1. Declared status contract.
    assert status == entry["expect"], (
        f"{entry['name']}: status {status} != contract {entry['expect']} "
        f"(body: {json.dumps(body)[:200]})"
    )

    # 2. Declared structural contract (required key paths present).
    for dotted in entry.get("shape", []):
        assert get_key_path(body, dotted), (
            f"{entry['name']}: missing required key path '{dotted}' "
            f"(body: {json.dumps(body)[:200]})"
        )

    # 3. Baseline drift (only if a baseline has been captured).
    if baseline is not None and entry["name"] in baseline:
        current = normalize_response(status, body)
        expected = baseline[entry["name"]]
        assert current == expected, (
            f"{entry['name']}: contract DRIFT vs baseline.\n"
            f"  baseline: {json.dumps(expected)}\n"
            f"  current : {json.dumps(current)}"
        )
