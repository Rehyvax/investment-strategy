"""Pantalla 6 — Mercado-AI conversacional.

Chat surface that consults `scripts.mercado_ai.chat_mercado_ai` with
the latest cerebro state + snapshot context per turn. Conversation
state is held in `st.session_state["mercado_messages"]` (a list of
{"role", "content"} dicts mirroring the Anthropic message shape)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DASHBOARD_ROOT.parent
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import streamlit as st  # noqa: E402

from auth import check_auth  # noqa: E402
from styles import inject_css  # noqa: E402

from mercado_ai import chat_mercado_ai  # type: ignore  # noqa: E402

try:
    from llm_narratives import is_llm_available  # noqa: E402
except ImportError:

    def is_llm_available() -> bool:  # type: ignore
        return False


CEREBRO_PATH = PROJECT_ROOT / "dashboard" / "data" / "cerebro_state.json"
SNAPSHOT_DIR = PROJECT_ROOT / "data" / "snapshots" / "real"


SUGGESTED_QUESTIONS = (
    "¿Cómo está mi cartera hoy?",
    "Resumen de las posiciones con tesis halfway o vigilancia",
    "Compara MSFT vs NOW en fundamentals",
    "¿Qué sectores tengo sobreexpuestos?",
    "Explícame el último debate de MELI",
    "¿Qué posición pesa más y por qué tiene esa tesis?",
    "¿Hay alguna noticia material de las últimas 24 horas?",
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _load_cerebro_state() -> dict:
    if not CEREBRO_PATH.exists():
        return {}
    try:
        return json.loads(CEREBRO_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _load_latest_snapshot() -> dict:
    if not SNAPSHOT_DIR.exists():
        return {}
    candidates = []
    for f in SNAPSHOT_DIR.glob("*.json"):
        if f.name.startswith("_"):
            continue
        stem = f.stem
        if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
            candidates.append(f)
    if not candidates:
        return {}
    candidates.sort()
    try:
        return json.loads(candidates[-1].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _send(user_input: str) -> None:
    """Append user msg, call LLM, append assistant reply (or error)."""
    st.session_state.mercado_messages.append(
        {"role": "user", "content": user_input}
    )
    history_for_llm = st.session_state.mercado_messages[:-1]
    cerebro_state = _load_cerebro_state()
    snapshot = _load_latest_snapshot()
    response = chat_mercado_ai(
        user_input, history_for_llm, cerebro_state, snapshot
    )
    if response:
        st.session_state.mercado_messages.append(
            {"role": "assistant", "content": response}
        )
    else:
        st.session_state.mercado_messages.append(
            {
                "role": "assistant",
                "content": (
                    "(Error: LLM no disponible o sin créditos. "
                    "Verifica ANTHROPIC_API_KEY en .env)"
                ),
            }
        )


# ----------------------------------------------------------------------
# Page setup
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="Mercado-AI",
    page_icon=":speech_balloon:",
    layout="wide",
)
inject_css()

if not check_auth():
    st.stop()

if "mercado_messages" not in st.session_state:
    st.session_state.mercado_messages = []


# ----------------------------------------------------------------------
# Sidebar — suggestions + reset
# ----------------------------------------------------------------------
with st.sidebar:
    st.markdown("**Mercado-AI**")
    st.caption("Coste estimado: ~$0.02-0.05 por mensaje (Sonnet 4.6).")
    if not is_llm_available():
        st.warning(
            "ANTHROPIC_API_KEY no detectada. Las respuestas estarán "
            "deshabilitadas hasta configurarla en .env."
        )
    if st.button("Nueva conversación", use_container_width=True):
        st.session_state.mercado_messages = []
        st.rerun()
    st.markdown("---")
    st.markdown("**Preguntas sugeridas**")
    for s in SUGGESTED_QUESTIONS:
        if st.button(s, use_container_width=True, key=f"sugg_{abs(hash(s))}"):
            with st.spinner("Mercado-AI pensando…"):
                _send(s)
            st.rerun()


# ----------------------------------------------------------------------
# Chat surface
# ----------------------------------------------------------------------
st.markdown(
    "<h1 style='margin-bottom:0;'>Mercado-AI</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='color:#64748B; margin-top:4px; font-size:0.9375rem;'>"
    "Consultor conversacional con contexto de tu cartera + cerebro state.</p>",
    unsafe_allow_html=True,
)

if not st.session_state.mercado_messages:
    st.markdown(
        """
        <div class="institutional-card" style="text-align:center; padding:32px;">
            <h3 style="color:#475569; margin:0 0 12px 0;">Pregúntame cualquier cosa</h3>
            <p style="color:#64748B; margin:0;">
                Tengo contexto de tu snapshot actual, news, technicals, fundamentals,
                tesis vigentes y debates recientes.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

for msg in st.session_state.mercado_messages:
    role_color = "#1E40AF" if msg["role"] == "user" else "#475569"
    role_bg = "#EFF6FF" if msg["role"] == "user" else "#F8FAFC"
    role_label = "Tú" if msg["role"] == "user" else "Mercado-AI"
    st.markdown(
        f"""
        <div style="background:{role_bg}; padding:12px 16px; border-radius:8px;
                    margin:8px 0; border-left:3px solid {role_color};">
            <div style="font-size:0.7rem; color:{role_color}; font-weight:600;
                        text-transform:uppercase; letter-spacing:0.05em;
                        margin-bottom:4px;">{role_label}</div>
            <p style="margin:0; color:#0F172A; line-height:1.6;
                      white-space:pre-wrap;">{msg["content"]}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

user_input = st.chat_input("Pregunta sobre tu cartera o mercado…")
if user_input:
    with st.spinner("Mercado-AI pensando…"):
        _send(user_input)
    st.rerun()
