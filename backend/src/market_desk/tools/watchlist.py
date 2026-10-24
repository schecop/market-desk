"""Watchlist tools: thin wrappers over market_desk.watchlist, which owns the logic."""

from datetime import datetime

from pydantic import BaseModel, Field

from market_desk import watchlist
from market_desk.db.models import WatchlistEntry
from market_desk.tools.base import Tool, ToolContext, ToolError


class NoInput(BaseModel):
    pass


class TickerInput(BaseModel):
    ticker: str = Field(description="Stock ticker, e.g. 'AAPL'")


class WatchedCompany(BaseModel):
    ticker: str
    name: str
    added_at: datetime | None = None

    @classmethod
    def from_entry(cls, entry: WatchlistEntry) -> "WatchedCompany":
        return cls(ticker=entry.ticker, name=entry.name, added_at=entry.added_at)


class Watchlist(BaseModel):
    companies: list[WatchedCompany]


class Removed(BaseModel):
    ticker: str
    removed: bool


async def list_watchlist(ctx: ToolContext, params: NoInput) -> Watchlist:
    entries = watchlist.list_watchlist(ctx.session)
    return Watchlist(companies=[WatchedCompany.from_entry(e) for e in entries])


async def add_to_watchlist(ctx: ToolContext, params: TickerInput) -> WatchedCompany:
    try:
        entry = await watchlist.add_to_watchlist(ctx.session, ctx.edgar, params.ticker)
    except watchlist.AlreadyWatchedError as exc:
        raise ToolError(str(exc)) from exc
    except watchlist.UnknownTickerError as exc:
        raise ToolError(f"{exc}; check the ticker or look it up with get_company_facts.") from exc
    # Any other EdgarError (SEC down, malformed response) is not the model's to fix: let it
    # propagate, and the loop decides what to log and what to tell the model.
    return WatchedCompany.from_entry(entry)


async def remove_from_watchlist(ctx: ToolContext, params: TickerInput) -> Removed:
    removed = watchlist.remove_from_watchlist(ctx.session, params.ticker)
    # Not an error: "it wasn't there" is a fine answer, and the model can say so
    return Removed(ticker=params.ticker.upper(), removed=removed)


LIST_WATCHLIST = Tool(
    name="list_watchlist",
    description=(
        "The companies on the user's watchlist (ticker, name, when added). Use it whenever the "
        "user says 'my watchlist' or 'my companies'."
    ),
    input_model=NoInput,
    handler=list_watchlist,
)

ADD_TO_WATCHLIST = Tool(
    name="add_to_watchlist",
    description=(
        "Add a company to the user's watchlist by ticker; the user then gets an alert when it "
        "files a new 10-K. Only when the user asks for it."
    ),
    input_model=TickerInput,
    handler=add_to_watchlist,
    writes=True,
)

REMOVE_FROM_WATCHLIST = Tool(
    name="remove_from_watchlist",
    description=(
        "Remove a company from the user's watchlist by ticker. Only when the user asks for it."
    ),
    input_model=TickerInput,
    handler=remove_from_watchlist,
    writes=True,
)
