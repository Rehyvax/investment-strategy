"""Local point-in-time price log for deterministic mark-to-market.

Resolves tech debt #4 (opened 2026-05-14) — snapshot rebuilder v1 used
yfinance on-demand which produces fresh prices that differ from values
stored in snapshot fixtures.

Persistence model
-----------------
- Append-only JSONL at data/events/prices/YYYY-MM.jsonl (gitignored).
- Two event types share the file:
  * "price_eod" (existing schema, preserved verbatim):
      {event_type, ts, ticker, currency, close, previous_close,
       intraday_pct, source, as_of_date}
  * "fx_eod" (new): EUR-base FX, one row per (date, native_currency):
      {event_type, ts, as_of_date, native_currency, native_per_eur,
       source, fetched_ts}

Lookups
-------
- PriceLog.get_price(ticker, as_of_date) returns the most recent
  price_eod whose as_of_date <= the request, marking the result with
  `data_quality = "exact"` or `data_quality = "stale_fallback"` so
  callers can detect when they are reading a carried-forward price.
- PriceLog.get_fx(native_currency, as_of_date) follows the same rule.

CLI
---
- python -m src.portfolios.price_log --backfill --start YYYY-MM-DD \
      --end YYYY-MM-DD --tickers <comma-separated>
- python -m src.portfolios.price_log --daily-fetch --date YYYY-MM-DD \
      --tickers <comma-separated>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG_DIR = ROOT / "data" / "events" / "prices"

# Exchange suffix → yfinance symbol convention. Mirrors the same map in
# snapshot.py so PriceFetcher can resolve "EUNH" + "XETRA" → "EUNH.DE".
EXCHANGE_SUFFIX = {
    "XETRA": ".DE",
    "LSE": ".L",
    "London_Stock_Exchange": ".L",
    "Euronext_AMS": ".AS",
    "EURONEXT_AMS": ".AS",
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


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def derive_yf_symbol(ticker: str, exchange: str | None) -> str:
    if not exchange:
        return ticker
    suf = EXCHANGE_SUFFIX.get(exchange)
    if suf and not ticker.endswith(suf):
        return f"{ticker}{suf}"
    return ticker


@dataclass(frozen=True)
class PriceRecord:
    ticker: str
    as_of_date: str  # ISO YYYY-MM-DD
    close: float
    currency: str
    source: str
    data_quality: str  # "exact" | "stale_fallback"


@dataclass(frozen=True)
class FxRecord:
    native_currency: str
    as_of_date: str
    native_per_eur: float
    source: str
    data_quality: str


class PriceLog:
    def __init__(self, log_dir: Path | None = None):
        self.log_dir = log_dir or DEFAULT_LOG_DIR

    # ------------------------------------------------------------------
    # IO helpers
    # ------------------------------------------------------------------
    def _month_path(self, d: date) -> Path:
        return self.log_dir / f"{d.year:04d}-{d.month:02d}.jsonl"

    def _months_covering(self, start: date, end: date) -> list[Path]:
        seen: list[Path] = []
        y, m = start.year, start.month
        while (y, m) <= (end.year, end.month):
            p = self.log_dir / f"{y:04d}-{m:02d}.jsonl"
            if p.exists():
                seen.append(p)
            m += 1
            if m > 12:
                m = 1
                y += 1
        return seen

    def _iter_jsonl(self, path: Path) -> Iterator[dict]:
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------
    def get_price(self, ticker: str, as_of_date: date) -> PriceRecord | None:
        """Returns the most recent price_eod for `ticker` with
        as_of_date <= request. Falls back across month files. Tags result
        as 'exact' when date matches, 'stale_fallback' otherwise."""
        best: dict | None = None
        target = as_of_date.isoformat()
        # Look up the current and prior months. Two months back is enough
        # for any realistic stale_fallback window (4–8 weeks).
        for m_offset in range(0, 3):
            y, m = as_of_date.year, as_of_date.month - m_offset
            while m <= 0:
                m += 12
                y -= 1
            p = self.log_dir / f"{y:04d}-{m:02d}.jsonl"
            for event in self._iter_jsonl(p):
                if event.get("event_type") != "price_eod":
                    continue
                if event.get("ticker") != ticker:
                    continue
                d = event.get("as_of_date") or event.get("date")
                if not isinstance(d, str) or d > target:
                    continue
                if best is None or d > (
                    best.get("as_of_date") or best.get("date") or ""
                ):
                    best = event
            if best is not None:
                # Stop early if exact match found
                bd = best.get("as_of_date") or best.get("date")
                if bd == target:
                    break
        if best is None:
            return None
        bd = best.get("as_of_date") or best.get("date") or ""
        return PriceRecord(
            ticker=ticker,
            as_of_date=bd,
            close=float(best["close"]),
            currency=best.get("currency", "USD"),
            source=best.get("source", "yfinance"),
            data_quality="exact" if bd == target else "stale_fallback",
        )

    def get_fx(self, native_currency: str, as_of_date: date) -> FxRecord | None:
        """Returns native-per-EUR FX. e.g. native_currency='USD' →
        native_per_eur=1.1738 means 1 EUR = 1.1738 USD."""
        if native_currency == "EUR":
            return FxRecord("EUR", as_of_date.isoformat(), 1.0, "identity", "exact")
        target = as_of_date.isoformat()
        best: dict | None = None
        for m_offset in range(0, 3):
            y, m = as_of_date.year, as_of_date.month - m_offset
            while m <= 0:
                m += 12
                y -= 1
            p = self.log_dir / f"{y:04d}-{m:02d}.jsonl"
            for event in self._iter_jsonl(p):
                if event.get("event_type") != "fx_eod":
                    continue
                if event.get("native_currency") != native_currency:
                    continue
                d = event.get("as_of_date")
                if not isinstance(d, str) or d > target:
                    continue
                if best is None or d > best.get("as_of_date", ""):
                    best = event
            if best is not None and best.get("as_of_date") == target:
                break
        if best is None:
            return None
        return FxRecord(
            native_currency=native_currency,
            as_of_date=best["as_of_date"],
            native_per_eur=float(best["native_per_eur"]),
            source=best.get("source", "yfinance"),
            data_quality=(
                "exact" if best["as_of_date"] == target else "stale_fallback"
            ),
        )

    # ------------------------------------------------------------------
    # Write paths
    # ------------------------------------------------------------------
    def append_price(self, event: dict) -> bool:
        """Append a price_eod event. Idempotent on (ticker, as_of_date, source).
        Returns True if written, False if a matching entry already exists."""
        d_str = event.get("as_of_date") or event.get("date")
        if not d_str:
            raise ValueError("price event missing as_of_date / date")
        d = date.fromisoformat(d_str)
        path = self._month_path(d)
        # Idempotency check.
        for existing in self._iter_jsonl(path):
            if (
                existing.get("event_type") == "price_eod"
                and existing.get("ticker") == event.get("ticker")
                and (existing.get("as_of_date") or existing.get("date")) == d_str
                and existing.get("source") == event.get("source")
            ):
                return False
        return self._atomic_append(path, event)

    def append_fx(self, event: dict) -> bool:
        d_str = event.get("as_of_date")
        if not d_str:
            raise ValueError("fx event missing as_of_date")
        d = date.fromisoformat(d_str)
        path = self._month_path(d)
        for existing in self._iter_jsonl(path):
            if (
                existing.get("event_type") == "fx_eod"
                and existing.get("native_currency") == event.get("native_currency")
                and existing.get("as_of_date") == d_str
                and existing.get("source") == event.get("source")
            ):
                return False
        return self._atomic_append(path, event)

    def _atomic_append(self, path: Path, event: dict) -> bool:
        # Append-then-fsync is good enough for JSONL log + ensures crash
        # safety: a partial line is detected as JSONDecodeError on read
        # and skipped. We avoid a full rewrite-via-tmp because logs grow
        # large and rewriting every append is wasteful.
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(event, separators=(",", ":")) + "\n")
            fp.flush()
            try:
                os.fsync(fp.fileno())
            except OSError:
                pass
        return True

    # ------------------------------------------------------------------
    # Inventory helpers
    # ------------------------------------------------------------------
    def list_tickers(self) -> set[str]:
        out: set[str] = set()
        if not self.log_dir.exists():
            return out
        for p in self.log_dir.glob("*.jsonl"):
            for event in self._iter_jsonl(p):
                if event.get("event_type") == "price_eod":
                    t = event.get("ticker")
                    if isinstance(t, str):
                        out.add(t)
        return out

    def list_dates_for(self, ticker: str) -> list[str]:
        out: set[str] = set()
        if not self.log_dir.exists():
            return []
        for p in self.log_dir.glob("*.jsonl"):
            for event in self._iter_jsonl(p):
                if (
                    event.get("event_type") == "price_eod"
                    and event.get("ticker") == ticker
                ):
                    d = event.get("as_of_date") or event.get("date")
                    if isinstance(d, str):
                        out.add(d)
        return sorted(out)


class PriceFetcher:
    """Wraps yfinance to populate the price log. NOT used at rebuild time
    once the log is backfilled (rebuilder reads the log)."""

    def __init__(self, price_log: PriceLog | None = None, source: str = "yfinance"):
        self.log = price_log or PriceLog()
        self.source = source

    def fetch_eod(
        self,
        ticker: str,
        as_of_date: date,
        currency: str,
        exchange: str | None = None,
        yf_symbol: str | None = None,
    ) -> dict | None:
        try:
            import yfinance as yf
        except ImportError:
            return None
        symbol = yf_symbol or derive_yf_symbol(ticker, exchange)
        try:
            from datetime import date as _date

            start = _date.fromordinal(as_of_date.toordinal() - 5)
            end = _date.fromordinal(as_of_date.toordinal() + 1)
            hist = yf.Ticker(symbol).history(
                start=start.isoformat(),
                end=end.isoformat(),
                auto_adjust=False,
            )
        except Exception:
            return None
        if hist is None or hist.empty:
            return None
        dates_close: list[tuple[date, float]] = []
        for idx, row in zip(hist.index, hist["Close"]):
            dates_close.append((idx.date(), float(row)))
        valid = [(d, c) for d, c in dates_close if d <= as_of_date]
        if not valid:
            return None
        d_match, close = valid[-1]
        if d_match != as_of_date:
            # Stale — yfinance has no row for as_of_date (weekend / holiday /
            # not yet available). We still emit an event tagged as stale.
            pass
        prev_close = valid[-2][1] if len(valid) >= 2 else close
        return {
            "event_type": "price_eod",
            "ts": _now_iso_utc(),
            "ticker": ticker,
            "currency": currency,
            "close": close,
            "previous_close": prev_close,
            "intraday_pct": (close / prev_close - 1.0) if prev_close else 0.0,
            "source": self.source,
            "as_of_date": d_match.isoformat(),
        }

    def fetch_fx(self, native_currency: str, as_of_date: date) -> dict | None:
        """Fetches native_per_eur for the given currency. For USD that
        means the EURUSD=X close (USD per 1 EUR)."""
        if native_currency == "EUR":
            return None
        try:
            import yfinance as yf
        except ImportError:
            return None
        symbol = f"EUR{native_currency}=X"
        try:
            from datetime import date as _date

            start = _date.fromordinal(as_of_date.toordinal() - 7)
            end = _date.fromordinal(as_of_date.toordinal() + 1)
            hist = yf.Ticker(symbol).history(
                start=start.isoformat(),
                end=end.isoformat(),
                auto_adjust=False,
            )
        except Exception:
            return None
        if hist is None or hist.empty:
            return None
        dates_close: list[tuple[date, float]] = []
        for idx, row in zip(hist.index, hist["Close"]):
            dates_close.append((idx.date(), float(row)))
        valid = [(d, c) for d, c in dates_close if d <= as_of_date]
        if not valid:
            return None
        d_match, native_per_eur = valid[-1]
        return {
            "event_type": "fx_eod",
            "ts": _now_iso_utc(),
            "as_of_date": d_match.isoformat(),
            "native_currency": native_currency,
            "native_per_eur": native_per_eur,
            "source": self.source,
            "fetched_ts": _now_iso_utc(),
        }


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _daterange(start: date, end: date) -> Iterable[date]:
    cur = start
    while cur <= end:
        yield cur
        cur = date.fromordinal(cur.toordinal() + 1)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Price log fetcher / backfiller.")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--backfill", action="store_true")
    mode.add_argument("--daily-fetch", action="store_true")
    p.add_argument("--start", type=_parse_date)
    p.add_argument("--end", type=_parse_date)
    p.add_argument("--date", type=_parse_date)
    p.add_argument(
        "--tickers",
        type=str,
        required=True,
        help="comma-separated TICKER[:CURRENCY[:EXCHANGE]] entries",
    )
    p.add_argument("--include-fx", action="store_true", default=True)
    args = p.parse_args(argv)

    pl = PriceLog()
    pf = PriceFetcher(pl)

    parsed_tickers: list[tuple[str, str, str | None]] = []
    for spec in args.tickers.split(","):
        spec = spec.strip()
        if not spec:
            continue
        parts = spec.split(":")
        t = parts[0]
        cur = parts[1] if len(parts) > 1 else "USD"
        ex = parts[2] if len(parts) > 2 else None
        parsed_tickers.append((t, cur, ex))

    if args.backfill:
        if not args.start or not args.end:
            p.error("--backfill requires --start and --end")
        dates = list(_daterange(args.start, args.end))
    else:
        if not args.date:
            p.error("--daily-fetch requires --date")
        dates = [args.date]

    written_px = 0
    written_fx = 0
    skipped = 0
    failed: list[str] = []
    fx_currencies: set[str] = {cur for _, cur, _ in parsed_tickers if cur != "EUR"}

    for d in dates:
        for ticker, cur, ex in parsed_tickers:
            ev = pf.fetch_eod(ticker, d, cur, exchange=ex)
            if ev is None:
                failed.append(f"{ticker}@{d}")
                continue
            if pl.append_price(ev):
                written_px += 1
            else:
                skipped += 1
        if args.include_fx:
            for cur in fx_currencies:
                ev = pf.fetch_fx(cur, d)
                if ev is None:
                    failed.append(f"FX[{cur}]@{d}")
                    continue
                if pl.append_fx(ev):
                    written_fx += 1
                else:
                    skipped += 1

    print(
        f"price_log: wrote {written_px} price_eod + {written_fx} fx_eod events, "
        f"skipped {skipped} duplicates, {len(failed)} failures"
    )
    if failed:
        for f in failed[:20]:
            print(f"  FAIL {f}")
        if len(failed) > 20:
            print(f"  ... +{len(failed) - 20} more")
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
