#!/usr/bin/env python3
"""
Waste Sorting Guide  -  CampusSolve Project #41 (Environment & Sustainability)

Search a curated list of items, get the suggested waste category, log what you
dispose of, and review summaries, warnings, charts and exports.

Run:  python waste_guide.py
Needs Python 3.10+. Matplotlib is optional (charts are skipped without it).
"""
from __future__ import annotations

import csv
import difflib
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

# ----------------------------------------------------------------- paths
BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
REPORT_DIR = BASE / "reports"
ITEMS_FILE = DATA_DIR / "items.csv"
RECORDS_FILE = DATA_DIR / "records.json"
IMPORT_LOG = REPORT_DIR / "import_errors.log"

# ----------------------------------------------------------------- constants
CATEGORIES = ["Paper", "Plastic", "Glass", "Metal", "Organic",
              "E-Waste", "Hazardous", "Landfill"]
MIN_WEIGHT, MAX_WEIGHT = 0.01, 50.0      # kg per entry
MAX_QTY = 500
# Threshold rules (stretch feature: warning indicators)
HAZ_ENTRY_LIMIT_KG = 2.0                 # single hazardous entry
HAZ_WEEK_LIMIT_KG = 5.0                  # hazardous in last 7 days
EWASTE_ENTRY_LIMIT_KG = 10.0
LANDFILL_SHARE_LIMIT = 40.0              # % of total weight

CURATED_ITEMS = [  # (name, category, tip)
    ("newspaper", "Paper", "Keep dry; bundle with other paper."),
    ("cardboard box", "Paper", "Flatten boxes before binning."),
    ("office paper", "Paper", "Staples are fine; remove plastic covers."),
    ("magazine", "Paper", "Glossy paper is recyclable."),
    ("paper cup", "Landfill", "Plastic lining makes most cups non-recyclable."),
    ("pizza box", "Landfill", "Grease-soaked cardboard contaminates recycling."),
    ("tissue paper", "Landfill", "Used tissues are too short-fibred to recycle."),
    ("plastic bottle", "Plastic", "Empty, rinse and crush; keep the cap on."),
    ("milk jug", "Plastic", "Rinse; HDPE is widely recycled."),
    ("plastic bag", "Plastic", "Take to a store drop-off, not the kerbside bin."),
    ("food container", "Plastic", "Rinse off food residue first."),
    ("styrofoam", "Landfill", "Expanded polystyrene is rarely accepted."),
    ("chip packet", "Landfill", "Multi-layer foil film is not recyclable."),
    ("straw", "Landfill", "Too small to sort; use a reusable one."),
    ("glass bottle", "Glass", "Rinse; remove metal lids and recycle separately."),
    ("glass jar", "Glass", "Rinse; labels can stay on."),
    ("broken glass", "Hazardous", "Wrap in newspaper, label as sharp."),
    ("window glass", "Landfill", "Different melting point from bottle glass."),
    ("aluminium can", "Metal", "Rinse and crush."),
    ("tin can", "Metal", "Rinse; labels can stay on."),
    ("aluminium foil", "Metal", "Ball up clean foil; greasy foil goes to landfill."),
    ("bottle cap", "Metal", "Metal caps: collect in a tin and recycle."),
    ("scrap metal", "Metal", "Take to a scrap collector."),
    ("food scraps", "Organic", "Compost; avoid meat and dairy in home bins."),
    ("fruit peel", "Organic", "Great for compost."),
    ("tea bag", "Organic", "Compost if the bag is plant-based."),
    ("coffee grounds", "Organic", "Excellent compost nitrogen source."),
    ("garden waste", "Organic", "Leaves and cuttings: compost or green bin."),
    ("eggshell", "Organic", "Crush and compost."),
    ("battery", "Hazardous", "Never bin; use a battery drop-off point."),
    ("paint can", "Hazardous", "Take to a hazardous waste facility."),
    ("light bulb", "Hazardous", "CFL/LED bulbs go to special collection."),
    ("medicine", "Hazardous", "Return expired medicine to a pharmacy."),
    ("aerosol can", "Hazardous", "Only empty cans can be recycled as metal."),
    ("mobile phone", "E-Waste", "Donate, or use an e-waste take-back."),
    ("laptop", "E-Waste", "Wipe data; use a certified recycler."),
    ("charger cable", "E-Waste", "Collect with other e-waste."),
    ("headphones", "E-Waste", "Repair, or recycle as e-waste."),
    ("printer cartridge", "E-Waste", "Manufacturer take-back programs exist."),
    ("old clothes", "Landfill", "Donate if wearable; otherwise textile drop-off."),
    ("cigarette butt", "Landfill", "Fully extinguish; never litter."),
    ("diaper", "Landfill", "Wrap and bin as general waste."),
    ("ceramic mug", "Landfill", "Ceramics cannot be recycled with glass."),
    ("face mask", "Landfill", "Cut the ear loops, then bin."),
]

