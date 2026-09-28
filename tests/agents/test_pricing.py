from __future__ import annotations

import json
import pathlib

from app.agents import llm


def test_unpriced_model_costs_zero_rather_than_guessing(tmp_path: pathlib.Path) -> None:
    empty = tmp_path / "pricing.json"
    empty.write_text(json.dumps({"models": {}}))
    llm._pricing = None
    llm.PRICING_PATH = empty
    assert llm.price_usd("some-model", 1_000_000, 1_000_000) == 0.0


def test_configured_model_is_priced_per_million(tmp_path: pathlib.Path) -> None:
    priced = tmp_path / "pricing.json"
    priced.write_text(json.dumps({"models": {"m": {"input": 3.0, "output": 15.0}}}))
    llm._pricing = None
    llm.PRICING_PATH = priced
    assert llm.price_usd("m", 1_000_000, 0) == 3.0
    assert llm.price_usd("m", 0, 1_000_000) == 15.0
    assert llm.price_usd("m", 500_000, 100_000) == 1.5 + 1.5


def test_missing_pricing_file_does_not_crash(tmp_path: pathlib.Path) -> None:
    llm._pricing = None
    llm.PRICING_PATH = tmp_path / "nope.json"
    assert llm.price_usd("m", 100, 100) == 0.0
