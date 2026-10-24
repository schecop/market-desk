"""search_filings: a company's SEC filings from EDGAR (metadata and links; text in Sprint 3)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from market_desk.clients.edgar import ARCHIVES_URL, EdgarNotFoundError
from market_desk.tools.base import Tool, ToolContext, ToolError


class SearchFilingsInput(BaseModel):
    ticker: str = Field(description="Stock ticker, e.g. 'AAPL'")
    form: Literal["10-K", "10-Q", "8-K"] = Field(
        default="10-K", description="10-K annual report, 10-Q quarterly report, 8-K current event"
    )
    limit: int = Field(default=5, ge=1, le=20, description="How many filings, newest first")


class FilingSummary(BaseModel):
    form: str
    filing_date: date
    report_date: date | None = None
    accession_number: str
    url: str


class FilingList(BaseModel):
    company: str
    cik: int
    filings: list[FilingSummary]


async def search_filings(ctx: ToolContext, params: SearchFilingsInput) -> FilingList:
    try:
        company = await ctx.edgar.get_company(params.ticker)
    except EdgarNotFoundError as err:
        raise ToolError(
            f"No SEC company with ticker {params.ticker.upper()}; "
            "check the ticker or look it up with get_company_facts."
        ) from err

    filings = await ctx.edgar.list_filings(company.cik, form=params.form, limit=params.limit)
    return FilingList(
        company=company.name,
        cik=company.cik,
        filings=[
            FilingSummary(
                form=f.form,
                filing_date=f.filing_date,
                report_date=f.report_date,
                accession_number=f.accession_number,
                url=ARCHIVES_URL.format(
                    cik=company.cik,
                    accession=f.accession_number.replace("-", ""),
                    document=f.primary_document,
                ),
            )
            for f in filings
        ],
    )


SEARCH_FILINGS = Tool(
    name="search_filings",
    description=(
        "List a public company's recent SEC filings (form, dates, link to the document), "
        "newest first. Use it to find which filings exist and when they were filed. It returns "
        "no filing text yet, so it can't answer what a filing says (risks, strategy); say so "
        "rather than guess."
    ),
    input_model=SearchFilingsInput,
    handler=search_filings,
)
