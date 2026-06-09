"""Lint guard: handlers must use the shared structured logger, not stdlib logging.

All handler logging goes through utils.logger.get_logger() so that PII redaction
and structured JSON output apply uniformly. This test fails if any handler under
src/ reintroduces `import logging` / `logging.getLogger()`, which would silently
bypass redaction.

The shared logger module itself (utils/logger.py) is exempt — it legitimately
wraps powertools, which uses stdlib logging internally.
"""

import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[3] / "src"
EXEMPT = {"layers/common/utils/logger.py"}

_STDLIB_LOGGING = re.compile(r"^\s*import logging\b|logging\.getLogger\(", re.M)


def test_no_handler_uses_stdlib_logging():
    offenders = []
    for py in SRC.rglob("*.py"):
        rel = py.relative_to(SRC).as_posix()
        if rel in EXEMPT or py.name == "__init__.py":
            continue
        if _STDLIB_LOGGING.search(py.read_text()):
            offenders.append(rel)
    assert not offenders, (
        "These files use stdlib logging instead of utils.logger.get_logger() "
        f"(bypasses PII redaction): {offenders}"
    )