SAMPLE_NOTES = ["", "", "", "hostel block A", "canteen", "library", "lab clean-up",
                "fest event", "sports hall", "dept. office"]


# ----------------------------------------------------------------- ANSI
class C:
    on = sys.stdout.isatty()
    RED = "\033[91m" if on else ""
    GREEN = "\033[92m" if on else ""
    YEL = "\033[93m" if on else ""
    CYAN = "\033[96m" if on else ""
    BOLD = "\033[1m" if on else ""
    END = "\033[0m" if on else ""


def ok(msg): print(f"{C.GREEN}OK {msg}{C.END}")
def warn(msg): print(f"{C.YEL}!! {msg}{C.END}")
def err(msg): print(f"{C.RED}ERROR {msg}{C.END}")
def head(msg): print(f"\n{C.BOLD}{C.CYAN}== {msg} =={C.END}")


# ----------------------------------------------------------------- input helpers
def ask_text(prompt: str, allow_blank=False, max_len=60) -> str:
    while True:
        s = " ".join(input(prompt).split())          # trim + collapse spaces
        if not s and not allow_blank:
            err("Input cannot be blank.")
        elif len(s) > max_len:
            err(f"Max {max_len} characters.")
        else:
            return s


def ask_number(prompt: str, lo: float, hi: float, as_int=False):
    while True:
        raw = input(prompt).strip()
        try:
            val = int(raw) if as_int else float(raw)
        except ValueError:
            err("Please enter a valid " + ("whole number." if as_int else "number."))
            continue
        if val != val or not (lo <= val <= hi):      # NaN or out of range
            err(f"Value must be between {lo} and {hi}.")
            continue
        return val


def ask_date(prompt: str) -> str:
    while True:
        raw = input(prompt + " [YYYY-MM-DD, Enter = today]: ").strip()
        if not raw:
            return date.today().isoformat()
        try:
            d = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            err("Use the format YYYY-MM-DD.")
            continue
        if d > date.today():
            err("Date cannot be in the future.")
            continue
        return d.isoformat()


def ask_category(prompt="Category") -> str:
    for i, c in enumerate(CATEGORIES, 1):
        print(f"  {i}. {c}")
    n = ask_number(f"{prompt} (1-{len(CATEGORIES)}): ", 1, len(CATEGORIES), as_int=True)
    return CATEGORIES[n - 1]


# ----------------------------------------------------------------- data model
@dataclass
class Record:
    id: int
    date: str
    item: str
    category: str
    quantity: int
    weight_kg: float
    notes: str = ""

    @staticmethod
    def validate(d: dict) -> "Record":
        """Raise ValueError if dict does not satisfy the schema."""
        try:
            rec = Record(
                id=int(d["id"]), date=str(d["date"]).strip(),
                item=" ".join(str(d["item"]).split()).lower(),
                category=str(d["category"]).strip().title()
                if str(d["category"]).lower() != "e-waste" else "E-Waste",
                quantity=int(d["quantity"]), weight_kg=float(d["weight_kg"]),
                notes=str(d.get("notes", "") or "").strip(),
            )
        except (KeyError, TypeError) as e:
            raise ValueError(f"missing/invalid field: {e}")
        datetime.strptime(rec.date, "%Y-%m-%d")      # ValueError if bad
        if not rec.item:
            raise ValueError("item is blank")
        if rec.category not in CATEGORIES:
            raise ValueError(f"unknown category '{rec.category}'")
        if not 1 <= rec.quantity <= MAX_QTY:
            raise ValueError(f"quantity out of range 1-{MAX_QTY}")
        if not MIN_WEIGHT <= rec.weight_kg <= MAX_WEIGHT:
            raise ValueError(f"weight out of range {MIN_WEIGHT}-{MAX_WEIGHT}")
        return rec


# ----------------------------------------------------------------- persistence
def ensure_dirs():
    DATA_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)


