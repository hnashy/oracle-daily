"""Robust EPL team name normalizer for ORACLE Data Surgery (Phase 1).

Maps common OddsHarvester / bookmaker short names and variants
to a single canonical key that matches OpenFootball 2024-25 names
after stripping FC/AFC suffixes.
"""
from __future__ import annotations
import re
from typing import Optional

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
    """Return a stable canonical key for matching."""
    raw = clean(name)
    if raw in CANONICAL:
        return CANONICAL[raw]
    parts = raw.split()
    for i in range(len(parts), 0, -1):
        candidate = " ".join(parts[:i])
        if candidate in CANONICAL:
            return CANONICAL[candidate]
    return raw

if __name__ == "__main__":
    openfootball = [
        "AFC Bournemouth", "Arsenal FC", "Aston Villa FC", "Brentford FC",
        "Brighton & Hove Albion FC", "Chelsea FC", "Crystal Palace FC",
        "Everton FC", "Fulham FC", "Ipswich Town FC", "Leicester City FC",
        "Liverpool FC", "Manchester City FC", "Manchester United FC",
        "Newcastle United FC", "Nottingham Forest FC", "Southampton FC",
        "Tottenham Hotspur FC", "West Ham United FC", "Wolverhampton Wanderers FC"
    ]
    odds_variants = [
        "Bournemouth", "Arsenal", "Aston Villa", "Brentford", "Brighton",
        "Chelsea", "Crystal Palace", "Everton", "Fulham", "Ipswich",
        "Leicester", "Liverpool", "Man City", "Man Utd", "Newcastle",
        "Nott'm Forest", "Southampton", "Tottenham", "West Ham", "Wolves",
        "Manchester United", "Brighton & Hove Albion", "Wolverhampton Wanderers",
        "Spurs", "Forest", "Saints"
    ]
    print("=== OpenFootball → canonical ===")
    for t in openfootball:
        print(f"{t:40s} → {normalize_team(t)}")
    print("\n=== Odds variants → canonical ===")
    for t in odds_variants:
        print(f"{t:40s} → {normalize_team(t)}")
