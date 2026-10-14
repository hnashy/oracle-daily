import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "tools" / "odds_adapter.py"


def test_adapter_keeps_only_pre_kickoff_quotes(tmp_path):
    raw = tmp_path / "raw.json"
    out = tmp_path / "odds.json"
    raw.write_text(json.dumps([
        {"home_team":"Arsenal","away_team":"Chelsea","kickoff_utc":"2026-10-20T18:00:00Z","scraped_at_utc":"2026-10-20T12:00:00Z","odds":{"1":1.8,"X":3.7,"2":4.5}},
        {"home_team":"A","away_team":"B","kickoff_utc":"2026-10-20T18:00:00Z","scraped_at_utc":"2026-10-20T19:00:00Z","odds":{"1":2,"X":3,"2":4}},
    ]), encoding="utf-8")
    subprocess.run([sys.executable, str(ADAPTER), str(raw), str(out)], check=True)
    data = json.loads(out.read_text())
    assert len(data["matches"]) == 1
    assert data["matches"][0]["odds"] == {"h": 1.8, "d": 3.7, "a": 4.5}