def save_items(items: list[dict]):
    with open(ITEMS_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["name", "category", "tip"])
        w.writeheader()
        w.writerows(items)


def load_items() -> list[dict]:
    """Load the curated list; recreate it from defaults if missing/corrupt."""
    try:
        with open(ITEMS_FILE, newline="", encoding="utf-8") as f:
            items = [r for r in csv.DictReader(f)
                     if r.get("name") and r.get("category") in CATEGORIES]
        if items:
            return items
        raise ValueError("empty")
    except (FileNotFoundError, ValueError, csv.Error, KeyError):
        warn("Item list missing or unreadable - creating the default curated list.")
        items = [dict(name=n, category=c, tip=t) for n, c, t in CURATED_ITEMS]
        save_items(items)
        return items


def make_sample_records(n=40) -> list[Record]:
    """Realistic seed data incl. boundary values and edge cases."""
    rnd = random.Random(41)
    recs = []
    for i in range(1, n + 1):
        name, cat, _ = rnd.choice(CURATED_ITEMS)
        weight = {"Hazardous": rnd.uniform(0.05, 1.2), "E-Waste": rnd.uniform(0.1, 3),
                  "Glass": rnd.uniform(0.3, 4), "Metal": rnd.uniform(0.1, 2.5)
                  }.get(cat, rnd.uniform(0.05, 3.5))
        recs.append(Record(i, (date.today() - timedelta(days=rnd.randint(0, 59))).isoformat(),
                           name, cat, rnd.randint(1, 12), round(weight, 2),
                           rnd.choice(SAMPLE_NOTES)))
    # edge cases
    recs[0].weight_kg, recs[0].item, recs[0].category = MIN_WEIGHT, "straw", "Landfill"
    recs[1].weight_kg, recs[1].item, recs[1].category = MAX_WEIGHT, "scrap metal", "Metal"
    recs[2].weight_kg, recs[2].item, recs[2].category = 3.4, "paint can", "Hazardous"
    recs[2].date = date.today().isoformat()
    recs[3].quantity, recs[3].item, recs[3].category = MAX_QTY, "bottle cap", "Metal"
    return recs


def save_records(records: list[Record]):
    tmp = RECORDS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in records], f, indent=2)
    tmp.replace(RECORDS_FILE)                         # atomic swap


def load_records() -> list[Record]:
    try:
        with open(RECORDS_FILE, encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, list):
            raise json.JSONDecodeError("not a list", "", 0)
    except FileNotFoundError:
        ok("No records file found - created sample data (40 entries).")
        recs = make_sample_records()
        save_records(recs)
        return recs
    except json.JSONDecodeError:
        bad = RECORDS_FILE.with_suffix(f".corrupt-{datetime.now():%H%M%S}")
        RECORDS_FILE.rename(bad)
        warn(f"records.json was corrupted; backed up to {bad.name}. Starting fresh.")
        save_records([])
        return []
    recs, skipped = [], 0
    for d in raw:
        try:
            recs.append(Record.validate(d))
        except ValueError:
            skipped += 1
    if skipped:
        warn(f"Skipped {skipped} invalid record(s) while loading.")
    return recs


def next_id(records) -> int:
    return max((r.id for r in records), default=0) + 1


# ----------------------------------------------------------------- core logic
def find_items(query: str, items: list[dict], limit=5) -> list[tuple[dict, str]]:
    """Return (item, match_type) ranked: exact > contains > fuzzy."""
    q = query.lower().strip()
    exact = [i for i in items if i["name"] == q]
    contains = [i for i in items if i not in exact and (q in i["name"] or
                any(w in i["name"].split() for w in q.split()))]
    names = [i["name"] for i in items]
    fuzzy_names = difflib.get_close_matches(q, names, n=limit, cutoff=0.6)
    fuzzy = [i for i in items if i["name"] in fuzzy_names and i not in exact + contains]
    out = [(i, "exact") for i in exact] + [(i, "partial") for i in contains] \
        + [(i, "similar") for i in fuzzy]
    return out[:limit]


def anomaly_threshold(records) -> float | None:
    w = [r.weight_kg for r in records]
    if len(w) < 8:
        return None
    return statistics.mean(w) + 2 * statistics.pstdev(w)


