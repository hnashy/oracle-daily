#!/usr/bin/env python3
"""ORACLE Weekly Pipeline — Arabic Telegram report format."""
from __future__ import annotations

import argparse
import json
import math
import os
import urllib.request
from datetime import datetime, timezone
from math import exp, factorial
from pathlib import Path

from production_oracle import ProductionOracle, OUT

LEAGUE_AR = {
    "en.1": "الدوري الإنجليزي (EPL)",
    "es.1": "الدوري الإسباني (La Liga)",
    "it.1": "الدوري الإيطالي (Serie A)",
    "de.1": "الدوري الألماني (Bundesliga)",
    "fr.1": "الدوري الفرنسي (Ligue 1)",
    "EPL": "الدوري الإنجليزي (EPL)",
}


def poisson(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return exp(-lam) * lam ** k / factorial(k)


def over25_btts(lh: float, la: float) -> tuple[float, float]:
    """Approx P(goals > 2.5) and P(BTTS) from independent Poisson."""
    o25 = 0.0
    btts = 0.0
    for x in range(0, 10):
        for y in range(0, 10):
            p = poisson(x, lh) * poisson(y, la)
            if x + y >= 3:
                o25 += p
            if x >= 1 and y >= 1:
                btts += p
    return o25, btts


def conf_ar(c: float) -> str:
    if c >= 0.55:
        return "ثقة عالية"
    if c >= 0.48:
        return "ثقة متوسطة"
    return "ثقة منخفضة"


def pick_ar(pick: str) -> str:
    return {"h": "فوز محلي", "d": "تعادل", "a": "فوز ضيف"}.get(pick, pick)


def send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram not configured")
        return False
    # Telegram limit ~4096 chars — split if needed
    chunks = []
    while text:
        chunks.append(text[:4000])
        text = text[4000:]
    ok = True
    for chunk in chunks:
        body = json.dumps({"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status != 200:
                    ok = False
        except Exception as e:
            print(f"Telegram error: {e}")
            ok = False
    return ok


def format_report(preds: list, league: str, week_label: str) -> str:
    league_name = LEAGUE_AR.get(league, league)
    n = len(preds)
    # Keep chronological order if kickoff present, else confidence
    def sort_key(p):
        d = p.get("kickoff") or ""
        t = p.get("time") or ""
        return (d, t)

    ordered = sorted(preds, key=sort_key)

    lines = [
        "🔮 ORACLE — تحليل الجولة",
        f"🏆 {league_name}",
        f"📅 {week_label} · 0/{n}",
        "━━━━━━━━━━━━━━",
        "",
    ]

    for i, p in enumerate(ordered, 1):
        lh = float(p.get("lh") or 1.3)
        la = float(p.get("la") or 1.1)
        o25, btts = over25_btts(lh, la)
        time_s = p.get("time") or "—"
        date_s = p.get("kickoff") or "—"
        conf = float(p.get("confidence") or 0)
        lines.append(f"{i}. {p['home']} vs {p['away']}")
        lines.append(f"   🕐 {time_s} · {date_s}")
        lines.append(
            f"   📊 محلي {p['prob_h']*100:.0f}% | تعادل {p['prob_d']*100:.0f}% | ضيف {p['prob_a']*100:.0f}%"
        )
        lines.append(f"   ⭐ المفضّل: {pick_ar(p['pick'])} ({conf_ar(conf)})")
        lines.append(f"   ⚽ أكثر 2.5: {o25*100:.0f}% | BTTS: {btts*100:.0f}%")
        lines.append(f"   xG {lh:.2f} – {la:.2f} 🔒")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━")
    lines.append("نموذج ENS-1.2 • وضع الجولة • للبحث فقط")
    return "\n".join(lines)


def cmd_predict(args):
    model = ProductionOracle.load(args.model)
    fixtures = json.loads(Path(args.fixtures).read_text(encoding="utf-8"))
    preds = []
    for f in fixtures:
        home = f.get("home") or f.get("HomeTeam") or f.get("team1")
        away = f.get("away") or f.get("AwayTeam") or f.get("team2")
        odds = f.get("odds") or f.get("market_odds")
        if odds is None and f.get("AvgH"):
            try:
                odds = {"h": float(f["AvgH"]), "d": float(f["AvgD"]), "a": float(f["AvgA"])}
            except Exception:
                odds = None
        if not home or not away:
            continue
        p = model.predict(home, away, market_odds=odds)
        p["kickoff"] = f.get("date") or f.get("Date") or f.get("kickoff")
        p["time"] = f.get("time") or f.get("Time") or ""
        p["round"] = f.get("round") or ""
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
    print(json.dumps({"n": len(preds), "saved": str(out_path)}, indent=2, ensure_ascii=False))

    week = args.week or (preds[0].get("round") if preds else "Matchweek")
    report = format_report(preds, args.league, week)
    print("\n" + report)
    if args.telegram:
        ok = send_telegram(report)
        print(f"Telegram sent: {ok}")


def cmd_learn(args):
    model = ProductionOracle.load(args.model)
    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
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
    }, indent=2, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="ORACLE weekly pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("predict", help="Predict upcoming fixtures")
    p.add_argument("fixtures", help="JSON list of fixtures")
    p.add_argument("--model", default="data/models/oracle_en1_2024-25.json")
    p.add_argument("--out", default="")
    p.add_argument("--league", default="en.1")
    p.add_argument("--week", default="")
    p.add_argument("--telegram", action="store_true")

    l = sub.add_parser("learn", help="Update model after results")
    l.add_argument("results", help="JSON list with home/away/gh/ga")
    l.add_argument("--model", default="data/models/oracle_en1_2024-25.json")

    args = ap.parse_args()
    if args.cmd == "predict":
        cmd_predict(args)
    elif args.cmd == "learn":
        cmd_learn(args)


if __name__ == "__main__":
    main()
