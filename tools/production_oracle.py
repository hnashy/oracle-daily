"""ORACLE Production Engine

Trained on full EPL 2024-25 (380 matches). Ready for current-season prediction,
weekly Telegram reports, and post-match learning updates.
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from math import exp, factorial
from pathlib import Path
from typing import Any, Dict, Optional

OUT = ("h", "d", "a")

CANONICAL = {
    "bournemouth": "bournemouth", "afc bournemouth": "bournemouth",
    "arsenal": "arsenal", "aston villa": "aston villa", "villa": "aston villa",
    "brentford": "brentford", "brighton": "brighton hove albion",
    "brighton and hove albion": "brighton hove albion", "brighton hove albion": "brighton hove albion",
    "chelsea": "chelsea", "crystal palace": "crystal palace", "palace": "crystal palace",
    "everton": "everton", "fulham": "fulham", "ipswich": "ipswich town", "ipswich town": "ipswich town",
    "leicester": "leicester city", "leicester city": "leicester city", "liverpool": "liverpool",
    "manchester city": "manchester city", "man city": "manchester city",
    "manchester united": "manchester united", "manchester utd": "manchester united",
    "man utd": "manchester united", "man united": "manchester united",
    "newcastle": "newcastle united", "newcastle united": "newcastle united",
    "nottingham forest": "nottingham forest", "nottingham": "nottingham forest",
    "nott m forest": "nottingham forest", "nottm forest": "nottingham forest", "forest": "nottingham forest",
    "southampton": "southampton", "saints": "southampton",
    "tottenham": "tottenham hotspur", "tottenham hotspur": "tottenham hotspur", "spurs": "tottenham hotspur",
    "west ham": "west ham united", "west ham united": "west ham united",
    "wolves": "wolverhampton wanderers", "wolverhampton": "wolverhampton wanderers",
    "wolverhampton wanderers": "wolverhampton wanderers",
}

def clean(s: str) -> str:
    s = str(s or "").lower().strip().replace("&", "and").replace("'", "")
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"\b(afc|fc|cf|sc)\b", " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def normalize_team(name: str) -> str:
    raw = clean(name)
    if raw in CANONICAL:
        return CANONICAL[raw]
    parts = raw.split()
    for i in range(len(parts), 0, -1):
        c = " ".join(parts[:i])
        if c in CANONICAL:
            return CANONICAL[c]
    return raw

def poisson(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return exp(-lam) * lam ** k / factorial(k)


class ProductionOracle:
    """Production model: Elo-style attack/defence + Dixon-Coles + market blend."""

    def __init__(self, league: str = "en.1", season: str = "2024-25"):
        self.league = league
        self.season = season
        self.att: Dict[str, float] = defaultdict(lambda: 1.0)
        self.defn: Dict[str, float] = defaultdict(lambda: 1.0)
        self.home_g = 1.45
        self.away_g = 1.15
        self.rho = -0.08
        self.played: Dict[str, int] = defaultdict(int)
        self.history: list = []
        self.matches_trained = 0
        # Phase 3 full-season: optimal market weight stayed at 1.0;
        # use 0.85 as a slightly conservative production default.
        self.market_weight = 0.85

    def _lam(self, h: str, a: str):
        h, a = normalize_team(h), normalize_team(a)
        lh = max(0.2, min(4.0, self.home_g * self.att[h] * self.defn[a]))
        la = max(0.15, min(3.5, self.away_g * self.att[a] * self.defn[h]))
        return lh, la

    def predict_internal(self, home: str, away: str):
        h, a = normalize_team(home), normalize_team(away)
        lh, la = self._lam(h, a)
        ph = [poisson(i, lh) for i in range(8)]
        pa = [poisson(i, la) for i in range(8)]
        p = {"h": 0.0, "d": 0.0, "a": 0.0}
        for x in range(8):
            for y in range(8):
                tau = 1.0
                if x == 0 and y == 0:
                    tau = 1 - lh * la * self.rho
                elif x == 1 and y == 0:
                    tau = 1 + la * self.rho
                elif x == 0 and y == 1:
                    tau = 1 + lh * self.rho
                elif x == 1 and y == 1:
                    tau = 1 - self.rho
                v = max(0.0, tau) * ph[x] * pa[y]
                if x > y:
                    p["h"] += v
                elif x < y:
                    p["a"] += v
                else:
                    p["d"] += v
        z = sum(p.values()) or 1.0
        return {k: max(1e-9, p[k] / z) for k in OUT}, lh, la

    def predict(
        self,
        home: str,
        away: str,
        market_odds: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """Predict 1X2 probabilities.

        market_odds: optional {"h", "d", "a"} decimal odds (pre-kickoff).
        """
        internal, lh, la = self.predict_internal(home, away)
        if market_odds and all(float(market_odds.get(k, 0)) > 1 for k in OUT):
            q = {k: 1 / float(market_odds[k]) for k in OUT}
            z = sum(q.values())
            market = {k: q[k] / z for k in OUT}
            w = self.market_weight
            final = {k: (1 - w) * internal[k] + w * market[k] for k in OUT}
            zf = sum(final.values())
            final = {k: final[k] / zf for k in OUT}
        else:
            market = None
            final = internal
            w = 0.0
        pick = max(OUT, key=lambda k: final[k])
        return {
            "home": home,
            "away": away,
            "prob_h": round(final["h"], 4),
            "prob_d": round(final["d"], 4),
            "prob_a": round(final["a"], 4),
            "pick": pick,
            "confidence": round(final[pick], 4),
            "internal": {k: round(internal[k], 4) for k in OUT},
            "market": {k: round(market[k], 4) for k in OUT} if market else None,
            "market_weight": w,
            "lh": round(lh, 3),
            "la": round(la, 3),
        }

    def update(self, home: str, away: str, gh: int, ga: int, ts: Optional[float] = None):
        """Post-match learning update (call only after final score is known)."""
        h, a = normalize_team(home), normalize_team(away)
        lh, la = self._lam(h, a)
        k = 0.06 * (1.3 if self.played[h] < 8 or self.played[a] < 8 else 1.0)
        self.att[h] = max(0.5, min(1.7, self.att[h] + k * ((gh / max(0.2, lh)) - 1)))
        self.defn[a] = max(0.5, min(1.7, self.defn[a] + k * ((gh / max(0.2, lh)) - 1)))
        self.att[a] = max(0.5, min(1.7, self.att[a] + k * ((ga / max(0.2, la)) - 1)))
        self.defn[h] = max(0.5, min(1.7, self.defn[h] + k * ((ga / max(0.2, la)) - 1)))
        self.played[h] += 1
        self.played[a] += 1
        n = sum(self.played.values()) // 2
        self.home_g = (self.home_g * n + gh) / (n + 1)
        self.away_g = (self.away_g * n + ga) / (n + 1)
        self.history.append({"h": h, "a": a, "gh": gh, "ga": ga, "ts": ts})
        self.matches_trained += 1

    def state_dict(self) -> dict:
        return {
            "league": self.league,
            "season": self.season,
            "att": dict(self.att),
            "defn": dict(self.defn),
            "home_g": self.home_g,
            "away_g": self.away_g,
            "rho": self.rho,
            "played": dict(self.played),
            "matches_trained": self.matches_trained,
            "market_weight": self.market_weight,
            "history_len": len(self.history),
            "saved_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

    def load_state(self, d: dict):
        self.league = d["league"]
        self.season = d["season"]
        self.att = defaultdict(lambda: 1.0, d["att"])
        self.defn = defaultdict(lambda: 1.0, d["defn"])
        self.home_g = d["home_g"]
        self.away_g = d["away_g"]
        self.rho = d["rho"]
        self.played = defaultdict(int, d["played"])
        self.matches_trained = d["matches_trained"]
        self.market_weight = d.get("market_weight", 0.85)

    def save(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.state_dict(), indent=2, ensure_ascii=False) + "\n")

    @classmethod
    def load(cls, path: str | Path) -> "ProductionOracle":
        d = json.loads(Path(path).read_text())
        m = cls()
        m.load_state(d)
        return m
