"""Each contract README states how many valid and invalid fixtures the contract has; the stated totals must equal the files on disk.

Reading rule (explicit, so the check cannot silently read some other number): in a README's text, the FIRST match of
`\\bValid \\((\\d+)\\)` is the stated valid total and the FIRST match of `\\bInvalid \\((\\d+)\\)` is the stated invalid total
(case-insensitive, whole word, so "Invalid (94)" is not read as a valid count). A total includes every fixture in the directory,
including ones added later. On disk the count is the number of `*.json` files in `fixtures/valid/` and `fixtures/invalid/`.
"""
import re
from pathlib import Path

import pytest

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
VALID_STATED = re.compile(r"\bvalid \((\d+)\)", re.IGNORECASE)
INVALID_STATED = re.compile(r"\binvalid \((\d+)\)", re.IGNORECASE)

# READMEs that state no total in the `Valid (N)` / `Invalid (N)` form. They are exempt until they state one; adding a
# stated total to one of them removes it from this list (see test_exemption_list_is_current).
NO_STATED_TOTAL = {"bounded-deferral", "execution-attempt-lifecycle", "governed-exchange", "index-evidence-registry"}

NAMES = sorted(p.parent.name for p in CONTRACTS.glob("*/fixtures") if p.is_dir())


def stated(name):
    body = (CONTRACTS / name / "README.md").read_text(encoding="utf-8")
    valid, invalid = VALID_STATED.search(body), INVALID_STATED.search(body)
    return (int(valid.group(1)) if valid else None), (int(invalid.group(1)) if invalid else None)


def on_disk(name, kind):
    return len(list((CONTRACTS / name / "fixtures" / kind).glob("*.json")))


@pytest.mark.parametrize("name", [n for n in NAMES if n not in NO_STATED_TOTAL])
def test_readme_stated_fixture_counts_equal_files_on_disk(name):
    valid, invalid = stated(name)
    assert valid is not None and invalid is not None, (
        f"contracts/{name}/README.md must state `Valid (N)` and `Invalid (N)` fixture totals (found valid={valid}, invalid={invalid})")
    assert valid == on_disk(name, "valid"), (
        f"contracts/{name}/README.md states Valid ({valid}) but fixtures/valid has {on_disk(name, 'valid')} files; update the README")
    assert invalid == on_disk(name, "invalid"), (
        f"contracts/{name}/README.md states Invalid ({invalid}) but fixtures/invalid has {on_disk(name, 'invalid')} files; update the README")


def test_exemption_list_is_current():
    assert NO_STATED_TOTAL <= set(NAMES), NO_STATED_TOTAL - set(NAMES)
    for name in NO_STATED_TOTAL:
        assert stated(name) == (None, None), f"contracts/{name}/README.md now states a total; remove it from NO_STATED_TOTAL"
    assert len(NAMES) - len(NO_STATED_TOTAL) >= 13
