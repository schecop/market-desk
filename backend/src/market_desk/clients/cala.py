"""Typed async client for the Cala API: auth, timeouts and errors in one place (ADR-0003)."""

import asyncio
import logging
import types
from collections.abc import Awaitable, Callable
from typing import Any, Literal
from uuid import UUID

import httpx2
from pydantic import BaseModel, Field, ValidationError
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from market_desk.config import Settings

logger = logging.getLogger(__name__)

# Retry policy (ADR-0003). Every attempt spends one call of Cala's quota, so keep it small.
MAX_ATTEMPTS = 3
MAX_RETRY_AFTER = 30.0  # seconds; a longer Retry-After fails fast instead of blocking the agent


class Entity(BaseModel):
    id: UUID
    name: str
    entity_type: str
    description: str | None = None


class Source(BaseModel):
    name: str
    url: str


class Document(BaseModel):
    name: str
    url: str


class Origin(BaseModel):
    source: Source
    document: Document
    breadcrumb: list[str]


class KnowBit(BaseModel):
    id: UUID
    content: str
    origins: list[Origin]


class EntityMention(BaseModel):
    id: UUID
    name: str
    entity_type: str
    mentions: list[str]


class SearchAnswer(BaseModel):
    content: str
    context: list[KnowBit]
    entities: list[EntityMention] | None


class EntitySearchResponse(BaseModel):
    entities: list[Entity]


class EntityRelationships(BaseModel):
    # {} rather than None: "no relationships" has one representation, and callers can
    # .get("X", []) without a None check. default_factory builds a fresh dict per instance.
    outgoing: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    incoming: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class EntityDetails(BaseModel):
    id: UUID
    name: str
    entity_type: str
    description: str | None = None
    properties: dict[str, Any]
    # Tolerant: you only get relationships when you ask for them, so a missing key isn't fatal
    relationships: EntityRelationships = Field(default_factory=EntityRelationships)
    numerical_observations: list[Any] | None = None


class CalaError(Exception):
    """Base class: anything that goes wrong talking to Cala. Other 4xx raise it directly."""


class CalaConfigError(CalaError):
    """The client can't be built (no API key). Not retried."""


class CalaValidationError(CalaError):
    """422: our request is invalid. Retrying the same request gives the same answer."""

    def __init__(self, message: str, error_type: str) -> None:
        self.message = message
        self.error_type = error_type
        # Clean data in the attributes; a readable line for logs in str(exc)
        super().__init__(f"{error_type}: {message}")


class CalaRateLimitError(CalaError):
    """429: too many requests. retry_after is seconds to wait, or None if Cala didn't say."""

    def __init__(self, message: str, retry_after: float | None) -> None:
        self.message = message
        self.retry_after = retry_after
        super().__init__(message)


class CalaServerError(CalaError):
    """5xx: a failure on Cala's side, usually temporary. Retried."""


class CalaResponseError(CalaError):
    """A success whose body doesn't fit the model: Cala broke its contract. Not retried."""


class CalaConnectionError(CalaError):
    """Timeout or network failure: no response at all. Retried."""