def compute_warnings(records: list[Record]) -> list[str]:
    msgs = []
    limit = anomaly_threshold(records)
    for r in records:
        if r.category == "Hazardous" and r.weight_kg > HAZ_ENTRY_LIMIT_KG:
            msgs.append(f"[CRITICAL] #{r.id} {r.date}: hazardous '{r.item}' {r.weight_kg} kg "
                        f"exceeds {HAZ_ENTRY_LIMIT_KG} kg per-entry limit")
        elif r.category == "E-Waste" and r.weight_kg > EWASTE_ENTRY_LIMIT_KG:
            msgs.append(f"[WARNING] #{r.id}: e-waste batch {r.weight_kg} kg is unusually large")
        elif limit and r.weight_kg > limit:
            msgs.append(f"[ANOMALY] #{r.id} {r.date}: '{r.item}' {r.weight_kg} kg is far above "
                        f"typical (> {limit:.1f} kg)")
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    haz_week = sum(r.weight_kg for r in records if r.category == "Hazardous" and r.date >= week_ago)
    if haz_week > HAZ_WEEK_LIMIT_KG:
        msgs.append(f"[CRITICAL] Hazardous waste in last 7 days = {haz_week:.2f} kg "
                    f"(limit {HAZ_WEEK_LIMIT_KG} kg)")
    total = sum(r.weight_kg for r in records)
    if total:
        share = 100 * sum(r.weight_kg for r in records if r.category == "Landfill") / total
        if share > LANDFILL_SHARE_LIMIT:
            msgs.append(f"[WARNING] Landfill share is {share:.1f}% (target < {LANDFILL_SHARE_LIMIT:.0f}%)")
    return msgs


def summarize(records: list[Record]) -> dict:
    if not records:
        return {}
    total_w = sum(r.weight_kg for r in records)
    by_cat_w, by_cat_n = defaultdict(float), Counter()
    by_item = Counter()
    for r in records:
        by_cat_w[r.category] += r.weight_kg
        by_cat_n[r.category] += 1
        by_item[r.item] += r.quantity
    landfill = by_cat_w.get("Landfill", 0)
    diversion = 100 * (total_w - landfill - by_cat_w.get("Hazardous", 0)) / total_w
    today = date.today()
    cur = sum(r.weight_kg for r in records if (today - date.fromisoformat(r.date)).days < 30)
    prev = sum(r.weight_kg for r in records if 30 <= (today - date.fromisoformat(r.date)).days < 60)
    trend_pct = None if prev == 0 else 100 * (cur - prev) / prev
    status = ("GOOD" if diversion >= 70 else "FAIR" if diversion >= 50 else "POOR")
    return dict(entries=len(records), total_w=total_w, avg_w=total_w / len(records),
                max_rec=max(records, key=lambda r: r.weight_kg), by_cat_w=dict(by_cat_w),
                by_cat_n=dict(by_cat_n), top_items=by_item.most_common(3),
                diversion=diversion, status=status, cur30=cur, prev30=prev,
                trend_pct=trend_pct)


def weekly_totals(records):
    wk = defaultdict(float)
    for r in records:
        d = date.fromisoformat(r.date)
        wk[(d - timedelta(days=d.weekday())).isoformat()] += r.weight_kg
    return dict(sorted(wk.items()))


# ----------------------------------------------------------------- display
def table(rows: list[list], headers: list[str], widths: list[int]):
    line = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    fmt = lambda cells: "| " + " | ".join(
        str(c)[:w].ljust(w) for c, w in zip(cells, widths)) + " |"
    print(line); print(fmt(headers)); print(line)
    for r in rows:
        print(fmt(r))
    print(line)


def show_records(recs: list[Record], page_size=10):
    if not recs:
        warn("No records to show.")
        return
    pages = (len(recs) + page_size - 1) // page_size
    for p in range(pages):
        chunk = recs[p * page_size:(p + 1) * page_size]
        table([[r.id, r.date, r.item, r.category, r.quantity, f"{r.weight_kg:.2f}", r.notes]
               for r in chunk],
              ["ID", "Date", "Item", "Category", "Qty", "Kg", "Notes"],
              [4, 10, 18, 9, 4, 7, 16])
        print(f"Page {p + 1}/{pages}  ({len(recs)} records)")
        if p < pages - 1 and input("Enter = next page, q = stop: ").strip().lower() == "q":
            break


def bar(pct, width=24):
    return "#" * round(pct / 100 * width)


