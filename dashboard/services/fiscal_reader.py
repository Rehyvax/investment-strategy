"""Fiscal reader (Spain LIRPF context) for Pantalla 9.

Derives every metric from `data/events/portfolios/real/trades.jsonl` +
the latest snapshot — never invents fiscal data. Outputs are dicts
ready for Streamlit rendering; no UI imports here.

Public surface:
    get_realized_pnl_breakdown(year)        -> dict
    get_active_two_month_locks(as_of=today) -> list[dict]
    get_fifo_log(year)                      -> list[dict]
    get_tax_loss_harvesting_candidates()    -> list[dict] (Q4 only)
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

LAB_ROOT = Path(__file__).resolve().parents[2]
TRADES_FP = LAB_ROOT / "data" / "events" / "portfolios" / "real" / "trades.jsonl"
SNAPSHOTS_DIR = LAB_ROOT / "data" / "snapshots" / "real"

# Spain savings-base IRPF brackets 2026 (CLAUDE.md §7).
# Used for the rough withholding estimate on Pantalla 9. Real
# liquidation depends on full annual base — this is illustrative.
IRPF_BRACKETS_2026 = [
    (6_000.0, 0.19),
    (50_000.0, 0.21),
    (200_000.0, 0.23),
    (300_000.0, 0.27),
    (float("inf"), 0.30),
]

# Tax-loss harvesting candidate threshold (CLAUDE.md §7 inspiration).
HARVEST_LOSS_PCT_THRESHOLD = -5.0


class FiscalReader:
    def __init__(
        self,
        trades_fp: Path | None = None,
        snapshots_dir: Path | None = None,
    ):
        self.trades_fp = trades_fp or TRADES_FP
        self.snapshots_dir = snapshots_dir or SNAPSHOTS_DIR

    # ------------------------------------------------------------------
    # Trade event iteration
    # ------------------------------------------------------------------
    def _iter_sells(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.trades_fp.exists():
            return out
        with self.trades_fp.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("event_type") != "trade":
                    continue
                if ev.get("side") != "sell":
                    continue
                if ev.get("realized_pnl_eur") is None:
                    continue
                out.append(ev)
        return out

    def _iter_buys(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.trades_fp.exists():
            return out
        with self.trades_fp.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("event_type") != "trade":
                    continue
                if ev.get("side") != "buy":
                    continue
                out.append(ev)
        return out

    # ------------------------------------------------------------------
    # Realized P&L breakdown
    # ------------------------------------------------------------------
    def get_realized_pnl_breakdown(self, year: int | None = None) -> dict[str, Any]:
        target = year or date.today().year
        gains_eur = 0.0
        losses_eur = 0.0
        n_gains = 0
        n_losses = 0
        for ev in self._iter_sells():
            td = ev.get("trade_date", "")
            try:
                if int(td[:4]) != target:
                    continue
            except (ValueError, TypeError):
                continue
            pnl = float(ev.get("realized_pnl_eur") or 0.0)
            if pnl > 0:
                gains_eur += pnl
                n_gains += 1
            elif pnl < 0:
                losses_eur += pnl
                n_losses += 1
        net = gains_eur + losses_eur
        # Estimated IRPF on the NET positive gain (losses compensate first).
        taxable = max(0.0, net)
        withholding_est = _estimate_irpf(taxable)
        # Carry-forward cap on losses: 4 fiscal years (LIRPF art. 49).
        return {
            "year": target,
            "gains_eur": round(gains_eur, 2),
            "losses_eur": round(losses_eur, 2),  # negative
            "net_eur": round(net, 2),
            "n_gains": n_gains,
            "n_losses": n_losses,
            "estimated_irpf_eur": round(withholding_est, 2),
            "loss_carryforward_available_eur": round(min(0.0, net), 2),  # negative
            "loss_carryforward_horizon_years": 4,
        }

    # ------------------------------------------------------------------
    # 2-month rule active locks (art. 33.5 f LIRPF)
    # ------------------------------------------------------------------
    def get_active_two_month_locks(
        self, as_of: date | None = None
    ) -> list[dict[str, Any]]:
        as_of = as_of or date.today()
        as_of_str = as_of.isoformat()
        buys = self._iter_buys()
        out: list[dict[str, Any]] = []
        for ev in self._iter_sells():
            if not ev.get("is_loss"):
                continue
            window_end = ev.get("two_month_rule_window_end")
            if not isinstance(window_end, str):
                continue
            if window_end < as_of_str:
                continue
            ticker = ev.get("ticker", "")
            isin = ev.get("isin", "")
            sale_date = ev.get("trade_date", "")
            loss_eur = abs(float(ev.get("realized_pnl_eur") or 0.0))
            # Has the user already triggered the rule by buying back?
            repurchase = None
            for b in buys:
                if b.get("isin") != isin and b.get("ticker") != ticker:
                    continue
                btd = b.get("trade_date", "")
                if not isinstance(btd, str):
                    continue
                # Buy must be AFTER the sale and BEFORE the window end.
                if sale_date < btd <= window_end:
                    repurchase = {
                        "trade_date": btd,
                        "quantity": b.get("quantity"),
                        "event_id": b.get("event_id"),
                    }
                    break
            out.append(
                {
                    "ticker": ticker,
                    "isin": isin,
                    "sale_date": sale_date,
                    "loss_eur": round(loss_eur, 2),
                    "window_end": window_end,
                    "days_remaining": (
                        date.fromisoformat(window_end) - as_of
                    ).days
                    if _is_date(window_end)
                    else None,
                    "repurchase_detected": repurchase is not None,
                    "repurchase_detail": repurchase,
                    "lirpf_article": "art. 33.5 f LIRPF",
                }
            )
        out.sort(key=lambda r: r["window_end"])
        return out

    # ------------------------------------------------------------------
    # FIFO log per year
    # ------------------------------------------------------------------
    def get_fifo_log(self, year: int | None = None) -> list[dict[str, Any]]:
        target = year or date.today().year
        out: list[dict[str, Any]] = []
        for ev in self._iter_sells():
            td = ev.get("trade_date", "")
            try:
                if int(td[:4]) != target:
                    continue
            except (ValueError, TypeError):
                continue
            consumption = ev.get("fifo_consumption") or []
            # Some events store a single lot consumed; still emit a row.
            if not consumption and ev.get("lot_id_consumed"):
                consumption = [
                    {
                        "lot_id": ev.get("lot_id_consumed"),
                        "quantity": ev.get("quantity"),
                        "cost_basis_eur": ev.get("cost_basis_eur_consumed"),
                    }
                ]
            for lot in consumption:
                out.append(
                    {
                        "sale_date": td,
                        "ticker": ev.get("ticker"),
                        "isin": ev.get("isin", ""),
                        "shares": lot.get("quantity"),
                        "cost_basis_eur_lot": lot.get("cost_basis_eur"),
                        "sale_price_native": ev.get("price_native"),
                        "proceeds_eur": ev.get("proceeds_eur"),
                        "realized_pnl_eur_lot": _approx_lot_pnl(ev, lot),
                        "lot_id": lot.get("lot_id"),
                        "is_loss": ev.get("is_loss"),
                    }
                )
        out.sort(key=lambda r: r["sale_date"], reverse=True)
        return out

    def export_fifo_csv(self, year: int | None = None) -> str:
        """Returns a CSV string for download. Header in Spanish so a
        gestor can paste straight into a Modelo 100 working sheet."""
        rows = self.get_fifo_log(year)
        header = (
            "Fecha venta;Ticker;ISIN;Acciones;Coste base (EUR);"
            "Precio venta (nativo);Ingreso (EUR);Pérdida/Ganancia lote (EUR);"
            "Es pérdida;Lot ID\n"
        )
        out = [header]
        for r in rows:
            out.append(
                ";".join(
                    [
                        str(r.get("sale_date") or ""),
                        str(r.get("ticker") or ""),
                        str(r.get("isin") or ""),
                        f"{r.get('shares', 0)}",
                        f"{r.get('cost_basis_eur_lot', 0)}",
                        f"{r.get('sale_price_native', 0)}",
                        f"{r.get('proceeds_eur', 0)}",
                        f"{r.get('realized_pnl_eur_lot', 0)}",
                        "sí" if r.get("is_loss") else "no",
                        str(r.get("lot_id") or ""),
                    ]
                )
                + "\n"
            )
        return "".join(out)

    # ------------------------------------------------------------------
    # Tax-loss harvesting candidates (Q4 only)
    # ------------------------------------------------------------------
    def get_tax_loss_harvesting_candidates(
        self,
        as_of: date | None = None,
        loss_pct_threshold: float = HARVEST_LOSS_PCT_THRESHOLD,
    ) -> list[dict[str, Any]]:
        as_of = as_of or date.today()
        # Q4 = Oct/Nov/Dec
        if as_of.month < 10:
            return []
        snap = self._latest_snapshot()
        if snap is None:
            return []
        out: list[dict[str, Any]] = []
        for p in snap.get("positions", []) or []:
            cb = float(p.get("cost_basis_per_share_native") or 0.0)
            cur = float(p.get("current_price_native") or 0.0)
            if cb <= 0 or cur <= 0:
                continue
            pnl_pct = (cur / cb - 1.0) * 100.0
            if pnl_pct >= loss_pct_threshold:
                continue
            out.append(
                {
                    "ticker": p.get("ticker"),
                    "isin": p.get("isin", ""),
                    "current_value_eur": p.get("current_value_eur"),
                    "unrealized_pnl_eur": p.get("unrealized_pnl_eur"),
                    "unrealized_pnl_pct": round(pnl_pct, 2),
                    "reasoning": (
                        f"Pérdida latente {pnl_pct:.1f}%. Realizar antes del "
                        "31 dic para aplicar contra ganancias del año fiscal "
                        f"{as_of.year}."
                    ),
                }
            )
        out.sort(key=lambda r: r["unrealized_pnl_pct"])
        return out

    # ------------------------------------------------------------------
    def _latest_snapshot(self) -> dict[str, Any] | None:
        if not self.snapshots_dir.exists():
            return None
        cands: list[Path] = []
        for f in self.snapshots_dir.glob("*.json"):
            if f.name.startswith("_"):
                continue
            stem = f.stem
            if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
                cands.append(f)
        if not cands:
            return None
        cands.sort()
        return json.loads(cands[-1].read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def _estimate_irpf(amount_eur: float) -> float:
    """Bracketed IRPF estimate on the savings base.

    Pure function — covered by tests."""
    if amount_eur <= 0:
        return 0.0
    remaining = amount_eur
    last_bound = 0.0
    total = 0.0
    for upper, rate in IRPF_BRACKETS_2026:
        slab = min(remaining, upper - last_bound)
        if slab <= 0:
            break
        total += slab * rate
        remaining -= slab
        last_bound = upper
        if remaining <= 0:
            break
    return total


def _is_date(s: str) -> bool:
    try:
        date.fromisoformat(s)
        return True
    except (TypeError, ValueError):
        return False


def _approx_lot_pnl(ev: dict[str, Any], lot: dict[str, Any]) -> float:
    """Best-effort per-lot P&L. When the trade event consumes a single
    lot the realized_pnl_eur on the event already covers it; otherwise
    we pro-rate by share fraction."""
    cb = lot.get("cost_basis_eur")
    if cb is None:
        return float(ev.get("realized_pnl_eur") or 0.0)
    full_qty = float(ev.get("quantity") or 0.0)
    lot_qty = float(lot.get("quantity") or 0.0)
    full_pnl = float(ev.get("realized_pnl_eur") or 0.0)
    if full_qty <= 0 or lot_qty <= 0:
        return full_pnl
    return round(full_pnl * (lot_qty / full_qty), 2)
