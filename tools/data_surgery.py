#!/usr/bin/env python3
"""ORACLE Phase 1 — Data Surgery

Strict matching between OddsHarvester records and OpenFootball fixtures.
Goal: raise Match Rate to >95% by fixing team names and match_date.

Usage:
  python tools/data_surgery.py data/raw/odds_history.json reports/data_surgery_report.json
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ───────────────────────── Team Normalizer (Phase 1 improved) ─────────────────

CANONICAL = {
    "bournemouth": "bournemouth", "afc bournemouth": "bournemouth", "bournemouth afc": "bournemouth",
    "arsenal": "arsenal", "arsenal fc": "arsenal",
    "aston villa": "aston villa", "villa": "aston villa",
    "brentford": "brentford", "brentford fc": "brentford",
    "brighton": "brighton hove albion", "brighton and hove albion": "brighton hove albion",
    "brighton hove albion": "brighton hove albion", "brighton & hove albion": "brighton hove albion",
    "brighton & hove": "brighton hove albion",
    "chelsea": "chelsea", "chelsea fc": "chelsea",
    "crystal palace": "crystal palace", "palace": "crystal palace",
    "everton": "everton", "everton fc": "everton",
    "fulham": "fulham", "fulham fc": "fulham",
    "ipswich": "ipswich town", "ipswich town": "ipswich town",
    "leicester": "leicester city", "leicester city": "leicester city",
    "liverpool": "liverpool", "liverpool fc": "liverpool",
    "manchester city": "manchester city", "man city": "manchester city", "mancity": "manchester city",
    "manchester united": "manchester united", "manchester utd": "manchester united",
    "man utd": "manchester united", "man united": "manchester united", "manu": "manchester united",
    "manchester u": "manchester united",
    "newcastle": "newcastle united", "newcastle united": "newcastle united", "newcastle utd": "newcastle united",
    "nottingham forest": "nottingham forest", "nottingham": "nottingham forest",
    "notts forest": "nottingham forest", "forest": "nottingham forest",
    "nott m forest": "nottingham forest", "nottm forest": "nottingham forest",
    "nott forest": "nottingham forest", "nott forest": "nottingham forest",
    "southampton": "southampton", "saints": "southampton",
    "tottenham": "tottenham hotspur", "tottenham hotspur": "tottenham hotspur",
    "spurs": "tottenham hotspur", "tottenham hotspurs": "tottenham hotspur",
    "west ham": "west ham united", "west ham united": "west ham united", "westham": "west ham united",
    "wolves": "wolverhampton wanderers", "wolverhampton": "wolverhampton wanderers",
    "wolverhampton wanderers": "wolverhampton wanderers",
}

def clean(s: str) -> str:
    s = str(s or "").lower().strip()
    s = s.replace("&", "and")
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"\b(afc|fc|cf|sc)\b", " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def normalize_team(name: str) -> str:
    raw = clean(name)
    if raw in CANONICAL:
        return CANONICAL[raw]
    parts = raw.split()
    for i in range(len(parts), 0, -1):
        candidate = " ".join(parts[:i])
        if candidate in CANONICAL:
            return CANONICAL[candidate]
    return raw

# ───────────────────────── Date helpers ──────────────────────────────────────

def parse_date(value: Any) -> str | None:
    if not value:
        return None
    s = str(value).strip()
    m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1)
    m = re.search(r"(\d{1,2})[/\.](\d{1,2})[/\.](\d{4})", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if d > 12:
            return f"{y:04d}-{mo:02d}-{d:02d}"
    return None

def parse_ts(value: Any) -> float | None:
    if not value:
        return None
    s = str(value).replace(" UTC", "Z").replace(" ", "T")
    if not re.search(r"[Zz]|[+\-]\d{2}:?\d{2}$", s):
        s += "Z"
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None

# ───────────────────────── OpenFootball fixtures ─────────────────────────────

def load_openfootball(season: str = "2024-25") -> list[dict]:
    url = f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/en.1.json"
    data = json.load(urllib.request.urlopen(url))
    fixtures = []
    for m in data.get("matches", []):
        sc = m.get("score", {}).get("ft")
        if not sc or len(sc) != 2:
            continue
        date = m.get("date")
        time = m.get("time") or "15:00"
        ts = parse_ts(f"{date} {time}")
        fixtures.append({
            "date": date,
            "time": time,
            "home": m["team1"],
            "away": m["team2"],
            "home_key": normalize_team(m["team1"]),
            "away_key": normalize_team(m["team2"]),
            "gh": int(sc[0]),
            "ga": int(sc[1]),
            "ts": ts,
            "key": f"{date}|{normalize_team(m['team1'])}|{normalize_team(m['team2'])}",
        })
    return fixtures

# ───────────────────────── Main surgery ──────────────────────────────────────

def surgery(raw_path: Path, out_path: Path, season: str = "2024-25") -> dict:
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        records = raw.get("matches") or raw.get("data") or raw.get("results") or [raw]
    else:
        records = raw

    fixtures = load_openfootball(season)
    fixture_by_key = {f["key"]: f for f in fixtures}
    by_teams: dict[str, list] = defaultdict(list)
    for f in fixtures:
        by_teams[f"{f['home_key']}|{f['away_key']}"].append(f)

    reasons = Counter()
    matched = []
    excluded = []

    for i, rec in enumerate(records):
        home = rec.get("home_team") or rec.get("home") or rec.get("team1")
        away = rec.get("away_team") or rec.get("away") or rec.get("team2")
        date_raw = rec.get("match_date") or rec.get("kickoff") or rec.get("date") or rec.get("start_time")

        if not home or not away:
            reasons["missing_team_names"] += 1
            excluded.append({"index": i, "reason": "missing_team_names", "home": home, "away": away})
            continue

        home_key = normalize_team(home)
        away_key = normalize_team(away)
        date = parse_date(date_raw)

        if not date:
            candidates = by_teams.get(f"{home_key}|{away_key}", [])
            if len(candidates) == 1:
                date = candidates[0]["date"]
                reasons["date_recovered_from_teams"] += 1
            else:
                reasons["missing_match_date"] += 1
                excluded.append({
                    "index": i, "reason": "missing_match_date",
                    "home": home, "away": away, "home_key": home_key, "away_key": away_key,
                    "raw_date": date_raw
                })
                continue

        key = f"{date}|{home_key}|{away_key}"
        fix = fixture_by_key.get(key)
        if not fix:
            reasons["no_model_fixture_match"] += 1
            excluded.append({
                "index": i, "reason": "no_model_fixture_match",
                "home": home, "away": away,
                "home_key": home_key, "away_key": away_key,
                "date": date, "raw_date": date_raw
            })
            continue

        scraped = parse_ts(rec.get("scraped_at_utc") or rec.get("scraped_at") or rec.get("collected_at"))
        if scraped is not None and fix["ts"] is not None and scraped >= fix["ts"]:
            reasons["post_kickoff_quote"] += 1
            excluded.append({"index": i, "reason": "post_kickoff_quote", "home": home, "away": away, "date": date})
            continue

        matched.append({
            "index": i,
            "home": home, "away": away,
            "home_key": home_key, "away_key": away_key,
            "date": date,
            "fixture_home": fix["home"], "fixture_away": fix["away"],
            "gh": fix["gh"], "ga": fix["ga"],
            "ts": fix["ts"],
            "key": key,
        })
        reasons["matched"] += 1

    total = len(records)
    match_rate = reasons["matched"] / total if total else 0.0

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "phase": "1_data_surgery",
        "season": season,
        "source": str(raw_path),
        "total_records": total,
        "matched": reasons["matched"],
        "match_rate": round(match_rate, 4),
        "success_criterion": ">0.95",
        "criterion_met": match_rate >= 0.95,
        "exclusion_reasons": dict(reasons),
        "excluded_sample": excluded[:50],
        "excluded_total": len(excluded),
        "notes": [
            "Team names normalized with expanded EPL alias dictionary.",
            "Dates extracted via regex YYYY-MM-DD; recovery attempted from unique team-pair when date missing.",
            "Post-kickoff quotes are discarded (leakage guard).",
            "If match_rate < 0.95 the remaining failures are listed under excluded_sample.",
        ],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "excluded_sample"}, ensure_ascii=False, indent=2))
    return report

def main():
    ap = argparse.ArgumentParser(description="ORACLE Phase 1 Data Surgery")
    ap.add_argument("raw", type=Path, help="Raw OddsHarvester JSON")
    ap.add_argument("out", type=Path, help="Output report JSON")
    ap.add_argument("--season", default="2024-25")
    args = ap.parse_args()
    surgery(args.raw, args.out, args.season)

if __name__ == "__main__":
    main()