def summary_text(s: dict, warnings: list[str]) -> list[str]:
    L = ["WASTE SORTING GUIDE - EXECUTIVE SUMMARY",
         f"Generated: {datetime.now():%Y-%m-%d %H:%M}", "",
         f"Entries:            {s['entries']}",
         f"Total weight:       {s['total_w']:.2f} kg",
         f"Average per entry:  {s['avg_w']:.2f} kg",
         f"Heaviest entry:     #{s['max_rec'].id} {s['max_rec'].item} ({s['max_rec'].weight_kg} kg)",
         f"Diversion rate:     {s['diversion']:.1f}%  -> status {s['status']}",
         f"Last 30 days:       {s['cur30']:.2f} kg  (previous 30: {s['prev30']:.2f} kg)"]
    if s["trend_pct"] is not None:
        L.append(f"Trend:              {s['trend_pct']:+.1f}% vs previous 30 days")
    L += ["", "By category:"]
    for c, w in sorted(s["by_cat_w"].items(), key=lambda x: -x[1]):
        pct = 100 * w / s["total_w"]
        L.append(f"  {c:<10}{w:>8.2f} kg {pct:>5.1f}%  {s['by_cat_n'][c]:>3} entries  {bar(pct)}")
    L += ["", "Top items by quantity: " + ", ".join(f"{n} ({q})" for n, q in s["top_items"]), ""]
    L += ["Warnings:"] + (["  " + w for w in warnings] if warnings else ["  none"])
    return L


# ----------------------------------------------------------------- menu actions
def act_search_item(items):
    head("Search the item guide")
    q = ask_text("What are you throwing away? ")
    res = find_items(q, items)
    if not res:
        warn(f"'{q}' is not in the guide.")
        if input("Add it to the curated list? (y/n): ").strip().lower() == "y":
            act_add_item(items, preset=q)
        return None
    for it, kind in res:
        print(f"  [{kind:<7}] {C.BOLD}{it['name']}{C.END} -> {C.GREEN}{it['category']}{C.END}"
              f"\n             tip: {it['tip']}")
    return res[0][0]


def act_add_item(items, preset=""):
    name = preset.lower() or ask_text("New item name: ").lower()
    if any(i["name"] == name for i in items):
        err("That item already exists.")
        return
    cat = ask_category()
    tip = ask_text("Disposal tip (optional): ", allow_blank=True, max_len=100)
    items.append(dict(name=name, category=cat, tip=tip or "-"))
    save_items(items)
    ok(f"Added '{name}' as {cat}.")


def act_log(records, items):
    head("Log a disposal entry")
    name = ask_text("Item: ").lower()
    match = find_items(name, items, 1)
    if match and match[0][1] != "similar":
        cat = match[0][0]["category"]
        ok(f"Suggested category: {cat}")
        if input("Accept? (Enter = yes, n = choose manually): ").strip().lower() == "n":
            cat = ask_category()
    else:
        if match:
            warn(f"Did you mean '{match[0][0]['name']}'?")
        warn("Not in the guide - please choose a category.")
        cat = ask_category()
    qty = ask_number(f"Quantity (1-{MAX_QTY}): ", 1, MAX_QTY, as_int=True)
    wt = ask_number(f"Total weight in kg ({MIN_WEIGHT}-{MAX_WEIGHT}): ", MIN_WEIGHT, MAX_WEIGHT)
    d = ask_date("Date")
    note = ask_text("Notes (optional): ", allow_blank=True, max_len=40)
    rec = Record.validate(dict(id=next_id(records), date=d, item=name, category=cat,
                               quantity=qty, weight_kg=round(wt, 2), notes=note))
    records.append(rec)
    save_records(records)
    ok(f"Saved entry #{rec.id}.")
    for w in compute_warnings([rec] if rec.category in ("Hazardous", "E-Waste") else []):
        warn(w)


def act_query(records):
    head("Search records")
    print("  1. Keyword (item or notes)\n  2. Category\n  3. Date range\n  4. Show all")
    n = ask_number("Choose 1-4: ", 1, 4, as_int=True)
    if n == 1:
        k = ask_text("Keyword: ").lower()
        hits = [r for r in records if k in r.item or k in r.notes.lower()]
    elif n == 2:
        c = ask_category()
        hits = [r for r in records if r.category == c]
    elif n == 3:
        a, b = ask_date("From"), ask_date("To")
        if a > b:
            a, b = b, a
        hits = [r for r in records if a <= r.date <= b]
    else:
        hits = records
    show_records(sorted(hits, key=lambda r: r.date, reverse=True))


