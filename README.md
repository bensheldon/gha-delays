# gha-delays

An experiment to measure how late GitHub Actions `schedule` (cron) workflows actually run, and to find a scheduling heuristic that reliably runs workflows as close as possible to their intended time.

## Background

GitHub Actions supports `on: schedule` triggers using cron syntax, but [GitHub's docs](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#schedule) warn that scheduled runs can be delayed during periods of high load, and that load is highest at the start of every hour. In practice, runs can start many minutes late, or be dropped entirely.

## Goals

- **Measure** the delay between a workflow's scheduled time and when it actually starts, across different minutes of the hour, hours of the day, and days of the week.
- **Find dropped runs**: how often scheduled runs never happen at all.
- **Recommend a heuristic** for picking cron schedules (e.g. avoiding `:00`, using odd minutes, scheduling redundant triggers) that minimizes delay and maximizes reliability.

## Methodology

`script/generate.py` generates ~80 no-op workflows in `.github/workflows/`. Each one only echoes its schedule. They're grouped into two sets:

- **Minute sweep** (`minute-00` … `minute-59`): `M * * * *` for every minute. Together they cover every hour/minute combination in UTC.
  → *Do particular hour/minute combinations have more or less delay?*
- **Format variants** (`fmt-*`): equivalent or overlapping schedules written different ways: steps (`*/5`, `0-59/5`, `7/15`), lists, multiple `cron:` entries, explicit hour/day/month ranges, named days and months, and `timezone:` (including half-hour and 45-minute offsets). Most target minute `:17`, so they can be compared directly against `minute-17`.
  → *Do particular schedule formats have more or less delay?*

The repo is public, so Actions minutes are free.

## Analysis

```sh
python3 script/analyze.py --refresh
```

This fetches all `schedule` runs through `gh api`. For each run, it computes the intended time as the latest cron match at or before the run's `created_at`. It writes `data/runs.csv` and prints p50/p90/max delay by workflow, by UTC hour and by minute.

Caveats:
- If a run's delay is longer than its schedule's interval (e.g. 7 minutes on `*/5`), the run is attributed to the wrong slot.
- Dropped runs show up as gaps in the expected run counts.
- GitHub disables scheduled workflows in public repos after 60 days without repository activity. Push a commit to keep them running.

## Status

Collecting data.

## License

MIT
