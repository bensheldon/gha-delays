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
START_DATE = datetime(2026, 11, 23).date()  # experiment start
# Delays are unreliable when they can exceed the interval (a late run gets
# attributed to the next slot), so short-interval workflows are excluded.
MIN_INTERVAL = 30
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
    """Fetch per workflow, per UTC day, to stay under the API's 1000-result cap per query."""
    runs = []
    today = datetime.now(timezone.utc).date()
    for name, _ in VARIANTS:
        day = START_DATE
        while day <= today:
            out = subprocess.check_output(["gh", "api", "--paginate",
                f"repos/{{owner}}/{{repo}}/actions/workflows/{name}.yml/runs?event=schedule&per_page=100&created={day}",
                "--jq", ".workflow_runs[] | {name, created_at, run_started_at, id}"], cwd=ROOT, text=True)
            runs += [json.loads(l) for l in out.splitlines() if l]
            day += timedelta(days=1)
    CACHE.parent.mkdir(exist_ok=True); CACHE.write_text(json.dumps(runs))
    return runs

def slots(schedules, start, end):
    """All intended UTC minutes in [start, end] across schedules."""
    out, t = [], start.replace(second=0, microsecond=0)
    while t <= end:
        if any(matches(s["cron"], t.astimezone(ZoneInfo(s.get("timezone", "UTC")))) for s in schedules):
            out.append(t)
        t += timedelta(minutes=1)
    return out

def interval(schedules):
    """Smallest gap in minutes between scheduled slots over one day."""
    base = datetime(2026, 1, 5, tzinfo=timezone.utc)
    ss = slots(schedules, base, base + timedelta(days=1))
    return min((b - a).total_seconds() / 60 for a, b in zip(ss, ss[1:]))

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
    rows.sort(key=lambda r: (r["workflow"], r["intended"]))
    (ROOT / "data").mkdir(exist_ok=True)
    with open(ROOT / "data" / "runs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["workflow", "intended", "created_at", "delay_min"])
        w.writeheader(); w.writerows(rows)

    # Dropped runs: expected slots from each workflow's first run until 1h before the last
    # observed run anywhere (so still-pending runs aren't counted as dropped).
    last = max(datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) for r in rows) - timedelta(hours=1)
    by_wf_rows = defaultdict(list)
    for r in rows: by_wf_rows[r["workflow"]].append(r)
    print(f"\n## Coverage (through {last:%Y-%m-%d %H:%M} UTC)")
    print(f"{'workflow':<24}{'interval':>9}{'expected':>9}{'ran':>6}{'dropped':>9}")
    for name, schedules in VARIANTS:
        rs = by_wf_rows.get(name, [])
        if not rs: print(f"{name:<24}{'':>9}{'':>9}{0:>6}{'(no runs)':>9}"); continue
        first = datetime.fromisoformat(rs[0]["intended"])
        exp = set(slots(schedules, first, last))
        got = {datetime.fromisoformat(r["intended"]) for r in rs} & exp
        print(f"{name:<24}{interval(schedules):>9.0f}{len(exp):>9}{len(got):>6}{1 - len(got)/max(len(exp),1):>9.0%}")

    by_wf, by_hour, by_min = defaultdict(list), defaultdict(list), defaultdict(list)
    for name, schedules in VARIANTS:
        if interval(schedules) < MIN_INTERVAL: continue
        for r in by_wf_rows.get(name, []):
            by_wf[name].append(r["delay_min"])
            if name.startswith("minute-"):
                t = datetime.fromisoformat(r["intended"])
                by_hour[f"{t.hour:02d}h UTC"].append(r["delay_min"])
                by_min[f":{t.minute:02d}"].append(r["delay_min"])
    table(f"Delay by workflow (interval >= {MIN_INTERVAL} min)", by_wf)
    table("Minute sweep by UTC hour", by_hour)
    table("Minute sweep by minute", by_min)

if __name__ == "__main__":
    main()
