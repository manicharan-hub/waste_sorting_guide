# Waste Sorting Guide  (CampusSolve #41)

Menu-driven Python app: search a curated list of items, get the suggested waste
category, log disposals, and review summaries, warnings, charts and exports.

## Run
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt                      # only needed for charts
python waste_guide.py
```
First launch auto-creates `data/items.csv` (44 curated items) and `data/records.json`
(40 seeded entries incl. boundary/edge cases). Delete `data/records.json` to reset.

## Features
| Requirement | Where |
|---|---|
| Terminal menu | `main()` |
| Input validation | `ask_text / ask_number / ask_date`, `Record.validate` |
| Core logic (item -> category) | `find_items` (exact, partial, fuzzy via difflib) |
| Persistence (CSV + JSON) | `items.csv`, `records.json`; atomic saves, corrupt-file recovery |
| Query & search | keyword, category, date range, pagination |
| Executive summary | totals, averages, diversion rate, status, 30-day trend |
| Charts | Matplotlib -> `reports/charts.png` (text fallback if not installed) |
| Export (stretch) | Markdown, TXT audit log, CSV in `reports/` |
| Warnings (stretch) | hazardous limits, anomaly detection (mean + 2 sd), landfill share |
| Bulk import (stretch) | option 9; try `data/import_sample.csv`; errors in `reports/import_errors.log` |

## Demo script (5 min)
1. Launch -> banner + critical alert.  2. Option 1: search `plastic botle` (typo still matches).
3. Option 2: enter `abc` for quantity and `99` for weight; watch validation re-prompt, then save.
4. Option 4 summary, option 6 warnings, option 7 chart.  5. Option 9 import `data/import_sample.csv`
(2 accepted, 4 rejected with reasons).  6. Option 0, relaunch, option 3 -> data persisted.  7. Option 8 export.

## Tunable thresholds
Constants at the top of `waste_guide.py` (`HAZ_ENTRY_LIMIT_KG`, `LANDFILL_SHARE_LIMIT`, ...).
