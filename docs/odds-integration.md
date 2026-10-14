# OddsHarvester داخل ORACLE

## تدفق البيانات

1. شغّل OddsHarvester خارج المتصفح:

```bash
oddsharvester upcoming -s football -l england-premier-league \
  -m 1x2 --headless -f json -o data/raw/odds.json
```

2. طبّع البيانات:

```bash
python3 tools/odds_adapter.py data/raw/odds.json data/normalized/odds.json
```

3. افتح ORACLE عبر خادم HTTP، وليس `file://`:

```bash
python3 -m http.server 8000
```

تقرأ الواجهة `data/normalized/odds.json` اختياريًا. إذا لم يوجد سعر مطابق، يستمر النموذج دون قسم السوق.

## الحماية من التسرب

- يجب أن يحتوي كل سجل على `kickoff_utc` و`scraped_at_utc`.
- المحول يسقط السجل إذا كان `scraped_at_utc >= kickoff_utc`.
- لا تُستخدم أسعار ما بعد البداية في الاختبار التاريخي.
- الأسعار الحالية لا تُخلط مع سجل النتائج التاريخية.

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