def act_summary(records):
    head("Executive summary")
    s = summarize(records)
    if not s:
        warn("No records yet.")
        return
    for line in summary_text(s, compute_warnings(records)):
        if "[CRITICAL]" in line:
            print(C.RED + line + C.END)
        elif "[WARNING]" in line or "[ANOMALY]" in line:
            print(C.YEL + line + C.END)
        else:
            print(line)


def act_warnings(records):
    head("Threshold warnings")
    w = compute_warnings(records)
    if not w:
        ok("All clear - no thresholds breached.")
    for m in w:
        (err if "CRITICAL" in m else warn)(m)


def write_svg_chart(records) -> Path:
    """Dependency-free bar chart (standard library only)."""
    s = summarize(records)
    cats = sorted(s["by_cat_w"], key=lambda c: -s["by_cat_w"][c])
    top = max(s["by_cat_w"].values())
    rows = []
    for i, c in enumerate(cats):
        w = s["by_cat_w"][c]
        y, bw = 50 + i * 34, max(2, 420 * w / top)
        rows.append(f'<text x="10" y="{y + 18}" font-size="14">{c}</text>'
                    f'<rect x="100" y="{y}" width="{bw:.0f}" height="24" fill="#2e7d32"/>'
                    f'<text x="{110 + bw:.0f}" y="{y + 18}" font-size="13">{w:.1f} kg</text>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="640" '
           f'height="{60 + len(cats) * 34}" font-family="sans-serif">'
           '<rect width="100%" height="100%" fill="white"/>'
           '<text x="10" y="28" font-size="18" font-weight="bold">'
           'Waste weight by category (kg)</text>' + "".join(rows) + '</svg>')
    path = REPORT_DIR / "charts.svg"
    path.write_text(svg, encoding="utf-8")
    return path

def act_charts(records):
    head("Charts")
    if not records:
        warn("No records yet.")
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as e:
        warn(f"Matplotlib could not be loaded: {e}")
        warn("Using the built-in fallback charts instead.")
        s = summarize(records)
        for c, w in sorted(s["by_cat_w"].items(), key=lambda x: -x[1]):
            print(f"  {c:<10}{bar(100 * w / s['total_w'], 40)} {w:.1f} kg")
        ok(f"SVG chart saved to {write_svg_chart(records)}")
        return
    
    s = summarize(records)
    cats = sorted(s["by_cat_w"], key=lambda c: -s["by_cat_w"][c])
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    ax[0].bar(cats, [s["by_cat_w"][c] for c in cats], color="#2e7d32")
    ax[0].set_title("Waste weight by category"); ax[0].set_ylabel("kg")
    ax[0].tick_params(axis="x", rotation=40)
    wk = weekly_totals(records)
    ax[1].plot(list(wk), list(wk.values()), marker="o", color="#1565c0")
    ax[1].set_title("Weekly waste trend"); ax[1].set_ylabel("kg")
    ax[1].tick_params(axis="x", rotation=40)
    fig.tight_layout()
    path = REPORT_DIR / "charts.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    ok(f"Chart saved to {path}")


def act_export(records):
    head("Export report")
    s = summarize(records)
    if not s:
        warn("Nothing to export.")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    lines = summary_text(s, compute_warnings(records))
    txt = REPORT_DIR / f"audit_{stamp}.txt"
    txt.write_text("\n".join(lines), encoding="utf-8")
    md = REPORT_DIR / f"summary_{stamp}.md"
    rows = "\n".join(f"| {c} | {w:.2f} | {100 * w / s['total_w']:.1f}% | {s['by_cat_n'][c]} |"
                     for c, w in sorted(s["by_cat_w"].items(), key=lambda x: -x[1]))
    md.write_text(
        f"# Waste Sorting Guide - Summary\n\n*Generated {datetime.now():%Y-%m-%d %H:%M}*\n\n"
        f"- **Entries:** {s['entries']}\n- **Total weight:** {s['total_w']:.2f} kg\n"
        f"- **Average per entry:** {s['avg_w']:.2f} kg\n"
        f"- **Diversion rate:** {s['diversion']:.1f}% ({s['status']})\n\n"
        f"## By category\n\n| Category | Kg | Share | Entries |\n|---|---|---|---|\n{rows}\n\n"
        "## Warnings\n\n" + ("\n".join(f"- {w}" for w in compute_warnings(records)) or "None") + "\n",
        encoding="utf-8")
    csv_path = REPORT_DIR / f"records_{stamp}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(records[0])))
        w.writeheader()
        w.writerows(asdict(r) for r in records)
    ok(f"Wrote {txt.name}, {md.name}, {csv_path.name} to {REPORT_DIR}")


