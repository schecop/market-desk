"""The agent's tools: definitions the model reads, and handlers run against fakes."""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx2
import pytest
from fakes import APPLE_CIK, NEWEST, make_edgar, no_sleep
from pydantic import ValidationError
from sqlalchemy.orm import Session

from market_desk.clients.cala import CalaClient
from market_desk.db.models import Client
from market_desk.tools import TOOLS, ToolContext, ToolError

APPLE_ID = "e5bb591a-d308-4aa5-9672-96046d366cde"
RECORDS_ID = "0b0b0b0b-0000-4000-8000-000000000000"
# "Apple" also matches a record label; the tool must skip it and pick the company
APPLE_MATCHES = {
    "entities": [
        {"id": RECORDS_ID, "name": "Apple Records", "entity_type": "Organization"},
        {"id": APPLE_ID, "name": "Apple Inc.", "entity_type": "Company"},
    ]
}
APPLE_DETAILS = {
    "id": APPLE_ID,
    "name": "Apple Inc.",
    "entity_type": "Company",
    "description": "Consumer electronics company.",
    "properties": {
        "aliases": {"sources": [{"name": "SEC"}], "value": ["Apple", "AAPL"]},
        "founded": {"sources": [{"name": "Wikipedia"}, {"name": "SEC"}], "value": "1976"},
    },
    "relationships": {},
}


def fake_cala(request: httpx2.Request) -> httpx2.Response:
    """Search finds Apple only by "Apple"; entity details exist only for Apple Inc."""
    if request.method == "GET" and request.url.path == "/v1/entities":
        found = request.url.params["name"] == "Apple"
        return httpx2.Response(200, json=APPLE_MATCHES if found else {"entities": []})
    if request.method == "POST" and request.url.path == f"/v1/entities/{APPLE_ID}":
        return httpx2.Response(200, json=APPLE_DETAILS)
    return httpx2.Response(404)


@pytest.fixture
async def ctx(db_session: Session, client_id: int) -> AsyncIterator[ToolContext]:
    cala = CalaClient("test-key", 5, transport=httpx2.MockTransport(fake_cala), sleep=no_sleep)
    async with cala, make_edgar() as edgar:
        yield ToolContext(client_id=client_id, session=db_session, cala=cala, edgar=edgar)


async def run(ctx: ToolContext, name: str, **arguments: Any) -> Any:
    """Run a tool the way the loop will, and decode the JSON it returns."""
    return json.loads(await TOOLS[name].run(ctx, arguments))


# --- definitions: what the model sees ---


def test_every_definition_has_the_shape_the_api_expects() -> None:
    for name, tool in TOOLS.items():
        definition = tool.definition()
        assert definition["name"] == name
        assert definition["description"]
        assert definition["input_schema"]["type"] == "object"


def test_schema_comes_from_the_input_model() -> None:
    schema = TOOLS["search_filings"].definition()["input_schema"]

    assert schema["required"] == ["ticker"]
    assert schema["properties"]["form"]["enum"] == ["10-K", "10-Q", "8-K"]
    assert schema["properties"]["limit"]["maximum"] == 20


def test_only_watchlist_changes_are_write_tools() -> None:
    writes = {name for name, tool in TOOLS.items() if tool.writes}
    assert writes == {"add_to_watchlist", "remove_from_watchlist"}


# --- arguments: the model can get them wrong ---


@pytest.mark.anyio
async def test_bad_arguments_raise_before_the_handler_runs(ctx: ToolContext) -> None:
    with pytest.raises(ValidationError):
        await run(ctx, "search_filings", ticker="AAPL", form="S-1")
    with pytest.raises(ValidationError):
        await run(ctx, "get_company_facts")  # company is required


# --- get_company_facts ---


@pytest.mark.anyio
async def test_company_facts_picks_the_company_and_flattens_properties(ctx: ToolContext) -> None:
    result = await run(ctx, "get_company_facts", company="Apple")

    assert result == {
        "name": "Apple Inc.",
        "description": "Consumer electronics company.",
        "facts": {"aliases": ["Apple", "AAPL"], "founded": "1976"},
        "sources": ["SEC", "Wikipedia"],
    }


@pytest.mark.anyio
async def test_company_facts_unknown_company_is_a_tool_error(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="no company matching 'Nonexistent'"):
        await run(ctx, "get_company_facts", company="Nonexistent")


# --- search_filings ---


@pytest.mark.anyio
async def test_search_filings_lists_newest_first_with_document_links(ctx: ToolContext) -> None:
    result = await run(ctx, "search_filings", ticker="aapl", limit=1)

    assert (result["company"], result["cik"]) == ("Apple Inc.", APPLE_CIK)
    [filing] = result["filings"]
    assert filing["accession_number"] == NEWEST
    assert filing["url"].startswith(
        f"https://www.sec.gov/Archives/edgar/data/{APPLE_CIK}/{NEWEST.replace('-', '')}/"
    )


@pytest.mark.anyio
async def test_search_filings_unknown_ticker_raises(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="ZZZZ"):
        await run(ctx, "search_filings", ticker="ZZZZ")


# --- watchlist ---


@pytest.mark.anyio
async def test_watchlist_add_list_remove(ctx: ToolContext) -> None:
    added = await run(ctx, "add_to_watchlist", ticker="aapl")
    assert (added["ticker"], added["name"]) == ("AAPL", "Apple Inc.")

    listed = await run(ctx, "list_watchlist")
    assert [c["ticker"] for c in listed["companies"]] == ["AAPL"]

    assert await run(ctx, "remove_from_watchlist", ticker="aapl") == {
        "ticker": "AAPL",
        "removed": True,
    }
    assert await run(ctx, "remove_from_watchlist", ticker="AAPL") == {
        "ticker": "AAPL",
        "removed": False,
    }


@pytest.mark.anyio
async def test_adding_twice_is_a_tool_error(ctx: ToolContext) -> None:
    await run(ctx, "add_to_watchlist", ticker="AAPL")
    with pytest.raises(ToolError, match="already on the watchlist"):
        await run(ctx, "add_to_watchlist", ticker="AAPL")


@pytest.mark.anyio
async def test_add_to_watchlist_unknown_ticker_raises(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="ZZZZ"):
        await run(ctx, "add_to_watchlist", ticker="ZZZZ")


@pytest.mark.anyio
async def test_tools_only_see_the_context_clients_watchlist(ctx: ToolContext) -> None:
    other = Client(slug="other", name="Other client")
    ctx.session.add(other)
    ctx.session.commit()
    other_ctx = ToolContext(client_id=other.id, session=ctx.session, cala=ctx.cala, edgar=ctx.edgar)

    await run(other_ctx, "add_to_watchlist", ticker="AAPL")

    assert await run(ctx, "list_watchlist") == {"companies": []}
    assert await run(ctx, "remove_from_watchlist", ticker="AAPL") == {
        "ticker": "AAPL",
        "removed": False,
    }
    listed = await run(other_ctx, "list_watchlist")
    assert [c["ticker"] for c in listed["companies"]] == ["AAPL"]
