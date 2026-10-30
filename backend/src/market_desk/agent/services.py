"""The outside services the agent talks to, built once when the API starts.

One client each for the whole app, not one per request: each keeps a pool of open connections,
so later requests skip the TCP and TLS handshakes. The lifespan in api/main.py opens and
closes them; routes get them through `get_agent_services`, which tests override with fakes.
"""

from dataclasses import dataclass

from anthropic import AsyncAnthropic

from market_desk.clients.cala import CalaClient
from market_desk.clients.edgar import EdgarClient
from market_desk.config import Settings

TIMEOUT_SECONDS = 30


@dataclass
class AgentServices:
    anthropic: AsyncAnthropic
    cala: CalaClient
    edgar: EdgarClient

    async def close(self) -> None:
        await self.anthropic.close()
        await self.cala.close()
        await self.edgar.close()


def services_from_settings(settings: Settings) -> AgentServices | None:
    """The real clients, or None if a key is missing: the API still starts, /chat answers 503."""
    if (
        settings.anthropic_api_key is None
        or settings.cala_api_key is None
        or settings.edgar_user_agent is None
    ):
        return None
    return AgentServices(
        anthropic=AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value()),
        cala=CalaClient.from_settings(settings, timeout=TIMEOUT_SECONDS),
        edgar=EdgarClient.from_settings(settings, timeout=TIMEOUT_SECONDS),
    )