class CalaClient:
    """Async client for Cala. Use as `async with CalaClient.from_settings(...) as client:`.

    Every method returns Pydantic models or raises a CalaError subclass, never an httpx2 error.
    """

    base_url = "https://api.cala.ai"

    def __init__(
        self,
        api_key: str,
        timeout: float,
        transport: httpx2.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        headers = {"X-API-KEY": api_key}
        self.client = httpx2.AsyncClient(
            base_url=self.base_url, headers=headers, timeout=timeout, transport=transport
        )
        self._sleep = sleep

    @classmethod
    def from_settings(cls, settings: Settings, timeout: float) -> "CalaClient":
        if settings.cala_api_key is None:
            raise CalaConfigError("No Cala API key: set CALA_API_KEY in .env")

        return cls(settings.cala_api_key.get_secret_value(), timeout)

    async def __aenter__(self) -> "CalaClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: types.TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        await self.client.aclose()

    async def search_entities(self, name: str, limit: int = 20) -> list[Entity]:
        """Entities whose name matches `name`, most relevant first (Cala allows limit 1-100)."""
        query_params = {"name": name, "limit": str(limit)}
        response = await self._request("GET", "/v1/entities", params=query_params)
        return self._parse(response, EntitySearchResponse).entities

    async def search(self, question: str) -> SearchAnswer:
        """A natural-language answer with the facts and sources it rests on.

        A POST only to carry the question: it's a read, so it's idempotent and safe to retry.
        """
        body = {"input": question, "explainability": False, "return_entities": True}
        response = await self._request("POST", "/v1/knowledge/search", json=body)
        return self._parse(response, SearchAnswer)

    async def get_entity(
        self,
        entity_id: UUID,
        relationship: str | None = None,
        *,
        direction: Literal["outgoing", "incoming"] = "outgoing",
        limit: int = 10,
        offset: int = 0,
    ) -> EntityDetails:
        """One entity's details, plus one page (limit/offset) of one relationship type if asked.

        Direction is relative to this entity: outgoing = it is the subject (Apple IS_REGISTERED_IN
        United States), incoming = it is the object (Tim Cook IS_BOARD_MEMBER_OF Apple).
        """
        body: dict[str, Any] = {}  # no relationship asked for → send {} (Cala's default properties)
        if relationship is not None:
            body["relationships"] = {direction: {relationship: {"limit": limit, "offset": offset}}}
        response = await self._request("POST", f"/v1/entities/{entity_id}", json=body)
        return self._parse(response, EntityDetails)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx2.Response:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception(_should_retry),
            stop=stop_after_attempt(MAX_ATTEMPTS),
            wait=_wait,
            sleep=self._sleep,
            reraise=True,
            before_sleep=_log_retry,
        ):
            with attempt:
                try:
                    response = await self.client.request(method, path, params=params, json=json)
                except httpx2.TransportError as err:  # timeouts, DNS, connection refused...
                    raise CalaConnectionError(f"{method} {path}: no response ({err!r})") from err
                self._raise_for_error(response)
                return response  # inside `with attempt`: a success ends the retry loop
        raise AssertionError("unreachable")  # mypy: reraise=True never reaches here

    @staticmethod
    def _parse[M: BaseModel](response: httpx2.Response, model: type[M]) -> M:
        """Turn a successful response into `model`; a body that doesn't fit is Cala's fault."""
        try:
            return model.model_validate_json(response.content)
        except ValidationError as err:
            raise CalaResponseError(
                f"Unexpected response body for {model.__name__}: {_snippet(response)}"
            ) from err

    @staticmethod
    def _raise_for_error(response: httpx2.Response) -> None:
        """Map an error status to a CalaError subclass. The status decides; the body adds detail."""
        status_code = response.status_code

        if status_code == 422:
            error = _json_dict(response).get("error")
            if isinstance(error, dict):
                error_type = str(error.get("error_type", "unknown"))
                message = str(error.get("message", "no message"))
            else:  # not the documented shape (or not JSON at all): still a validation error
                error_type, message = "unknown", _snippet(response)
            raise CalaValidationError(message, error_type)

        if status_code == 429:
            cala_message = _json_dict(response).get("message")
            raise CalaRateLimitError(
                cala_message if isinstance(cala_message, str) else "Rate limit exceeded",
                _parse_retry_after(response.headers.get("retry-after")),
            )

        if response.is_server_error:
            raise CalaServerError(f"Cala server error {status_code}: {_snippet(response)}")

        if response.is_client_error:
            raise CalaError(f"Cala client error {status_code}: {_snippet(response)}")


def _json_dict(response: httpx2.Response) -> dict[str, Any]:
    """The body as a JSON object, or {} if it isn't one (HTML from a proxy, a list, garbage)."""
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _parse_retry_after(value: str | None) -> float | None:
    """Seconds from a Retry-After header; None if missing or not a non-negative number.

    The header may also be an HTTP date; Cala doesn't document it, so that counts as unknown.
    """
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def _snippet(response: httpx2.Response, limit: int = 200) -> str:
    """The start of the body, for error messages: enough to debug, not a whole HTML page."""
    return response.text[:limit]


_backoff = wait_exponential_jitter(multiplier=0.5, max=8)


def _wait(retry_state: RetryCallState) -> float:
    """How long to wait: Cala's Retry-After if it gave one, else exponential backoff with jitter."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, CalaRateLimitError) and exc.retry_after is not None:
        return exc.retry_after
    return _backoff(retry_state)


def _should_retry(exc: BaseException) -> bool:
    """Retry rate limits (unless Cala asks for too long a wait), 5xx and network failures."""
    if isinstance(exc, CalaRateLimitError) and exc.retry_after is not None:
        return exc.retry_after <= MAX_RETRY_AFTER
    return isinstance(exc, (CalaRateLimitError, CalaServerError, CalaConnectionError))


def _log_retry(retry_state: RetryCallState) -> None:
    """One WARNING per retry: which attempt failed, why, and how long until the next one."""
    logger.warning(
        "Cala request failed (%s); attempt %d, retrying in %.1fs",
        retry_state.outcome.exception() if retry_state.outcome else None,
        retry_state.attempt_number,
        # %.1f can't format None; next_action is always set in before_sleep, but don't bet the log
        retry_state.next_action.sleep if retry_state.next_action else 0.0,
    )
