# gha-delays

An experiment to measure how late GitHub Actions `schedule` (cron) workflows actually run, and to find a scheduling heuristic that reliably runs workflows as close as possible to their intended time.

## Background

GitHub Actions supports `on: schedule` triggers using cron syntax, but [GitHub's docs](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#schedule) warn that scheduled runs can be delayed during periods of high load, and that load is highest at the start of every hour. In practice, runs can start many minutes late, or be dropped entirely.

## Goals

- **Measure** the delay between a workflow's scheduled time and when it actually starts, across different minutes of the hour, hours of the day, and days of the week.
- **Find dropped runs**: how often scheduled runs never happen at all.
- **Recommend a heuristic** for picking cron schedules (e.g. avoiding `:00`, using odd minutes, scheduling redundant triggers) that minimizes delay and maximizes reliability.

## Status

Early exploration. Methodology, data, and findings will be added here as the experiment progresses.

## License

MIT
