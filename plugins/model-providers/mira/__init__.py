"""MIRA provider profile — HavoK's own MIRA brain as a selectable model in ARGUS.

ARGUS talks to MIRA's backend (mira-api) through its OpenAI-compatible shim (``POST /v1/chat/completions``,
added 2026-11-09, which wraps MIRA's ``/v1/hvksys-jarvis/call``). So a turn here routes through MIRA's FULL
brain — her persona, memory, MCP tools and provider-fallback chain — the same brain Mira Desktop, Discord and
the laphvk VI use. The reply comes back as MIRA, not a raw model.

Auth: the mira-api operator token in ``MIRA_API_KEY`` (role HAVOK, so the turn runs as HavoK in his active
session — talking to MIRA in ARGUS is the same conversation as the other clients). ``MIRA_BASE_URL`` overrides
the endpoint (default: debhvk on the home LAN); set it to the relay hostname to use ARGUS away from home.
"""

import os

from providers import register_provider
from providers.base import ProviderProfile

mira = ProviderProfile(
    name="mira",
    aliases=("mira-brain", "jarvis"),
    display_name="MIRA",
    description="MIRA's own brain (persona, memory, tools) via mira-api — talk to MIRA, not a raw model",
    env_vars=("MIRA_API_KEY", "MIRA_BASE_URL"),
    base_url=os.environ.get("MIRA_BASE_URL", "http://192.168.1.222:5000/v1"),
    fallback_models=("mira",),
    default_aux_model="mira",
    default_max_tokens=1024,
)

register_provider(mira)
