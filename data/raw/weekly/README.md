# Weekly input files

Place files here before the Action runs:

| File | When | Purpose |
|------|------|--------|
| `fixtures_en.1.json` | Before Saturday predict | Upcoming matches + optional odds |
| `results_en.1.json` | Before Monday learn | Final scores for post-match update |

## fixtures_en.1.json example

```json
[
  {
    "home": "Arsenal",
    "away": "Chelsea",
    "odds": { "h": 1.85, "d": 3.60, "a": 4.20 }
  },
  {
    "home": "Liverpool",
    "away": "Man City",
    "AvgH": 2.10,
    "AvgD": 3.40,
    "AvgA": 3.50
  }
]
```

## results_en.1.json example

```json
[
  { "home": "Arsenal", "away": "Chelsea", "gh": 2, "ga": 1 },
  { "HomeTeam": "Liverpool", "AwayTeam": "Man City", "FTHG": 1, "FTAG": 1 }
]
```

Multi-league later: `fixtures_es.1.json`, `results_es.1.json`, etc.
