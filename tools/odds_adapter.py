#!/usr/bin/env python3
"""Normalize OddsHarvester JSON/NDJSON records for ORACLE Daily.

The adapter is deliberately source-agnostic: it accepts a JSON list, an object
with ``matches``/``data``, or newline-delimited JSON produced by OddsHarvester.
It never treats a post-kickoff quote as pre-match data.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LABELS = ("h", "d", "a")
MARKET_ALIASES = {"1": "h", "x": "d", "2": "a", "home": "h", "draw": "d", "away": "a"}


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    for candidate in (text, text.replace(" UTC", "+00:00")):
        try:
            dt = datetime.fromisoformat(candidate)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def slug(value: Any) -> str:
    text = str(value or "").lower().strip()
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text


def records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("matches", "data", "results", "records", "events"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        return [payload]
    return []


def first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if record.get(key) not in (None, ""):
            return record[key]
    return None


def extract_odds(record: dict[str, Any]) -> dict[str, float]:
    raw = record.get("odds") or record.get("best_odds") or record.get("market_odds") or {}
    out: dict[str, float] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            label = MARKET_ALIASES.get(str(key).lower().strip(), str(key).lower().strip())
            if label not in LABELS and isinstance(value, dict):
                label = MARKET_ALIASES.get(str(value.get("outcome", key)).lower().strip(), "")
                value = value.get("odds")
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if label in LABELS and number > 1:
                out[label] = number
    # Some OddsHarvester outputs expose *_odds fields directly.
    for label, keys in {"h": ("home_odds", "odds_home", "1_odds"), "d": ("draw_odds", "odds_draw", "x_odds"), "a": ("away_odds", "odds_away", "2_odds")}.items():
        if label not in out:
            try:
                number = float(first(record, *keys))
                if number > 1:
                    out[label] = number
            except (TypeError, ValueError):
                pass
    return out


def normalize(record: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    home = first(record, "home_team", "home", "team1")
    away = first(record, "away_team", "away", "team2")
    kickoff = parse_time(first(record, "kickoff_utc", "kickoff", "start_time", "date"))
    scraped = parse_time(first(record, "scraped_at_utc", "scraped_at", "collected_at")) or now
    odds = extract_odds(record)
    if not home or not away or not kickoff or len(odds) != 3:
        return None
    # Critical leakage guard: this quote cannot be used pre-match after kickoff.
    if scraped >= kickoff:
        return None
    match_id = first(record, "match_id", "event_id", "match_link") or f"{kickoff.isoformat()}|{slug(home)}|{slug(away)}"
    return {
        "match_id": str(match_id),
        "home_team": str(home),
        "away_team": str(away),
        "kickoff_utc": kickoff.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "league": first(record, "league", "competition", "tournament"),
        "market": "1x2",
        "scraped_at_utc": scraped.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "odds": odds,
        "bookmakers": first(record, "bookmakers", "bookmaker_count"),
        "source": "OddsHarvester/OddsPortal",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    text = args.input.read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = [json.loads(line) for line in text.splitlines() if line.strip()]
    now = datetime.now(timezone.utc)
    normalized = [item for raw in records(payload) if (item := normalize(raw, now))]
    output = {"schema_version": 1, "generated_at_utc": now.isoformat().replace("+00:00", "Z"), "matches": normalized}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"normalized={len(normalized)} dropped={len(records(payload)) - len(normalized)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
