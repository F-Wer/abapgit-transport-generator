"""The code must stay valid Python 3.11 (requires-python = ">=3.11").

Python 3.12 accepts f-strings that reuse their own quote inside a
placeholder (PEP 701); 3.11 rejects the whole module. Development often
runs on 3.12 only, so this check reads 3.12's f-string tokens and reports
any nested string that uses the enclosing f-string's quote.
"""

import io
import sys
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".venv", ".git", "out", "probes", "__pycache__"}


def _quote(token_text: str) -> str:
    body = token_text.lstrip("rRbBfFuU")
    return body[:3] if body[:3] in ('"""', "'''") else body[:1]


def _reused_quotes(source: str) -> list[int]:
    lines, stack = [], []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.FSTRING_START:
            if stack and _quote(token.string) == stack[-1]:
                lines.append(token.start[0])
            stack.append(_quote(token.string))
        elif token.type == tokenize.FSTRING_END:
            stack.pop()
        elif token.type == tokenize.STRING and stack and _quote(token.string) == stack[-1]:
            lines.append(token.start[0])
    return lines


@pytest.mark.skipif(sys.version_info < (3, 12), reason="needs 3.12 f-string tokens")
def test_no_f_string_reuses_its_own_quote():
    offenders = []
    for path in sorted(ROOT.rglob("*.py")):
        if SKIP & set(path.relative_to(ROOT).parts):
            continue
        for line in _reused_quotes(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.relative_to(ROOT).as_posix()}:{line}")
    assert offenders == []


@pytest.mark.skipif(sys.version_info < (3, 12), reason="needs 3.12 f-string tokens")
def test_the_check_detects_a_reused_quote():
    assert _reused_quotes('x = f"{d["k"]}"\n') == [1]
    assert _reused_quotes("x = f\"{d['k']}\"\n") == []
