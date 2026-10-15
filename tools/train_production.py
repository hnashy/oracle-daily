#!/usr/bin/env python3
"""Train ProductionOracle on full football-data.co.uk season JSON and save state."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from production_oracle import ProductionOracle


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw", type=Path, help="football-data style JSON (list of matches)")
    ap.add_argument("--out", type=Path, default=Path("data/models/oracle_en1_2024-25.json"))
    ap.add_argument("--league", default="en.1")
    ap.add_argument("--season", default="2024-25")
    args = ap.parse_args()

    raw = json.loads(args.raw.read_text(encoding="utf-8"))
    matches = []
    for r in raw:
        home = r.get("HomeTeam")
        away = r.get("AwayTeam")
        if not home or not away:
            continue
        date_raw = r.get("Date")
        time_raw = r.get("Time") or "15:00"
        try:
            dt = datetime.strptime(f"{date_raw} {time_raw}", "%d/%m/%Y %H:%M")
            ts = dt.replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            continue
        gh = int(r["FTHG"])
        ga = int(r["FTAG"])
        matches.append((ts, home, away, gh, ga))

    matches.sort(key=lambda x: x[0])
    model = ProductionOracle(league=args.league, season=args.season)
    for ts, h, a, gh, ga in matches:
        model.update(h, a, gh, ga, ts)

    model.save(args.out)
    print(json.dumps({
        "matches_trained": model.matches_trained,
        "teams": len(model.att),
        "home_g": round(model.home_g, 4),
        "away_g": round(model.away_g, 4),
        "market_weight": model.market_weight,
        "saved_to": str(args.out),
    }, indent=2))


if __name__ == "__main__":
    main()