def act_import(records, items):
    head("Bulk import CSV")
    p = Path(ask_text("Path to CSV (columns: date,item,category,quantity,weight_kg,notes): "))
    try:
        f = open(p, newline="", encoding="utf-8-sig")
    except OSError as e:
        err(f"Cannot open file: {e.strerror}")
        return
    good, errors = 0, []
    with f:
        reader = csv.DictReader(f)
        need = {"date", "item", "weight_kg", "quantity"}
        if not reader.fieldnames or not need <= set(reader.fieldnames):
            err(f"CSV must contain columns: {', '.join(sorted(need))}")
            return
        for n, row in enumerate(reader, start=2):
            try:
                cat = (row.get("category") or "").strip()
                if not cat:                           # infer from curated list
                    m = find_items((row.get("item") or "").lower(), items, 1)
                    if not m:
                        raise ValueError("category blank and item not in guide")
                    cat = m[0][0]["category"]
                records.append(Record.validate({**row, "id": next_id(records), "category": cat}))
                good += 1
            except (ValueError, TypeError) as e:
                errors.append(f"line {n}: {e}  | {dict(row)}")
    save_records(records)
    ok(f"Imported {good} row(s); {len(errors)} rejected.")
    if errors:
        IMPORT_LOG.write_text("\n".join(errors), encoding="utf-8")
        warn(f"Row-by-row errors written to {IMPORT_LOG}")
        for e in errors[:5]:
            print("   ", e[:100])


def act_edit_delete(records):
    head("Delete a record")
    show_records(sorted(records, key=lambda r: r.id)[-5:])
    rid = ask_number("ID to delete (0 = cancel): ", 0, 10**9, as_int=True)
    if rid == 0:
        return
    target = next((r for r in records if r.id == rid), None)
    if not target:
        err("No such ID.")
    elif input(f"Delete #{rid} '{target.item}'? (y/n): ").strip().lower() == "y":
        records.remove(target)
        save_records(records)
        ok("Deleted.")


# ----------------------------------------------------------------- main loop
BANNER = r"""
  __        __          _          ____             _
  \ \      / /_ _ ___ | |_ ___   / ___|  ___  _ __| |_
   \ \ /\ / / _` / __|| __/ _ \  \___ \ / _ \| '__| __|
    \ V  V / (_| \__ \| ||  __/   ___) | (_) | |  | |_
     \_/\_/ \__,_|___/ \__\___|  |____/ \___/|_|   \__|   GUIDE
        CampusSolve #41  |  Sort smart. Waste less.
"""
MENU = """
 1. Search item -> suggested category     6. Threshold warnings
 2. Log a disposal entry                 7. Generate charts (Matplotlib)
 3. Search / browse records              8. Export reports (MD / TXT / CSV)
 4. Executive summary                    9. Bulk import CSV
 5. Add item to curated guide            10. Delete a record
 0. Exit"""


def main():
    ensure_dirs()
    print(C.GREEN + BANNER + C.END)
    items, records = load_items(), load_records()
    alerts = [w for w in compute_warnings(records) if "CRITICAL" in w]
    if alerts:
        warn(f"{len(alerts)} critical alert(s) - choose option 6 to review.")
    actions = {1: lambda: act_search_item(items), 2: lambda: act_log(records, items),
               3: lambda: act_query(records), 4: lambda: act_summary(records),
               5: lambda: act_add_item(items), 6: lambda: act_warnings(records),
               7: lambda: act_charts(records), 8: lambda: act_export(records),
               9: lambda: act_import(records, items), 10: lambda: act_edit_delete(records)}
    while True:
        print(MENU)
        try:
            choice = ask_number("\nSelect an option: ", 0, 10, as_int=True)
            if choice == 0:
                save_records(records)
                print("Goodbye - your data is saved. Keep sorting!")
                return
            actions[choice]()
        except (KeyboardInterrupt, EOFError):
            print("\nInterrupted - saving and exiting.")
            save_records(records)
            return
        except Exception as e:                        # last-resort guard: never crash the demo
            err(f"Unexpected problem: {e}")


if __name__ == "__main__":
    main()
