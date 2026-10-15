# ORACLE Production Weekly System

## What is ready

1. **Production model** trained on full EPL 2024-25 (380 matches)
   - Path: `data/models/oracle_en1_2024-25.json`
   - Market blend weight: 0.85 (Phase 3 showed market dominance)

2. **Predict** upcoming fixtures
3. **Learn** after final scores (online update)
4. **Telegram** report (optional)

## Retrain exactly from your file

```bash
python tools/train_production.py \
  path/to/epl_2024_2025_football_data.json \
  --out data/models/oracle_en1_2024-25.json
```

## Weekly flow

### 1. Predict matchweek

Prepare `fixtures.json`:

```json
[
  {"home": "Arsenal", "away": "Chelsea", "odds": {"h": 1.90, "d": 3.50, "a": 4.00}},
  {"home": "Liverpool", "away": "Man City", "AvgH": 2.10, "AvgD": 3.40, "AvgA": 3.50}
]
```

```bash
python tools/weekly_pipeline.py predict fixtures.json \
  --model data/models/oracle_en1_2024-25.json \
  --league EPL --week "MW10" \
  --telegram
```

### 2. After matches finish — learn

```json
[
  {"home": "Arsenal", "away": "Chelsea", "gh": 2, "ga": 1},
  {"HomeTeam": "Liverpool", "AwayTeam": "Man City", "FTHG": 1, "FTAG": 1}
]
```

```bash
python tools/weekly_pipeline.py learn results.json \
  --model data/models/oracle_en1_2024-25.json
```

### 3. Telegram secrets

```bash
export TELEGRAM_BOT_TOKEN="123:ABC..."
export TELEGRAM_CHAT_ID="-100..."
```

## Multi-league (next step)

- Train one model state per league (`oracle_es1_...`, `oracle_de1_...`)
- Weekly job loops leagues and sends one Telegram message per league or a combined digest
- GitHub Action can schedule Saturday morning predict + Monday learn

## Important limitations (from validation)

- On 2024-25 full season, **market pure beat the hybrid**
- Model is useful as a structured probability engine + online learner, not proven edge over closing line
- Always prefer pre-kickoff odds in the blend when available
