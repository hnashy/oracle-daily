#!/usr/bin/env python3
"""Auto-fetch EPL (or other) fixtures/results from OpenFootball football.json.

No API key. Writes:
  data/raw/weekly/fixtures_{league}.json  — upcoming (no FT score yet)
  data/raw/weekly/results_{league}.json   — recently finished (for learn)

Usage:
  python tools/fetch_openfootball_week.py --league en.1 --season 2026-27
  python tools/fetch_openfootball_week.py --league en.1 --season auto
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

LEAGUE_FILES = {
    "en.1": "en.1.json",
    "es.1": "es.1.json",
    "it.1": "it.1.json",
    "de.1": "de.1.json",
    "fr.1": "fr.1.json",
}


def detect_season(now: datetime | None = None) -> str:
    """Rough European season label: Aug–Jul → YYYY-(YYYY+1)."""
    now = now or datetime.now(timezone.utc)
    y = now.year
    if now.month >= 8:
        return f"{y}-{str(y + 1)[2:]}" if False else f"{y}-{y + 1}"
    return f"{y - 1}-{y}"


def load_season(season: str, league_file: str) -> dict:
    url = f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/{league_file}"
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        raise SystemExit(f"Failed to fetch {url}: {e}")


def has_ft(m: dict) -> bool:
    sc = m.get("score")
    if not isinstance(sc, dict):
        return False
    ft = sc.get("ft")
    return isinstance(ft, (list, tuple)) and len(ft) == 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default="en.1", choices=list(LEAGUE_FILES.keys()))
    ap.add_argument("--season", default="auto", help="e.g. 2026-27 or auto")
    ap.add_argument("--upcoming-days", type=int, default=10, help="Window for upcoming fixtures")
    ap.add_argument("--results-days", type=int, default=10, help="Window for recent results")
    ap.add_argument("--out-dir", type=Path, default=Path("data/raw/weekly"))
    args = ap.parse_args()

    season = detect_season() if args.season == "auto" else args.season
    league_file = LEAGUE_FILES[args.league]
    data = load_season(season, league_file)
    matches = data.get("matches") or []

    now = datetime.now(timezone.utc)
    today = now.date()
    upcoming_until = today + timedelta(days=args.upcoming_days)
    results_from = today - timedelta(days=args.results_days)

    fixtures = []
    results = []

    for m in matches:
        date_s = m.get("date")
        if not date_s:
            continue
        try:
            d = datetime.strptime(date_s, "%Y-%m-%d").date()
        except ValueError:
            continue

        home = m.get("team1")
        away = m.get("team2")
        if not home or not away:
            continue

        if has_ft(m):
            if results_from <= d <= today:
                ft = m["score"]["ft"]
                results.append({
                    "home": home,
                    "away": away,
                    "gh": int(ft[0]),
                    "ga": int(ft[1]),
                    "date": date_s,
                    "round": m.get("round"),
                    "source": "openfootball",
                    "season": season,
                })
        else:
            # upcoming / not played
            if today <= d <= upcoming_until:
                fixtures.append({
                    "home": home,
                    "away": away,
                    "date": date_s,
                    "time": m.get("time"),
                    "round": m.get("round"),
                    "source": "openfootball",
                    "season": season,
                    # odds optional — filled later if available
                })

    args.out_dir.mkdir(parents=True, exist_ok=True)
    fix_path = args.out_dir / f"fixtures_{args.league}.json"
    res_path = args.out_dir / f"results_{args.league}.json"
    fix_path.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2) + "\n")
    res_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")

    print(json.dumps({
        "season": season,
        "league": args.league,
        "name": data.get("name"),
        "upcoming_fixtures": len(fixtures),
        "recent_results": len(results),
        "fixtures_file": str(fix_path),
        "results_file": str(res_path),
        "window_upcoming_days": args.upcoming_days,
        "window_results_days": args.results_days,
    }, indent=2))


if __name__ == "__main__":
    main()
