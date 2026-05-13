"""Snapshot rebuilder, supersession-aware (CLAUDE.md §2.2.1).

Rebuilds a portfolio snapshot from the event stream while honoring
`system_correction` supersessions recorded in `data/events/runs.jsonl`.

Source-of-truth model
---------------------
The JSONL streams are immutable. Corrections never mutate prior events;
they are appended as `system_correction` events. Consumers (this module
included) MUST apply supersessions on replay.

correction_types handled
------------------------
- deployment_unwind: every event_id referenced in `events_unwound` /
  `events_unwound_v2` is treated as superseded. Entries may be free-text
  strings; event_ids are pulled by regex, with a fallback to resolve
  "<file> lines N-M" patterns by reading the referenced file.
- duplicate_event_reconciliation: only entries whose
  `status_post_reconciliation` starts with "superseded" are filtered.

All other correction_types (cross_reference_clarification,
agent_threshold_revision, screening_*_supersession, charter_*,
timestamp_realignment, algorithm_bug_in_capping_routine,
value_magic_formula_screening_buggy_v1_superseded,
user_override_thesis_recommendation, regime_*) are non-trade-level
and skipped for snapshot purposes.

Trade event schema
------------------
Encountered shapes in the event stream:
- `event_type: "cash"` with `trade_kind: "initial_cash"` — sets starting EUR cash.
- `event_type: "trade"` with `trade_kind: "initial_position"` — imports a
  prior holding at T0; declares quantity + cost basis WITHOUT consuming cash
  (these positions were already paid for outside the lab's books).
- `event_type: "trade"` with `side: "buy"` — consumes cash by `total_cost_eur`
  (preferred; falls back to `gross_value_eur`).
- `event_type: "trade"` with `side: "sell"` — credits cash by `proceeds_eur`
  (preferred; falls back to `gross_value_eur`). Consumes shares from FIFO lots
  (simplified proportional cost basis for now).
- `event_type: "operating_cost_reconciliation"` — AUTHORITATIVELY overrides
  the computed cash with `authoritative_cash_post_trades_eur` (broker-truth).

Mark-to-market
--------------
yfinance on-demand (Option A in design). Per-rebuild in-memory cache.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

ROOT = Path(__file__).resolve().parents[2]
RUNS_PATH = ROOT / "data" / "events" / "runs.jsonl"
TRADES_DIR = ROOT / "data" / "events" / "portfolios"
SNAPSHOTS_DIR = ROOT / "data" / "snapshots"

# Event IDs in this lab are 26-char Crockford base32 ULIDs (e.g.
# "01KRBP168SSRVDY9MT4CC6TBK3") plus some value-portfolio variants that
# don't begin with "01" (e.g. "71PGHWMQ995JV11433ZWDJT438"). Use a
# generic 26-char [0-9A-Z] match bounded by non-alphanum to avoid
# capturing arbitrary uppercase words from prose.
_EVENT_ID_RE = re.compile(r"(?<![0-9A-Z])[0-9A-Z]{26}(?![0-9A-Z])")
_LINE_RANGE_RE = re.compile(r"lines?\s+(\d+)\s*[-–]\s*(\d+)")
_TRADES_PATH_RE = re.compile(r"([a-zA-Z_]+)/trades\.jsonl")


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


@dataclass
class Position:
    ticker: str
    isin: str | None = None
    currency: str = "USD"
    exchange: str | None = None
    yf_symbol: str | None = None
    quantity: float = 0.0
    cost_basis_eur: float = 0.0
    cost_basis_native: float = 0.0
    # mark-to-market fields populated by _mark_to_market
    current_price_native: float | None = None
    current_value_eur: float | None = None
    unrealized_pnl_eur: float | None = None
    price_error: str | None = None


# Map exchange labels seen in events to yfinance suffixes when an
# explicit yf_symbol / yf_ticker_used field is not present.
_EXCHANGE_SUFFIX = {
    "XETRA": ".DE",
    "LSE": ".L",
    "London_Stock_Exchange": ".L",
    "Euronext_AMS": ".AS",
    "XAMS": ".AS",
    "Euronext_PAR": ".PA",
    "Euronext_BRU": ".BR",
    "Euronext_LIS": ".LS",
    "Borsa_Italiana": ".MI",
    "BME": ".MC",
    "SIX_Swiss": ".SW",
    "Copenhagen_OMX": ".CO",
    "Nasdaq_Baltic": ".HE",
}


def _derive_yf_symbol(ticker: str, exchange: str | None) -> str:
    if not exchange:
        return ticker
    suf = _EXCHANGE_SUFFIX.get(exchange)
    if suf and not ticker.endswith(suf):
        return f"{ticker}{suf}"
    return ticker


@dataclass
class RebuildResult:
    portfolio_id: str
    as_of_date: str
    cash_eur: float
    cash_source: str
    positions: list[Position]
    nav_total_eur: float
    equity_value_total_eur: float
    cost_basis_total_eur: float
    unrealized_pnl_total_eur: float
    fx_rate_usd_per_eur: float | None
    fx_rate_date: str | None
    superseded_event_ids: set[str] = field(default_factory=set)
    construction_method: str = "rebuilder_v1_supersession_aware"

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio_id": self.portfolio_id,
            "as_of_date": self.as_of_date,
            "as_of_ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "currency_base": "EUR",
            "fx_rate_usd_per_eur": self.fx_rate_usd_per_eur,
            "fx_rate_date": self.fx_rate_date,
            "positions": [
                {
                    "ticker": p.ticker,
                    "isin": p.isin,
                    "exchange": p.exchange,
                    "currency": p.currency,
                    "quantity": p.quantity,
                    "cost_basis_native": round(p.cost_basis_native, 6),
                    "cost_basis_eur": round(p.cost_basis_eur, 6),
                    "current_price_native": p.current_price_native,
                    "current_value_eur": (
                        round(p.current_value_eur, 4)
                        if p.current_value_eur is not None
                        else None
                    ),
                    "unrealized_pnl_eur": (
                        round(p.unrealized_pnl_eur, 4)
                        if p.unrealized_pnl_eur is not None
                        else None
                    ),
                    **({"price_error": p.price_error} if p.price_error else {}),
                }
                for p in self.positions
            ],
            "cash_eur": round(self.cash_eur, 4),
            "cash_source": self.cash_source,
            "equity_value_total_eur": round(self.equity_value_total_eur, 4),
            "cost_basis_total_eur": round(self.cost_basis_total_eur, 4),
            "nav_total_eur": round(self.nav_total_eur, 4),
            "unrealized_pnl_total_eur": round(self.unrealized_pnl_total_eur, 4),
            "positions_count": len(self.positions),
            "snapshot_construction_method": self.construction_method,
            "supersession_filter_applied": True,
            "superseded_event_ids_applied_count": len(self.superseded_event_ids),
        }


class SnapshotRebuilder:
    def __init__(
        self,
        portfolio_id: str,
        as_of_date: date,
        out_dir: Path | None = None,
        dry_run: bool = False,
        runs_path: Path | None = None,
        trades_dir: Path | None = None,
    ):
        self.portfolio_id = portfolio_id
        self.as_of_date = as_of_date
        self.dry_run = dry_run
        self.runs_path = runs_path or RUNS_PATH
        self.trades_dir = trades_dir or TRADES_DIR
        self.out_dir = out_dir or (SNAPSHOTS_DIR / portfolio_id)
        self._price_cache: dict[tuple[str, str], float] = {}
        self._fx_cache: dict[tuple[str, str], float] = {}

    # ------------------------------------------------------------------
    # Supersession pre-pass
    # ------------------------------------------------------------------
    def _trades_path_for(self, portfolio_id: str) -> Path:
        return self.trades_dir / portfolio_id / "trades.jsonl"

    def _read_event_ids_at_lines(
        self, path: Path, start: int, end: int
    ) -> set[str]:
        ids: set[str] = set()
        if not path.exists():
            return ids
        with path.open("r", encoding="utf-8") as fp:
            for i, line in enumerate(fp, start=1):
                if i < start:
                    continue
                if i > end:
                    break
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                eid = e.get("event_id")
                if isinstance(eid, str):
                    ids.add(eid)
        return ids

    def _extract_event_ids_from_entry(self, entry: Any) -> set[str]:
        if isinstance(entry, str):
            ids = set(_EVENT_ID_RE.findall(entry))
            if ids:
                return ids
            # Fallback: parse "<portfolio>/trades.jsonl lines N-M".
            path_m = _TRADES_PATH_RE.search(entry)
            range_m = _LINE_RANGE_RE.search(entry)
            if path_m and range_m:
                portfolio = path_m.group(1)
                start = int(range_m.group(1))
                end = int(range_m.group(2))
                return self._read_event_ids_at_lines(
                    self._trades_path_for(portfolio), start, end
                )
            return set()
        if isinstance(entry, dict):
            ids: set[str] = set()
            for v in entry.values():
                if isinstance(v, str):
                    ids.update(_EVENT_ID_RE.findall(v))
            eid = entry.get("event_id")
            if isinstance(eid, str):
                ids.add(eid)
            return ids
        return set()

    def _collect_superseded_event_ids(self) -> set[str]:
        superseded: set[str] = set()
        for event in _iter_jsonl(self.runs_path):
            if event.get("event_type") != "system_correction":
                continue
            ct = event.get("correction_type", "")
            if ct == "deployment_unwind":
                for u in event.get("events_unwound", []):
                    superseded.update(self._extract_event_ids_from_entry(u))
                for u in event.get("events_unwound_v2", []):
                    superseded.update(self._extract_event_ids_from_entry(u))
            elif ct == "duplicate_event_reconciliation":
                for entry in event.get("affected_events", []):
                    if not isinstance(entry, dict):
                        continue
                    status = entry.get("status_post_reconciliation", "")
                    if isinstance(status, str) and status.startswith("superseded"):
                        eid = entry.get("event_id")
                        if isinstance(eid, str):
                            superseded.add(eid)
            # All other correction_types do not unwind trade-level events.
        return superseded

    # ------------------------------------------------------------------
    # Trade applier
    # ------------------------------------------------------------------
    @staticmethod
    def _buy_cash_outflow(trade: dict[str, Any]) -> float:
        for k in ("total_cost_eur", "gross_value_eur", "cost_basis_eur"):
            v = trade.get(k)
            if isinstance(v, (int, float)):
                return float(v)
        return 0.0

    @staticmethod
    def _sell_cash_inflow(trade: dict[str, Any]) -> float:
        for k in ("proceeds_eur", "net_proceeds_eur", "gross_value_eur"):
            v = trade.get(k)
            if isinstance(v, (int, float)):
                return float(v)
        return 0.0

    def _apply_event(
        self,
        positions: dict[str, Position],
        state: dict[str, Any],
        event: dict[str, Any],
    ) -> None:
        etype = event.get("event_type")
        if etype == "cash":
            if event.get("trade_kind") == "initial_cash":
                state["cash_eur"] += float(event.get("amount_eur", 0.0))
                state["cash_source"] = "initial_cash_event"
        elif etype == "trade":
            tkind = event.get("trade_kind")
            side = event.get("side")
            ticker = event.get("ticker")
            if not ticker:
                return
            isin = event.get("isin")
            currency = event.get("currency", "USD")
            exchange = event.get("exchange")
            quantity = float(event.get("quantity", 0.0))
            if tkind in ("initial_position", "benchmark_initial_allocation"):
                # Imported holding at T0: declare quantity + cost basis, no cash change.
                cost_basis_eur = float(event.get("cost_basis_eur", 0.0))
                cost_basis_native = float(event.get("cost_basis_native", 0.0))
                yf_symbol = event.get("yf_ticker_used") or event.get("yf_symbol")
                pos = positions.setdefault(
                    ticker,
                    Position(
                        ticker=ticker,
                        isin=isin,
                        currency=currency,
                        exchange=exchange,
                        yf_symbol=yf_symbol,
                    ),
                )
                pos.quantity += quantity
                pos.cost_basis_eur += cost_basis_eur
                pos.cost_basis_native += cost_basis_native
                if not pos.yf_symbol and yf_symbol:
                    pos.yf_symbol = yf_symbol
                # initial_position is a position declaration only; do not touch cash.
                return
            if side == "buy":
                cash_out = self._buy_cash_outflow(event)
                state["cash_eur"] -= cash_out
                # cost basis for the lot: prefer cost_basis_eur_total, then total_cost_eur,
                # then gross_value_eur. Native total via gross_value_native if present.
                cost_basis_eur = float(
                    event.get(
                        "cost_basis_eur_total",
                        event.get(
                            "total_cost_eur",
                            event.get("gross_value_eur", 0.0),
                        ),
                    )
                )
                cost_basis_native = float(event.get("gross_value_native", 0.0))
                yf_symbol = event.get("yf_symbol") or event.get("yf_ticker_used")
                pos = positions.setdefault(
                    ticker,
                    Position(
                        ticker=ticker,
                        isin=isin,
                        currency=currency,
                        exchange=exchange,
                        yf_symbol=yf_symbol,
                    ),
                )
                pos.quantity += quantity
                pos.cost_basis_eur += cost_basis_eur
                pos.cost_basis_native += cost_basis_native
                if not pos.yf_symbol and yf_symbol:
                    pos.yf_symbol = yf_symbol
                return
            if side == "sell":
                cash_in = self._sell_cash_inflow(event)
                state["cash_eur"] += cash_in
                pos = positions.get(ticker)
                if pos is None or pos.quantity <= 0:
                    # Sell without prior position — log but don't crash.
                    state.setdefault("warnings", []).append(
                        f"SELL {ticker} but no open position; event {event.get('event_id')}"
                    )
                    return
                qty_sold = quantity
                # Simplified FIFO: proportional cost basis consumption.
                if pos.quantity > 0:
                    ratio = min(qty_sold / pos.quantity, 1.0)
                    pos.cost_basis_eur *= 1.0 - ratio
                    pos.cost_basis_native *= 1.0 - ratio
                pos.quantity -= qty_sold
                if pos.quantity <= 1e-9:
                    pos.quantity = 0.0
                return
        elif etype == "operating_cost_reconciliation":
            auth = event.get("authoritative_cash_post_trades_eur")
            if isinstance(auth, (int, float)):
                state["cash_eur"] = float(auth)
                state["cash_source"] = "broker_reported_authoritative"

    # ------------------------------------------------------------------
    # Mark-to-market
    # ------------------------------------------------------------------
    def _get_eod_price(
        self, ticker: str, yf_symbol: str | None, as_of: date
    ) -> float | None:
        symbol = yf_symbol or ticker
        key = (symbol, as_of.isoformat())
        if key in self._price_cache:
            return self._price_cache[key]
        try:
            import yfinance as yf  # local import: heavy dep
        except ImportError:
            return None
        try:
            t = yf.Ticker(symbol)
            # Pull a small window around as_of_date to be tolerant of weekends/holidays.
            start = as_of.toordinal() - 5
            from datetime import date as _date

            start_date = _date.fromordinal(start)
            end_date = _date.fromordinal(as_of.toordinal() + 1)
            hist = t.history(
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                auto_adjust=True,
            )
            if hist.empty:
                return None
            # Pick the row whose date <= as_of, latest.
            dates = [d.date() for d in hist.index]
            valid = [(d, hist.iloc[i]["Close"]) for i, d in enumerate(dates) if d <= as_of]
            if not valid:
                return None
            price = float(valid[-1][1])
            self._price_cache[key] = price
            return price
        except Exception:
            return None

    def _get_fx_usd_per_eur(self, as_of: date) -> float | None:
        key = ("EURUSD=X", as_of.isoformat())
        if key in self._fx_cache:
            return self._fx_cache[key]
        try:
            import yfinance as yf
        except ImportError:
            return None
        try:
            t = yf.Ticker("EURUSD=X")
            from datetime import date as _date

            start_date = _date.fromordinal(as_of.toordinal() - 5)
            end_date = _date.fromordinal(as_of.toordinal() + 1)
            hist = t.history(
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                auto_adjust=False,
            )
            if hist.empty:
                return None
            dates = [d.date() for d in hist.index]
            valid = [(d, hist.iloc[i]["Close"]) for i, d in enumerate(dates) if d <= as_of]
            if not valid:
                return None
            fx = float(valid[-1][1])
            self._fx_cache[key] = fx
            return fx
        except Exception:
            return None

    def _get_fx_pair(self, pair: str, as_of: date) -> float | None:
        # pair example: "GBPEUR=X", "DKKEUR=X". Returns units of EUR per 1 unit of native.
        # We'll fetch native/EUR rate via yfinance ticker "<NATIVE>EUR=X" which gives EUR per native.
        key = (pair, as_of.isoformat())
        if key in self._fx_cache:
            return self._fx_cache[key]
        try:
            import yfinance as yf
        except ImportError:
            return None
        try:
            t = yf.Ticker(pair)
            from datetime import date as _date

            start_date = _date.fromordinal(as_of.toordinal() - 7)
            end_date = _date.fromordinal(as_of.toordinal() + 1)
            hist = t.history(
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                auto_adjust=False,
            )
            if hist.empty:
                return None
            dates = [d.date() for d in hist.index]
            valid = [(d, hist.iloc[i]["Close"]) for i, d in enumerate(dates) if d <= as_of]
            if not valid:
                return None
            fx = float(valid[-1][1])
            self._fx_cache[key] = fx
            return fx
        except Exception:
            return None

    def _native_to_eur(self, currency: str, as_of: date) -> float | None:
        """Returns EUR per 1 unit of <currency>. None if unknown."""
        if currency == "EUR":
            return 1.0
        if currency == "USD":
            # Need USD->EUR. EURUSD=X gives USD per EUR; invert.
            usd_per_eur = self._get_fx_usd_per_eur(as_of)
            if usd_per_eur and usd_per_eur > 0:
                return 1.0 / usd_per_eur
            return None
        # Generic: try <CCY>EUR=X.
        pair = f"{currency}EUR=X"
        return self._get_fx_pair(pair, as_of)

    def _mark_to_market(self, positions: dict[str, Position]) -> None:
        for pos in positions.values():
            if pos.quantity <= 0:
                continue
            yf_sym = pos.yf_symbol or _derive_yf_symbol(pos.ticker, pos.exchange)
            price = self._get_eod_price(pos.ticker, yf_sym, self.as_of_date)
            if price is None:
                pos.price_error = f"no_price_for_{yf_sym}_on_{self.as_of_date}"
                continue
            pos.current_price_native = price
            value_native = price * pos.quantity
            fx = self._native_to_eur(pos.currency, self.as_of_date)
            if fx is None:
                pos.price_error = (
                    f"no_fx_for_{pos.currency}_on_{self.as_of_date}"
                )
                continue
            pos.current_value_eur = value_native * fx
            pos.unrealized_pnl_eur = pos.current_value_eur - pos.cost_basis_eur

    # ------------------------------------------------------------------
    # Main rebuild
    # ------------------------------------------------------------------
    def rebuild(self) -> RebuildResult:
        superseded = self._collect_superseded_event_ids()
        positions: dict[str, Position] = {}
        state: dict[str, Any] = {
            "cash_eur": 0.0,
            "cash_source": "no_initial_cash_event",
            "warnings": [],
        }

        trades_path = self._trades_path_for(self.portfolio_id)
        events = list(_iter_jsonl(trades_path))
        # Sort by timestamp ascending so deterministic replay; original file
        # order is already chronological but we re-sort for safety.
        events.sort(key=lambda e: e.get("ts", ""))

        for event in events:
            # Filter by trade_date <= as_of_date when present (operate at EOD).
            tdate = event.get("trade_date")
            if isinstance(tdate, str) and tdate > self.as_of_date.isoformat():
                continue
            if event.get("event_id") in superseded:
                continue
            self._apply_event(positions, state, event)

        active_positions = [p for p in positions.values() if p.quantity > 0]
        self._mark_to_market({p.ticker: p for p in active_positions})

        # Recompute USD/EUR for snapshot header (informational only).
        usd_per_eur = self._get_fx_usd_per_eur(self.as_of_date)

        equity_value_total_eur = sum(
            (p.current_value_eur or 0.0) for p in active_positions
        )
        cost_basis_total_eur = sum(p.cost_basis_eur for p in active_positions)
        nav_total_eur = state["cash_eur"] + equity_value_total_eur
        unrealized_pnl_total_eur = equity_value_total_eur - cost_basis_total_eur

        result = RebuildResult(
            portfolio_id=self.portfolio_id,
            as_of_date=self.as_of_date.isoformat(),
            cash_eur=state["cash_eur"],
            cash_source=state["cash_source"],
            positions=active_positions,
            nav_total_eur=nav_total_eur,
            equity_value_total_eur=equity_value_total_eur,
            cost_basis_total_eur=cost_basis_total_eur,
            unrealized_pnl_total_eur=unrealized_pnl_total_eur,
            fx_rate_usd_per_eur=usd_per_eur,
            fx_rate_date=self.as_of_date.isoformat() if usd_per_eur else None,
            superseded_event_ids=superseded,
        )

        if not self.dry_run:
            self._write_atomic(result)
        return result

    def _write_atomic(self, result: RebuildResult) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"{self.as_of_date.isoformat()}.json"
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fp:
            json.dump(result.to_dict(), fp, indent=2, sort_keys=True)
        os.replace(tmp, path)


# ----------------------------------------------------------------------
# CLI entry point
# ----------------------------------------------------------------------
ALL_PORTFOLIOS = (
    "real",
    "shadow",
    "aggressive",
    "conservative",
    "value",
    "momentum",
    "quality",
    "benchmark_passive",
    "robo_advisor",
)


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Rebuild portfolio snapshot(s).")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--portfolio", type=str, help="portfolio_id")
    g.add_argument("--all", action="store_true", help="rebuild all 9 portfolios")
    p.add_argument(
        "--date",
        type=_parse_date,
        default=date.today(),
        help="YYYY-MM-DD as-of date (default: today)",
    )
    p.add_argument("--out-dir", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    targets = ALL_PORTFOLIOS if args.all else (args.portfolio,)
    for pid in targets:
        rb = SnapshotRebuilder(
            pid,
            args.date,
            out_dir=args.out_dir / pid if args.out_dir else None,
            dry_run=args.dry_run,
        )
        result = rb.rebuild()
        print(
            f"{pid} {args.date.isoformat()} "
            f"NAV={result.nav_total_eur:,.2f} EUR "
            f"cash={result.cash_eur:,.2f} "
            f"pos={len(result.positions)} "
            f"superseded_applied={len(result.superseded_event_ids)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
