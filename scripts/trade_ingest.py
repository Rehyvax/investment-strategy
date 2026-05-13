"""Manual trade ingest for the real portfolio.

Scope (Phase 2D-extended): MANUAL ENTRY ONLY. The Lightyear CSV parser
is intentionally deferred until a real broker export sample is available
(building it without a real schema risks shipping a parser that fails on
the first real file).

Public surface used by `dashboard/pages/7_Trades.py`:

  ParsedTrade          dataclass (manual form binds to it 1:1)
  build_manual_trade   form-fields -> ParsedTrade with derived numbers
  check_compliance     returns a structured CompliancePayload
  persist_trade        atomic append to trades.jsonl, returns event_id
  get_recent_trades    used for the 2-month-rule lookup window
  get_all_trades       used by Bloque D (history table)

Compliance rules enforced (per CLAUDE.md §6 + §7 + §9):
  - cap_single_name 12% NAV post-trade (risk-concentration §3 limit)
  - cash sufficiency (buy) / share sufficiency (sell)
  - 2-month rule LIRPF lookup against last 60 days of sells-at-loss
    when proposing a buy on the same ISIN

The Coordinator never auto-executes; this module BLOCKS the trade only
when compliance fails. The user always has the final word in Lightyear.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

ROOT = Path(__file__).resolve().parents[1]
TRADES_FP = ROOT / "data" / "events" / "portfolios" / "real" / "trades.jsonl"
SNAPSHOTS_DIR = ROOT / "data" / "snapshots" / "real"

Side = Literal["buy", "sell"]


# ---------------------------------------------------------------------------
# ULID generator (matches the format used in the rest of the event log)
# ---------------------------------------------------------------------------
def _ulid() -> str:
    """Crockford-base32 ULID, 26 chars, 48-bit timestamp + 80-bit random."""
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    n = int(time.time() * 1000)
    ts = []
    for _ in range(10):
        ts.append(alphabet[n & 31])
        n >>= 5
    rnd = "".join(secrets.choice(alphabet) for _ in range(16))
    return "".join(reversed(ts)) + rnd


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class ParsedTrade:
    """Single normalized trade ready for compliance check + persistence.

    All amounts are stored in BOTH the native currency of execution and
    in EUR converted with the user-supplied FX rate (Lightyear executes
    a conversion at the time of the trade; we persist that exact rate)."""

    side: Side
    trade_date: str          # ISO YYYY-MM-DD
    ticker: str
    isin: str
    exchange: str
    currency: str            # native currency of execution
    quantity: float          # always positive
    price_native: float      # per-share execution price
    fees_native: float       # commissions + half-spread + FX fee total
    fx_rate_usd_per_eur: float  # broker-reported, always > 0
    notes: str = ""
    sector: str | None = None
    country: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    # Derived (filled by build_manual_trade for convenience)
    gross_value_native: float = 0.0
    net_value_native: float = 0.0
    gross_value_eur: float = 0.0
    net_value_eur: float = 0.0
    fees_eur: float = 0.0


def build_manual_trade(
    *,
    side: Side,
    trade_date: str,
    ticker: str,
    isin: str,
    exchange: str,
    currency: str,
    quantity: float,
    price_native: float,
    fees_native: float,
    fx_rate_usd_per_eur: float,
    notes: str = "",
    sector: str | None = None,
    country: str | None = None,
) -> ParsedTrade:
    """Wraps user form input + derives the *_eur fields and net value.

    Convention: a SELL credits the account by `gross - fees`; a BUY debits
    the account by `gross + fees`. The `net_value_*` field is the magnitude
    of the cash movement either way."""
    side = side.lower()  # type: ignore
    if side not in ("buy", "sell"):
        raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
    if quantity <= 0:
        raise ValueError(f"quantity must be > 0, got {quantity}")
    if price_native <= 0:
        raise ValueError(f"price_native must be > 0, got {price_native}")
    if fx_rate_usd_per_eur <= 0:
        raise ValueError(
            f"fx_rate_usd_per_eur must be > 0, got {fx_rate_usd_per_eur}"
        )

    gross_native = round(quantity * price_native, 4)
    fees_native = max(0.0, round(fees_native, 4))
    if side == "buy":
        net_native = round(gross_native + fees_native, 4)
    else:
        net_native = round(gross_native - fees_native, 4)

    # FX convention follows the existing event log: rate is USD-per-EUR.
    # For non-USD currencies the form must still pass the rate that
    # converts THIS trade's currency to EUR; we treat the field as
    # "<native>_per_EUR" generically.
    eur_per_native = 1.0 / fx_rate_usd_per_eur
    gross_eur = round(gross_native * eur_per_native, 4)
    fees_eur = round(fees_native * eur_per_native, 4)
    net_eur = round(net_native * eur_per_native, 4)

    return ParsedTrade(
        side=side,  # type: ignore
        trade_date=trade_date,
        ticker=ticker.upper().strip(),
        isin=isin.upper().strip(),
        exchange=exchange.upper().strip(),
        currency=currency.upper().strip(),
        quantity=quantity,
        price_native=price_native,
        fees_native=fees_native,
        fx_rate_usd_per_eur=fx_rate_usd_per_eur,
        notes=notes.strip(),
        sector=sector,
        country=country,
        gross_value_native=gross_native,
        net_value_native=net_native,
        gross_value_eur=gross_eur,
        fees_eur=fees_eur,
        net_value_eur=net_eur,
    )


# ---------------------------------------------------------------------------
# Compliance
# ---------------------------------------------------------------------------
@dataclass
class ComplianceFinding:
    code: str            # e.g. "cap_single_name", "cash_sufficient"
    severity: Literal["block", "warn", "info"]
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompliancePayload:
    findings: list[ComplianceFinding] = field(default_factory=list)
    blocked: bool = False
    post_trade_weight_pct: float | None = None
    post_trade_cash_eur: float | None = None
    post_trade_position_qty: float | None = None

    def add(self, f: ComplianceFinding) -> None:
        self.findings.append(f)
        if f.severity == "block":
            self.blocked = True


CAP_SINGLE_NAME_PCT = 12.0
TWO_MONTH_WINDOW_DAYS = 60


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
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


def get_all_trades() -> list[dict[str, Any]]:
    return list(_iter_jsonl(TRADES_FP))


def get_recent_trades(days: int = 90, as_of: date | None = None) -> list[dict[str, Any]]:
    """Returns trade events with `trade_date` within `[as_of-days, as_of]`."""
    as_of = as_of or date.today()
    cutoff = as_of - timedelta(days=days)
    out: list[dict[str, Any]] = []
    for ev in _iter_jsonl(TRADES_FP):
        if ev.get("event_type") not in ("trade",):
            continue
        td_str = ev.get("trade_date")
        if not isinstance(td_str, str):
            continue
        try:
            td = date.fromisoformat(td_str)
        except ValueError:
            continue
        if cutoff <= td <= as_of:
            out.append(ev)
    return out


def _load_latest_snapshot() -> dict[str, Any] | None:
    if not SNAPSHOTS_DIR.exists():
        return None
    candidates: list[Path] = []
    for f in SNAPSHOTS_DIR.glob("*.json"):
        if f.name.startswith("_"):
            continue
        stem = f.stem
        if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
            candidates.append(f)
    if not candidates:
        return None
    candidates.sort()
    with candidates[-1].open("r", encoding="utf-8") as fp:
        return json.load(fp)


def _position_in_snapshot(
    snap: dict[str, Any], ticker: str, isin: str
) -> dict[str, Any] | None:
    for p in snap.get("positions", []) or []:
        if p.get("isin") == isin or p.get("ticker") == ticker:
            return p
    return None


def check_compliance(
    trade: ParsedTrade,
    *,
    current_snapshot: dict[str, Any] | None = None,
    recent_trades: list[dict[str, Any]] | None = None,
    as_of_date: date | None = None,
) -> CompliancePayload:
    """Run the three blocking checks plus informative annotations.

    The function is pure (no I/O) when both snapshot and recent_trades are
    supplied. When `current_snapshot` is None, the latest snapshot on disk
    is loaded — useful for dashboard usage."""
    payload = CompliancePayload()
    snap = current_snapshot if current_snapshot is not None else _load_latest_snapshot()
    if snap is None:
        payload.add(
            ComplianceFinding(
                code="no_snapshot",
                severity="warn",
                message=(
                    "Sin snapshot real disponible — no se pueden validar caps "
                    "ni cash. La operación se persiste pero sin checks de "
                    "concentración."
                ),
            )
        )
        return payload

    nav_eur = float(snap.get("nav_total_eur", 0.0))
    cash_eur = float(snap.get("cash_eur", 0.0))
    existing_pos = _position_in_snapshot(snap, trade.ticker, trade.isin)
    existing_qty = float(existing_pos.get("quantity", 0.0)) if existing_pos else 0.0
    existing_value_eur = (
        float(existing_pos.get("current_value_eur", 0.0)) if existing_pos else 0.0
    )

    # ---- Check 1: cash / shares sufficient -------------------------------
    if trade.side == "buy":
        post_cash = round(cash_eur - trade.net_value_eur, 4)
        payload.post_trade_cash_eur = post_cash
        if post_cash < -0.005:
            payload.add(
                ComplianceFinding(
                    code="cash_sufficient",
                    severity="block",
                    message=(
                        f"Cash insuficiente: necesitas €{trade.net_value_eur:,.2f} "
                        f"pero solo hay €{cash_eur:,.2f} disponible. "
                        f"Quedaría en €{post_cash:,.2f}."
                    ),
                    detail={
                        "cash_available_eur": cash_eur,
                        "trade_net_eur": trade.net_value_eur,
                        "post_trade_cash_eur": post_cash,
                    },
                )
            )
        else:
            payload.add(
                ComplianceFinding(
                    code="cash_sufficient",
                    severity="info",
                    message=(
                        f"Cash OK. Quedan €{post_cash:,.2f} tras la compra."
                    ),
                    detail={
                        "post_trade_cash_eur": post_cash,
                    },
                )
            )
    else:  # sell
        post_qty = round(existing_qty - trade.quantity, 8)
        payload.post_trade_position_qty = post_qty
        if post_qty < -1e-6:
            payload.add(
                ComplianceFinding(
                    code="shares_sufficient",
                    severity="block",
                    message=(
                        f"Shares insuficientes: tienes {existing_qty} de "
                        f"{trade.ticker} y quieres vender {trade.quantity}."
                    ),
                    detail={
                        "shares_held": existing_qty,
                        "shares_to_sell": trade.quantity,
                        "post_trade_qty": post_qty,
                    },
                )
            )
        else:
            payload.add(
                ComplianceFinding(
                    code="shares_sufficient",
                    severity="info",
                    message=(
                        f"Shares OK. Quedarían {post_qty} de {trade.ticker} "
                        f"tras la venta."
                    ),
                    detail={"post_trade_qty": post_qty},
                )
            )

    # ---- Check 2: cap_single_name 12% post-trade -------------------------
    if trade.side == "buy":
        post_value_eur = existing_value_eur + trade.gross_value_eur
        # NAV post-trade ≈ NAV (cash is converted into equity 1:1; ignore
        # mark-to-market drift between snapshot and execution).
        post_nav = nav_eur
    else:
        # SELL: position value drops; NAV unchanged (cash up, equity down).
        sell_value_eur = trade.gross_value_eur
        post_value_eur = max(0.0, existing_value_eur - sell_value_eur)
        post_nav = nav_eur

    if post_nav <= 0:
        payload.add(
            ComplianceFinding(
                code="cap_single_name",
                severity="warn",
                message="NAV no positivo, no se puede calcular cap.",
            )
        )
    else:
        post_weight = (post_value_eur / post_nav) * 100.0
        payload.post_trade_weight_pct = round(post_weight, 4)
        if post_weight > CAP_SINGLE_NAME_PCT + 1e-4:
            payload.add(
                ComplianceFinding(
                    code="cap_single_name",
                    severity="block",
                    message=(
                        f"Concentración post-trade {post_weight:.2f}% "
                        f"supera el cap de single-name {CAP_SINGLE_NAME_PCT}%."
                    ),
                    detail={
                        "post_weight_pct": post_weight,
                        "cap_pct": CAP_SINGLE_NAME_PCT,
                        "post_value_eur": post_value_eur,
                        "post_nav_eur": post_nav,
                    },
                )
            )
        elif post_weight > CAP_SINGLE_NAME_PCT * 0.85:
            payload.add(
                ComplianceFinding(
                    code="cap_single_name",
                    severity="warn",
                    message=(
                        f"Concentración post-trade {post_weight:.2f}% cerca "
                        f"del cap {CAP_SINGLE_NAME_PCT}%."
                    ),
                    detail={"post_weight_pct": post_weight},
                )
            )
        else:
            payload.add(
                ComplianceFinding(
                    code="cap_single_name",
                    severity="info",
                    message=(
                        f"Concentración post-trade {post_weight:.2f}% dentro "
                        f"del cap {CAP_SINGLE_NAME_PCT}%."
                    ),
                    detail={"post_weight_pct": post_weight},
                )
            )

    # ---- Check 3: 2-month rule LIRPF (only on BUY of same ISIN) ----------
    if trade.side == "buy":
        as_of = as_of_date or date.today()
        recent = (
            recent_trades
            if recent_trades is not None
            else get_recent_trades(days=TWO_MONTH_WINDOW_DAYS, as_of=as_of)
        )
        offending: list[dict[str, Any]] = []
        for ev in recent:
            if ev.get("side") != "sell":
                continue
            if not ev.get("is_loss"):
                continue
            if ev.get("isin") != trade.isin:
                continue
            window_end = ev.get("two_month_rule_window_end")
            if isinstance(window_end, str):
                try:
                    end = date.fromisoformat(window_end)
                except ValueError:
                    end = None
                if end is not None and trade.trade_date <= end.isoformat():
                    offending.append(ev)
        if offending:
            losses = sum(
                abs(float(o.get("realized_pnl_eur", 0.0))) for o in offending
            )
            window_ends = sorted(
                {o.get("two_month_rule_window_end", "?") for o in offending}
            )
            payload.add(
                ComplianceFinding(
                    code="two_month_rule",
                    severity="block",
                    message=(
                        f"Regla 2 meses LIRPF activa para {trade.ticker} "
                        f"(ISIN {trade.isin}). Si compras antes de "
                        f"{window_ends[-1]}, se difiere la deducción de "
                        f"€{losses:,.2f}."
                    ),
                    detail={
                        "deferred_loss_eur": losses,
                        "window_end_latest": window_ends[-1],
                        "offending_event_ids": [
                            o.get("event_id") for o in offending
                        ],
                    },
                )
            )
        else:
            payload.add(
                ComplianceFinding(
                    code="two_month_rule",
                    severity="info",
                    message="Sin ventas a pérdida del mismo ISIN en 60 días.",
                )
            )

    return payload


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_append(fp: Path, line: str) -> None:
    """Append a single line atomically.

    Strategy: write to tmp + os.replace would lose existing content; the
    cheapest atomic-on-Windows append is to acquire the existing bytes,
    write them + the new line to tmp, then replace. For the volumes here
    (<10k events) this is fine."""
    fp.parent.mkdir(parents=True, exist_ok=True)
    existing = fp.read_text(encoding="utf-8") if fp.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    new_text = existing + line + "\n"
    tmp = fp.with_suffix(fp.suffix + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    os.replace(tmp, fp)


def persist_trade(
    trade: ParsedTrade, as_of_date: date | None = None
) -> str:
    """Append a `trade` event to trades.jsonl. Returns the new event_id.

    The event schema mirrors `data/events/portfolios/real/trades.jsonl`'s
    historical entries; consumers (snapshot rebuilder, generate_cerebro_state,
    Pantallas) need no migration."""
    event_id = _ulid()
    payload: dict[str, Any] = {
        "event_type": "trade",
        "event_id": event_id,
        "ts": _now_iso_utc(),
        "side": trade.side,
        "trade_date": trade.trade_date,
        "settle_date": trade.trade_date,
        "portfolio_id": "real",
        "ticker": trade.ticker,
        "isin": trade.isin,
        "exchange": trade.exchange,
        "currency": trade.currency,
        "quantity": trade.quantity,
        "price_native": trade.price_native,
        "fees_native": trade.fees_native,
        "fees_eur": trade.fees_eur,
        "fx_rate_usd_per_eur": trade.fx_rate_usd_per_eur,
        "fx_rate_date": trade.trade_date,
        "fx_rate_source": "user_manual_entry",
        "ingest_source": "manual_form_pantalla_7",
        "user_executed": True,
    }
    if trade.side == "buy":
        payload.update(
            {
                "gross_value_native": trade.gross_value_native,
                "gross_value_eur": trade.gross_value_eur,
                "net_outflow_eur": trade.net_value_eur,
            }
        )
    else:
        payload.update(
            {
                "proceeds_native_pre_fees": trade.gross_value_native,
                "proceeds_native": trade.net_value_native,
                "proceeds_eur": trade.net_value_eur,
            }
        )
    if trade.notes:
        payload["context_note"] = trade.notes
    if trade.sector:
        payload["sector_at_purchase"] = trade.sector
    if trade.country:
        payload["country_at_purchase"] = trade.country
    if trade.extra:
        payload["extra"] = trade.extra

    _atomic_append(TRADES_FP, json.dumps(payload, ensure_ascii=False))
    return event_id


# ---------------------------------------------------------------------------
# Public dict helpers (for templated rendering in Streamlit)
# ---------------------------------------------------------------------------
def trade_to_dict(trade: ParsedTrade) -> dict[str, Any]:
    return asdict(trade)


def compliance_to_dict(payload: CompliancePayload) -> dict[str, Any]:
    return {
        "blocked": payload.blocked,
        "post_trade_weight_pct": payload.post_trade_weight_pct,
        "post_trade_cash_eur": payload.post_trade_cash_eur,
        "post_trade_position_qty": payload.post_trade_position_qty,
        "findings": [asdict(f) for f in payload.findings],
    }
