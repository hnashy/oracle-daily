# OddsHarvester داخل ORACLE

## تدفق البيانات

1. شغّل OddsHarvester خارج المتصفح:

```bash
oddsharvester upcoming -s football -l england-premier-league \
  -m 1x2 --headless -f json -o data/raw/odds.json
```

2. طبّع البيانات القادمة:

```bash
python3 tools/odds_adapter.py data/raw/odds.json data/normalized/odds.json
```

3. للاختبار التاريخي الزمني، اجمع حركة الأسعار:

```bash
uv run oddsharvester historic -s football \
  -l england-premier-league --season 2024-2025 \
  --max-pages 1 -m 1x2 --odds-history --headless \
  -f json -o data/raw/epl_2024_2025_odds_history_sample.json
```

ثم شغّل:

```bash
node tools/odds_history_backtest.js \
  data/raw/epl_2024_2025_odds_history_sample.json \
  reports/odds_backtest.json
```

4. افتح ORACLE عبر خادم HTTP، وليس `file://`:

```bash
python3 -m http.server 8000
```

تقرأ الواجهة `data/normalized/odds.json` اختياريًا. إذا لم يوجد سعر مطابق، يستمر النموذج دون قسم السوق.

## الحماية من التسرب

- يجب أن يحتوي كل سجل على `kickoff_utc` و`scraped_at_utc` عند استخدام المحول القادم.
- المحول يسقط السجل إذا كان `scraped_at_utc >= kickoff_utc`.
- في الاختبار التاريخي، يختار `odds_history_backtest.js` `opening_odds` أو آخر نقطة تاريخية timestamp أصغر من kickoff لكل شركة.
- لا تُستخدم الأسعار الحالية التي جُمعت بعد المباراة.
- لا تُستخدم النتيجة إلا بعد إنشاء توقع المباراة وحساب الاحتمالات.

## الاحتمالات وEV

للسعر العشري `d`:

```text
q = 1 / d
```

ويُطبّع مجموع احتمالات 1X2 للحصول على احتمال سوقي تقريبي بعد إزالة الهامش.

للنموذج ذي الاحتمال `p`:

```text
EV = p × d - 1
```

الواجهة تعرض احتمال السوق، هامش السوق، وEV التعليمي لكل من المحلي/التعادل/الضيف. هذه ليست توصية تنفيذية ولا ضمان ربح.

## اختبار المحول

```bash
python3 -m pytest tools/test_odds_adapter.py
```
