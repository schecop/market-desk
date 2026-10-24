"""The agent's tools: typed functions plus the definitions the model reads.

TOOLS["get_company_facts"].definition()   # what goes in the API's tools=[...]
await TOOLS[name].run(ctx, arguments)     # what runs when the model asks for it
"""

from market_desk.tools.base import Tool, ToolContext, ToolError
from market_desk.tools.companies import COMPANY_FACTS
from market_desk.tools.filings import SEARCH_FILINGS
from market_desk.tools.watchlist import ADD_TO_WATCHLIST, LIST_WATCHLIST, REMOVE_FROM_WATCHLIST

# The registry: the model names a tool, the loop looks it up here
TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        COMPANY_FACTS,
        SEARCH_FILINGS,
        LIST_WATCHLIST,
        ADD_TO_WATCHLIST,
        REMOVE_FROM_WATCHLIST,
    )
}

__all__ = ["TOOLS", "Tool", "ToolContext", "ToolError"]
