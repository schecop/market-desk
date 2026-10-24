"""get_company_facts: verified, structured facts about a company from Cala."""

from typing import Any

from pydantic import BaseModel, Field

from market_desk.tools.base import Tool, ToolContext, ToolError

# Cala matches names loosely ("Apple" also finds Apple Records); look at a few, keep a company
CANDIDATES = 5


class CompanyFactsInput(BaseModel):
    company: str = Field(description="Company name or ticker, e.g. 'Apple' or 'AAPL'")


class CompanyFacts(BaseModel):
    name: str
    description: str | None = None
    # Property name → value, e.g. {"aliases": ["Apple", "AAPL"]}
    facts: dict[str, Any]
    # Names of the sources behind the facts, so the answer can cite them
    sources: list[str]


async def get_company_facts(ctx: ToolContext, params: CompanyFactsInput) -> CompanyFacts:
    matches = await ctx.cala.search_entities(params.company, limit=CANDIDATES)
    company = next((m for m in matches if m.entity_type == "Company"), None)
    if company is None:
        raise ToolError(f"Cala has no company matching {params.company!r}; try its full name.")

    details = await ctx.cala.get_entity(company.id)
    # Cala wraps each property as {"value": ..., "sources": [...]}; the model only needs the
    # values, plus one deduplicated list of sources instead of one per property.
    facts: dict[str, Any] = {}
    sources: set[str] = set()
    for key, prop in details.properties.items():
        if isinstance(prop, dict) and "value" in prop:
            facts[key] = prop["value"]
            sources.update(_source_names(prop.get("sources", [])))
        else:  # an unwrapped property: keep it as it is
            facts[key] = prop
    return CompanyFacts(
        name=details.name,
        description=details.description,
        facts=facts,
        sources=sorted(sources),
    )


def _source_names(raw: list[Any]) -> list[str]:
    """Tolerant: a source may be a {"name": ...} object or a plain string."""
    names = []
    for source in raw:
        if isinstance(source, dict) and isinstance(source.get("name"), str):
            names.append(source["name"])
        elif isinstance(source, str):
            names.append(source)
    return names


COMPANY_FACTS = Tool(
    name="get_company_facts",
    description=(
        "Verified, structured facts about one public company from Cala's knowledge base: "
        "identity, aliases and tickers, and other recorded properties, with their sources. "
        "Use it to identify a company and for exact facts. It does not contain what a company "
        "says about itself (strategy, risks, outlook): use search_filings for that."
    ),
    input_model=CompanyFactsInput,
    handler=get_company_facts,
)
