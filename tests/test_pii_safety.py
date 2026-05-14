"""PII safety regression tests.

Runs against the committable artifacts (cerebro_state.json + .gitignore)
to catch leaks BEFORE they hit a public push.

Triggered:
- on every `pytest tests/`
- by scripts/auto_commit_cerebro.bat as a hard gate before staging

If any test fails, the auto-commit refuses to stage cerebro_state.json
and exits with a non-zero status — the cron job leaves the bad version
local and surfaces an error in the log.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CEREBRO = ROOT / "dashboard" / "data" / "cerebro_state.json"
GITIGNORE = ROOT / ".gitignore"


# ---------------------------------------------------------------------------
# Patterns that must NEVER appear in cerebro_state.json. Conservative —
# false positives are preferable to leaks. Tune as the system evolves.
# ---------------------------------------------------------------------------
CRITICAL_PATTERNS: dict[str, str] = {
    # Anthropic API keys (Claude)
    "anthropic_key": r"sk-ant-[a-zA-Z0-9_-]{20,}",
    # OpenAI API keys (in case any module ever stores one)
    "openai_key": r"\bsk-[A-Za-z0-9]{40,}",
    # Alpaca paper / live API keys (PK prefix, 16+ char ID)
    "alpaca_key": r"\bPK[A-Z0-9]{16,}",
    # GitHub personal access tokens
    "github_token": r"\bghp_[A-Za-z0-9]{36}",
    "github_fine_grained": r"\bgithub_pat_[A-Za-z0-9_]{50,}",
    # Generic secret-looking JSON fields
    "alpaca_secret_field": r'"alpaca_secret"|"api_secret"|"private_key"',
    # Email
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    # Spanish DNI/NIE (8 digits + letter)
    "dni_nif": r"\b\d{8}[A-HJ-NP-TV-Z]\b",
    # Spanish IBAN
    "iban_es": r"\bES\d{22}\b",
    # User name (case-insensitive)
    "name_lluis": r"(?i)\blluis\s+goris\b|\bgoris\s+lluis\b",
}


@pytest.mark.skipif(
    not CEREBRO.exists(),
    reason="cerebro_state.json missing — generate via daily cron first",
)
def test_cerebro_state_no_pii() -> None:
    """The committable cerebro state must contain no PII / credentials.

    Run via auto_commit_cerebro.bat as a gate before `git add`."""
    content = CEREBRO.read_text(encoding="utf-8")
    issues: list[str] = []
    for name, pattern in CRITICAL_PATTERNS.items():
        matches = re.findall(pattern, content)
        if matches:
            issues.append(
                f"{name}: {len(matches)} match(es), first={matches[:2]}"
            )
    assert not issues, "PII detected in cerebro_state.json:\n  " + "\n  ".join(issues)


def test_gitignore_protects_env() -> None:
    """`.env` must remain gitignored — it carries every API key."""
    text = GITIGNORE.read_text(encoding="utf-8")
    # Match either bare `.env` line or under a comment block; both are valid.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    assert any(
        ln == ".env" or ln == "/.env" or ln.startswith(".env\n") or ln == ".env*"
        for ln in lines
    ), "`.env` is not in .gitignore — env file would leak on commit"


def test_gitignore_protects_data_dir() -> None:
    """`data/` (snapshots, events, lots) must remain gitignored.

    The cerebro state is the ONLY exception (allow-listed via `!` rule)
    and lives under `dashboard/data/`, not `data/`."""
    text = GITIGNORE.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    assert any(
        ln == "data/" or ln == "/data/" or ln.startswith("data/")
        for ln in lines
    ), "`data/` not in .gitignore — raw snapshots would leak on commit"


def test_gitignore_protects_backups() -> None:
    """`backups/` (nightly zips of full data tree) must remain gitignored."""
    text = GITIGNORE.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    assert any(
        ln == "backups/" or ln == "/backups/"
        for ln in lines
    ), "`backups/` not in .gitignore — full data tree zips would leak"
