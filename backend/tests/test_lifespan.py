"""The API starts the filing check timer only when an interval is configured."""

import asyncio

import pytest
from fastapi.testclient import TestClient

import market_desk.api.main as main
from market_desk.config import Settings


def start_api(monkeypatch: pytest.MonkeyPatch, interval: float) -> list[float]:
    """Start and stop the app; return the intervals the (fake) loop was started with."""
    started: list[float] = []

    async def fake_loop(minutes: float) -> None:
        started.append(minutes)
        await asyncio.Event().wait()  # runs until cancelled, like the real loop

    monkeypatch.setattr(main, "filing_check_loop", fake_loop)
    monkeypatch.setattr(
        main, "get_settings", lambda: Settings(filing_check_interval_minutes=interval)
    )
    with TestClient(main.app):  # entering runs startup, leaving runs shutdown
        pass
    return started


def test_loop_starts_when_an_interval_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    assert start_api(monkeypatch, interval=60) == [60]


def test_loop_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    assert start_api(monkeypatch, interval=0) == []
