#!/usr/bin/env python3
"""ORACLE Weekly Pipeline

1. Load production model
2. Import upcoming matchweek fixtures (+ optional odds)
3. Predict each match
4. Rank by confidence / value
5. Send report to Telegram (if token configured)
6. After results: update model (learn) and save

Usage:
  # Predict upcoming (fixtures JSON list with home/away/optional odds)
  python tools/weekly_pipeline.py predict fixtures.json --model data/models/oracle_en1_2024-25.json

  # Post-match learn
  python tools/weekly_pipeline.py learn results.json --model data/models/oracle_en1_2024-25.json

  # Telegram requires env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from production_oracle import ProductionOracle, OUT


def send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram not configured (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False


def format_report(preds: list, league: str, week_label: str) -> str:
    lines = [
        f"<b>ORACLE Weekly — {league}</b>",
        f"{week_label}",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
        "",
    ]
    # Sort by confidence descending
    ranked = sorted(preds, key=lambda p: -p["confidence"])
    for i, p in enumerate(ranked, 1):
        pick_label = {"h": "Home", "d": "Draw", "a": "Away"}[p["pick"]]
        lines.append(
            f"{i}. <b>{p['home']}</b> vs <b>{p['away']}</b>\n"
            f"   Pick: {pick_label} ({p['confidence']:.0%})\n"
            f"   H {p['prob_h']:.0%} | D {p['prob_d']:.0%} | A {p['prob_a']:.0%}"
        )
    lines.append("")
    lines.append(f"Model matches trained: see state file")
    lines.append("<i>Not financial advice. Probabilities only.</i>")
    return "\n".join(lines)


def cmd_predict(args):
    model = ProductionOracle.load(args.model)
    fixtures = json.loads(Path(args.fixtures).read_text())
    preds = []
    for f in fixtures:
        home = f.get("home") or f.get("HomeTeam") or f.get("team1")
        away = f.get("away") or f.get("AwayTeam") or f.get("team2")
        odds = f.get("odds") or f.get("market_odds")
        if odds is None and f.get("AvgH"):
            odds = {"h": float(f["AvgH"]), "d": float(f["AvgD"]), "a": float(f["AvgA"])}
        if not home or not away:
            continue
        p = model.predict(home, away, market_odds=odds)
        p["kickoff"] = f.get("date") or f.get("Date") or f.get("kickoff")
        preds.append(p)

    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "model_matches_trained": model.matches_trained,
        "n_fixtures": len(preds),
        "predictions": preds,
    }
    out_path = Path(args.out) if args.out else Path("reports/weekly_predictions.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"n": len(preds), "saved": str(out_path)}, indent=2))

    report = format_report(preds, args.league, args.week or "Matchweek")
    print("\n" + report.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", ""))
    if args.telegram:
        ok = send_telegram(report)
        print(f"Telegram sent: {ok}")


def cmd_learn(args):
    model = ProductionOracle.load(args.model)
    results = json.loads(Path(args.results).read_text())
    updated = 0
    for r in results:
        home = r.get("home") or r.get("HomeTeam")
        away = r.get("away") or r.get("AwayTeam")
        gh = r.get("gh") if r.get("gh") is not None else r.get("FTHG")
        ga = r.get("ga") if r.get("ga") is not None else r.get("FTAG")
        if home is None or away is None or gh is None or ga is None:
            continue
        model.update(home, away, int(gh), int(ga))
        updated += 1
    model.save(args.model)
    print(json.dumps({
        "updated": updated,
        "matches_trained_now": model.matches_trained,
        "saved": str(args.model),
    }, indent=2))


def main():
    ap = argparse.ArgumentParser(description="ORACLE weekly pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("predict", help="Predict upcoming fixtures")
    p.add_argument("fixtures", help="JSON list of fixtures")
    p.add_argument("--model", default="data/models/oracle_en1_2024-25.json")
    p.add_argument("--out", default="")
    p.add_argument("--league", default="EPL")
    p.add_argument("--week", default="")
    p.add_argument("--telegram", action="store_true")

    l = sub.add_parser("learn", help="Update model after results")
    l.add_argument("results", help="JSON list with home/away/gh/ga or FTHG/FTAG")
    l.add_argument("--model", default="data/models/oracle_en1_2024-25.json")

    args = ap.parse_args()
    if args.cmd == "predict":
        cmd_predict(args)
    elif args.cmd == "learn":
        cmd_learn(args)


if __name__ == "__main__":
    main()
