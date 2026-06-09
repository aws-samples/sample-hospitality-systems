"""
Capture the API contract baseline from the currently deployed API.

Banks the golden baseline that test_contract.py replays against: it captures
the normalized response shape for each request in the matrix. Any later
structural drift (status code, response shape, auth behavior) fails the run.

Usage:
    AWS_PROFILE=<your-profile> AWS_REGION=us-east-1 \\
        python tests/contract/capture.py

Writes tests/contract/baseline/contract.json (committed to the repo).

Re-running overwrites the baseline — only do that intentionally, for a
deliberate, documented contract change.
"""

import json
import os
import sys

# engine + matrix live alongside this file
sys.path.insert(0, os.path.dirname(__file__))
from engine import ContractContext, normalize_response  # noqa: E402
from matrix import MATRIX  # noqa: E402

BASELINE_PATH = os.path.join(os.path.dirname(__file__), "baseline", "contract.json")


def main():
    ctx = ContractContext()
    baseline = {}
    print(f"Capturing {len(MATRIX)} contract entries...\n")

    for entry in MATRIX:
        status, body = ctx.call(entry)
        record = normalize_response(status, body)
        baseline[entry["name"]] = record
        flag = "ok " if status == entry["expect"] else "!! "
        print(f"  {flag}{entry['name']:<45} {status} (expected {entry['expect']})")

    os.makedirs(os.path.dirname(BASELINE_PATH), exist_ok=True)
    with open(BASELINE_PATH, "w") as f:
        json.dump(baseline, f, indent=2, sort_keys=True)
        f.write("\n")

    mismatches = [e["name"] for e in MATRIX
                  if baseline[e["name"]]["status"] != e["expect"]]
    print(f"\nWrote {BASELINE_PATH}")
    if mismatches:
        print(f"\nWARNING: {len(mismatches)} entries returned an unexpected "
              f"status — review before trusting this baseline:")
        for m in mismatches:
            print(f"    {m}")
        return 1
    print("All entries returned their expected status. Baseline is trustworthy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
