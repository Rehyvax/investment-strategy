"""Tests for `dashboard/services/thesis_browser.py`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dashboard"))

from services.thesis_browser import ThesisBrowser  # noqa: E402


def _seed_theses(tmp_path: Path) -> Path:
    theses = tmp_path / "theses"
    theses.mkdir()
    # MSFT — single thesis, no closure
    (theses / "MSFT.jsonl").write_text(
        json.dumps(
            {
                "event_type": "thesis",
                "ticker": "MSFT",
                "timestamp": "2026-05-11T14:00:00Z",
                "recommendation": "watch",
                "confidence_calibrated": 0.65,
                "thesis_version": "v1",
            }
        ) + "\n",
        encoding="utf-8",
    )
    # MELI — v1 then v3 review (latest), with halfway falsifier
    (theses / "MELI.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event_type": "thesis",
                        "ticker": "MELI",
                        "timestamp": "2026-05-11T15:00:00Z",
                        "recommendation": "watch",
                        "confidence_calibrated": 0.62,
                    }
                ),
                json.dumps(
                    {
                        "event_type": "thesis",
                        "ticker": "MELI",
                        "timestamp": "2026-05-14T10:00:00Z",
                        "recommendation": "watch",
                        "confidence_calibrated": 0.48,
                        "thesis_version": "v3_post_Q1_2026",
                        "falsifier_status_audit": {
                            "f1": {"status": "halfway_activated"},
                        },
                    }
                ),
            ]
        ) + "\n",
        encoding="utf-8",
    )
    # AXON — thesis then closed
    (theses / "AXON.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event_type": "thesis",
                        "ticker": "AXON",
                        "timestamp": "2026-05-14T13:00:00Z",
                        "recommendation": "exit",
                        "confidence_calibrated": 0.55,
                    }
                ),
                json.dumps(
                    {
                        "event_type": "thesis_user_override_annotation",
                        "ticker": "AXON",
                        "timestamp": "2026-05-14T14:00:00Z",
                        "user_override_active": True,
                    }
                ),
                json.dumps(
                    {
                        "event_type": "thesis_closed_position",
                        "ticker": "AXON",
                        "timestamp": "2026-05-14T23:30:00Z",
                    }
                ),
            ]
        ) + "\n",
        encoding="utf-8",
    )
    return theses


def _seed_snapshot(tmp_path: Path) -> Path:
    snaps = tmp_path / "snaps"
    snaps.mkdir()
    snap = {
        "as_of_date": "2026-05-14",
        "positions": [
            {
                "ticker": "MSFT",
                "sector_at_purchase": "Technology",
                "country_at_purchase": "United States",
            },
            {
                "ticker": "MELI",
                "sector_at_purchase": "Consumer",
                "country_at_purchase": "Argentina",
            },
            # AXON not in snapshot → unknown sector/country
        ],
    }
    (snaps / "2026-05-14.json").write_text(json.dumps(snap), encoding="utf-8")
    return snaps


def _make(tmp_path: Path) -> ThesisBrowser:
    return ThesisBrowser(
        theses_dir=_seed_theses(tmp_path),
        snapshots_dir=_seed_snapshot(tmp_path),
    )


# ---------------------------------------------------------------------------
class TestListAssets:
    def test_groups_by_ticker(self, tmp_path):
        b = _make(tmp_path)
        assets = b.list_all_assets_with_theses()
        tickers = {a["ticker"] for a in assets}
        assert tickers == {"MSFT", "MELI", "AXON"}

    def test_marks_closed(self, tmp_path):
        b = _make(tmp_path)
        axon = next(
            a for a in b.list_all_assets_with_theses() if a["ticker"] == "AXON"
        )
        assert axon["status"] == "closed"
        assert axon["is_closed"] is True

    def test_marks_halfway(self, tmp_path):
        b = _make(tmp_path)
        meli = next(
            a for a in b.list_all_assets_with_theses() if a["ticker"] == "MELI"
        )
        assert meli["status"] == "halfway_active"
        assert meli["has_halfway_falsifier"] is True

    def test_resolves_sector_country_from_snapshot(self, tmp_path):
        b = _make(tmp_path)
        msft = next(
            a for a in b.list_all_assets_with_theses() if a["ticker"] == "MSFT"
        )
        assert msft["sector"] == "Technology"
        assert msft["country"] == "United States"
        # AXON not in snapshot → unknown
        axon = next(
            a for a in b.list_all_assets_with_theses() if a["ticker"] == "AXON"
        )
        assert axon["sector"] == "unknown"


class TestTimeline:
    def test_chronological_order(self, tmp_path):
        b = _make(tmp_path)
        timeline = b.get_timeline("AXON")
        timestamps = [e["timestamp"] for e in timeline]
        assert timestamps == sorted(timestamps)
        assert len(timeline) == 3
        assert timeline[-1]["event_type"] == "thesis_closed_position"


class TestFilters:
    def test_filter_by_status(self, tmp_path):
        b = _make(tmp_path)
        out = b.filter_assets(status="closed")
        assert {a["ticker"] for a in out} == {"AXON"}

    def test_filter_by_recommendation(self, tmp_path):
        b = _make(tmp_path)
        out = b.filter_assets(recommendation="watch")
        # MSFT + MELI are watch; AXON authoritative is exit
        assert {a["ticker"] for a in out} == {"MSFT", "MELI"}

    def test_filter_by_search_query_substring(self, tmp_path):
        b = _make(tmp_path)
        out = b.filter_assets(search_query="me")
        assert {a["ticker"] for a in out} == {"MELI"}

    def test_get_distinct_values_excludes_unknown(self, tmp_path):
        b = _make(tmp_path)
        sectors = b.get_distinct_values("sector")
        assert "unknown" not in sectors
        assert "Technology" in sectors
        assert "Consumer" in sectors


class TestEdge:
    def test_handles_empty_theses_dir(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        b = ThesisBrowser(theses_dir=empty, snapshots_dir=tmp_path)
        assert b.list_all_assets_with_theses() == []
        assert b.filter_assets() == []
        assert b.get_distinct_values("status") == []
