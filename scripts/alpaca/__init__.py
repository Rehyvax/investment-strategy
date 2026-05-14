"""Alpaca paper-trading client (Claude Autonomous experiment).

All trades are PAPER. Live trading is forbidden by design — the
client unconditionally constructs `TradingClient(..., paper=True)`.
Without ALPACA_API_KEY/SECRET, every helper degrades to a None /
empty return so the rest of the system keeps running.
"""
