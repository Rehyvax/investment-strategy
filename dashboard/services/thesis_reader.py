"""Reads thesis files at data/events/theses/{ASSET}.jsonl.

Adapted to the real on-disk schema (not the idealized one):
- event_type is `thesis` or `thesis_user_override_annotation`.
- version lives in `version` or `model_version`.
- recommendation in `recommendation` (no `verdict` field on most events).
- thesis text content via `confidence_justification` + `must_be_true`
  + override `note`; there is no `thesis_summary` field.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LAB_ROOT = Path(__file__).resolve().parents[2]
THESES_DIR = LAB_ROOT / "data" / "events" / "theses"


class ThesisReader:
    def __init__(self, theses_dir: Path | None = None):
        self.theses_dir = theses_dir or THESES_DIR

    def list_assets(self) -> list[str]:
        if not self.theses_dir.exists():
            return []
        return sorted(
            f.stem for f in self.theses_dir.glob("*.jsonl") if f.is_file()
        )

    def get_all_versions(self, asset: str) -> list[dict[str, Any]]:
        path = self.theses_dir / f"{asset}.jsonl"
        if not path.exists():
            return []
        out: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def get_authoritative_version(self, asset: str) -> dict[str, Any] | None:
        """Returns the authoritative event for the asset, with three states:
        (1) None — no thesis ever, OR position closed via
            `thesis_closed_position` (terminal). Closed positions deactivate
            their override annotation regardless of `user_override_active`.
        (2) `thesis_user_override_annotation` — user override is active and
            the position is still held.
        (3) Latest `thesis` / `thesis_review` event."""
        versions = self.get_all_versions(asset)
        if not versions:
            return None
        # Closed-position event is terminal — supersedes everything.
        if any(
            v.get("event_type") == "thesis_closed_position" for v in versions
        ):
            return None
        override = next(
            (
                v
                for v in reversed(versions)
                if v.get("event_type") == "thesis_user_override_annotation"
                and v.get("user_override_active")
            ),
            None,
        )
        if override:
            return override
        thesis_events = [
            v
            for v in versions
            if v.get("event_type") in ("thesis", "thesis_review")
        ]
        if thesis_events:
            return thesis_events[-1]
        return versions[-1]

    def get_closed_assets(self) -> list[str]:
        """Returns sorted list of tickers whose latest history contains a
        `thesis_closed_position` event. Used to filter the dashboard's
        recommendation feed and to mark theses as no-longer-authoritative
        in audit trails."""
        out: list[str] = []
        for asset in self.list_assets():
            versions = self.get_all_versions(asset)
            if any(
                v.get("event_type") == "thesis_closed_position"
                for v in versions
            ):
                out.append(asset)
        return sorted(out)

    def is_closed(self, asset: str) -> bool:
        """True if the asset has a `thesis_closed_position` event in its
        history. Closed status is terminal: a re-open requires a fresh
        thesis event."""
        return asset in self.get_closed_assets()

    def get_latest_thesis_only(self, asset: str) -> dict[str, Any] | None:
        """Returns the latest `thesis` (or `thesis_review`) event,
        ignoring overrides. Useful when the dashboard needs to show what
        the system actually concluded even when the user overrode it."""
        versions = self.get_all_versions(asset)
        thesis_events = [
            v
            for v in versions
            if v.get("event_type") in ("thesis", "thesis_review")
        ]
        return thesis_events[-1] if thesis_events else None

    @staticmethod
    def thesis_version_label(thesis: dict[str, Any]) -> str:
        return (
            thesis.get("version")
            or thesis.get("model_version")
            or thesis.get("thesis_version")
            or thesis.get("event_type", "thesis")
        )

    @staticmethod
    def thesis_summary_text(thesis: dict[str, Any]) -> str:
        """Best-effort narrative for the 'Tesis vigente' card. Pulls
        from `note` (override), then `confidence_justification`, then
        first `must_be_true` clause, then `reasoning`."""
        for key in ("note", "confidence_justification", "reasoning"):
            v = thesis.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        mbt = thesis.get("must_be_true") or []
        if mbt:
            first = mbt[0]
            if isinstance(first, dict):
                for k in ("claim", "statement", "text", "description"):
                    v = first.get(k)
                    if isinstance(v, str) and v.strip():
                        return v.strip()
            elif isinstance(first, str):
                return first.strip()
        return "Sin resumen disponible. Revisa el evento bruto en el JSONL."

    def get_falsifier_status(
        self, thesis: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Normalize the heterogeneous `falsifier_status_audit` payload
        into a uniform list of {name, status, threshold, current, note}.
        Handles dict-of-dicts, list, or plain string."""
        fsa = thesis.get("falsifier_status_audit")
        if not fsa:
            for alt in ("falsifiers", "would_falsify", "falsifier_clauses"):
                if alt in thesis:
                    fsa = thesis[alt]
                    break
        out: list[dict[str, Any]] = []
        if isinstance(fsa, dict):
            for name, det in fsa.items():
                if isinstance(det, dict):
                    threshold = (
                        det.get("v2_threshold")
                        or det.get("threshold")
                        or det.get("required")
                        or ""
                    )
                    # Pick the most informative numeric/current field.
                    current = ""
                    for k in (
                        "current",
                        "current_value",
                        "actual",
                    ):
                        if k in det:
                            current = str(det[k])
                            break
                    if not current:
                        # Pick the first numeric field that looks like a
                        # measurement reading.
                        for k, v in det.items():
                            if k in {
                                "v2_threshold",
                                "threshold",
                                "status",
                                "note",
                                "required_for_activation",
                            }:
                                continue
                            if isinstance(v, (int, float)):
                                current = f"{k}={v}"
                                break
                    out.append(
                        {
                            "name": name,
                            "status": det.get("status", "unknown"),
                            "threshold": threshold,
                            "current": current,
                            "note": det.get("note", ""),
                        }
                    )
                else:
                    out.append(
                        {
                            "name": name,
                            "status": "unknown",
                            "threshold": "",
                            "current": "",
                            "note": str(det),
                        }
                    )
        elif isinstance(fsa, list):
            for item in fsa:
                if isinstance(item, dict):
                    out.append(
                        {
                            "name": item.get(
                                "name", item.get("clause", "?")
                            ),
                            "status": item.get("status", "unknown"),
                            "threshold": item.get("threshold", ""),
                            "current": item.get("current", ""),
                            "note": item.get("note", ""),
                        }
                    )
                elif isinstance(item, str):
                    out.append(
                        {
                            "name": item,
                            "status": "unknown",
                            "threshold": "",
                            "current": "",
                            "note": "",
                        }
                    )
        return out
