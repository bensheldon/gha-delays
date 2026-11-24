#!/usr/bin/env python3
"""Fetch scheduled runs and report delay (run created_at - intended cron time).

Usage: python3 script/analyze.py [--refresh]   (requires `gh` auth)
Writes data/runs.csv; prints summaries by workflow and by UTC hour/minute.
"""
import csv, json, pathlib, statistics, subprocess, sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from generate import VARIANTS

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "raw_runs.json"
NAMES = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,"JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12,
         "SUN":0,"MON":1,"TUE":2,"WED":3,"THU":4,"FRI":5,"SAT":6}

def field(expr, lo, hi):
    vals = set()
    for part in expr.upper().split(","):
        part, step = (part.split("/") + ["1"])[:2]
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            a, b = (int(NAMES.get(x, x)) for x in part.split("-"))
        else:
            a = int(NAMES.get(part, part)); b = hi if step != "1" else a
        vals.update(range(a, b + 1, int(step)))
    return vals

def matches(cron, t):
    mi, h, dom, mon, dow = cron.split()
    return (t.minute in field(mi, 0, 59) and t.hour in field(h, 0, 23)
            and t.day in field(dom, 1, 31) and t.month in field(mon, 1, 12)
            and (t.isoweekday() % 7) in field(dow, 0, 6))

def intended(schedules, created):
    """Latest scheduled instant <= created across all schedules."""
    best = None
    for s in schedules:
        tz = ZoneInfo(s.get("timezone", "UTC"))
        t = created.astimezone(tz).replace(second=0, microsecond=0)
        for _ in range(60 * 24 * 2):
            if matches(s["cron"], t):
                break
            t = (t.astimezone(timezone.utc) - timedelta(minutes=1)).astimezone(tz)
        else:
            continue
        best = max(best or t, t)
    return best.astimezone(timezone.utc) if best else None

def fetch():
    out = subprocess.check_output(["gh", "api", "--paginate",
        "repos/{owner}/{repo}/actions/runs?event=schedule&per_page=100",
        "--jq", ".workflow_runs[] | {name, created_at, run_started_at, id}"], cwd=ROOT, text=True)
    runs = [json.loads(l) for l in out.splitlines() if l]
    CACHE.parent.mkdir(exist_ok=True); CACHE.write_text(json.dumps(runs))
    return runs

def pct(xs, p):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(p * len(xs)))]

def table(title, groups):
    print(f"\n## {title}\n{'key':<24}{'n':>6}{'p50':>8}{'p90':>8}{'max':>8}  (minutes)")
    for k, xs in sorted(groups.items()):
        print(f"{k:<24}{len(xs):>6}{statistics.median(xs):>8.1f}{pct(xs,.9):>8.1f}{max(xs):>8.1f}")

def main():
    runs = fetch() if "--refresh" in sys.argv or not CACHE.exists() else json.loads(CACHE.read_text())
    sched = dict(VARIANTS)
    rows = []
    for r in runs:
        if r["name"] not in sched: continue
        created = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
        it = intended(sched[r["name"]], created)
        if not it: continue
        rows.append({"workflow": r["name"], "intended": it.isoformat(), "created_at": r["created_at"],
                     "delay_min": round((created - it).total_seconds() / 60, 2)})
    with open(ROOT / "data" / "runs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["workflow", "intended", "created_at", "delay_min"])
        w.writeheader(); w.writerows(rows)

    by_wf, by_hour, by_min = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in rows:
        by_wf[r["workflow"]].append(r["delay_min"])
        if r["workflow"].startswith("minute-"):
            t = datetime.fromisoformat(r["intended"])
            by_hour[f"{t.hour:02d}h UTC"].append(r["delay_min"])
            by_min[f":{t.minute:02d}"].append(r["delay_min"])
    table("By workflow", by_wf)
    table("Minute sweep by UTC hour", by_hour)
    table("Minute sweep by minute", by_min)

if __name__ == "__main__":
    main()
