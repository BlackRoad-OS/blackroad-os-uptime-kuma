# BlackRoad OS — Uptime Kuma

> **Production-ready uptime monitoring** for BlackRoad OS. Real-time HTTP/TCP/Ping/DNS/Push monitoring with incident management, status pages, Stripe-powered billing, and a fully tested E2E pipeline.

[![CI](https://github.com/BlackRoad-OS/blackroad-os-uptime-kuma/actions/workflows/ci.yml/badge.svg)](https://github.com/BlackRoad-OS/blackroad-os-uptime-kuma/actions/workflows/ci.yml)
[![npm version](https://img.shields.io/npm/v/@blackroad-os/uptime-kuma)](https://www.npmjs.com/package/@blackroad-os/uptime-kuma)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)

---

## Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Architecture](#architecture)
4. [Installation](#installation)
   - [Python (pip)](#python-pip)
   - [npm / Node.js wrapper](#npm--nodejs-wrapper)
5. [Quick Start](#quick-start)
6. [CLI Reference](#cli-reference)
7. [Configuration](#configuration)
8. [Database Schema](#database-schema)
9. [Stripe Integration](#stripe-integration)
10. [Status Pages](#status-pages)
11. [API Reference](#api-reference)
12. [Testing (E2E & Unit)](#testing-e2e--unit)
13. [CI / CD](#ci--cd)
14. [Security](#security)
15. [Contributing](#contributing)
16. [License](#license)

---

## Overview

**BlackRoad OS Uptime Kuma** is the monitoring backbone of the BlackRoad OS platform. It gives teams instant visibility into service availability across all BlackRoad-powered products — from `worlds.blackroad.io` to custom customer deployments.

Key goals:
- **Zero blind spots** — monitor every endpoint, port, and certificate.
- **Instant incident response** — automated incident creation and resolution.
- **Public transparency** — per-product status pages with real-time data.
- **Monetization-ready** — Stripe integration for subscription-gated monitoring tiers.

---

## Features

| Feature | Description |
|---|---|
| **Multi-protocol checks** | HTTP(S), TCP, ICMP Ping, DNS, Push |
| **Incident tracking** | Auto-create / auto-resolve downtime incidents |
| **Status pages** | Public status pages with slug-based routing and custom themes |
| **Response time tracking** | Per-heartbeat latency recorded and averaged |
| **SSL certificate monitoring** | Days-to-expiry tracked for every HTTPS endpoint |
| **Uptime percentage** | Configurable rolling window (default: 30 days) |
| **SQLite backend** | Embedded, zero-config persistent storage |
| **npm wrapper** | First-class JavaScript/TypeScript integration |
| **Stripe billing** | Subscription tiers control monitor quotas |

---

## Architecture

```
blackroad-os-uptime-kuma/
├── src/
│   └── uptime_monitor.py   # Core monitoring engine (Python 3.11+)
├── tests/                  # Unit + E2E test suite (pytest)
├── .github/
│   └── workflows/
│       └── ci.yml          # GitHub Actions CI pipeline
├── LICENSE
└── README.md               # ← you are here
```

### Data flow

```
Scheduler ──► UptimeMonitor.run_check()
                 │
                 ├── check_http()  ──► requests + SSL cert inspection
                 ├── check_tcp()   ──► socket.create_connection()
                 ├── check_ping()  ──► subprocess ping
                 └── check_dns()   ──► (ping fallback; full DNS in roadmap)
                 │
                 ▼
           SQLite (heartbeats, incidents, monitors, status_pages)
```

---

## Installation

### Python (pip)

```bash
pip install requests
```

Clone and run directly:

```bash
git clone https://github.com/BlackRoad-OS/blackroad-os-uptime-kuma.git
cd blackroad-os-uptime-kuma
pip install requests
python src/uptime_monitor.py --help
```

### npm / Node.js wrapper

The `@blackroad-os/uptime-kuma` npm package provides a thin JavaScript/TypeScript wrapper around the Python engine, suitable for embedding in Node.js services, Next.js API routes, or CLI toolchains.

> **Status:** The npm package is currently in active development. Watch the repository for the first published release on the [npm registry](https://www.npmjs.com/package/@blackroad-os/uptime-kuma).

```bash
npm install @blackroad-os/uptime-kuma
# or
yarn add @blackroad-os/uptime-kuma
```

```js
import { UptimeClient } from '@blackroad-os/uptime-kuma';

const client = new UptimeClient({ dbPath: '~/.blackroad/uptime.db' });

// Add a monitor
const id = await client.addMonitor('Worlds API', 'http', 'https://worlds.blackroad.io/stats');

// Run all checks
const results = await client.runAllChecks();
console.log(results);
```

> **Note:** Requires Python 3.11+ available on `PATH`. The npm package spawns the Python engine as a subprocess and communicates via JSON stdio.

---

## Quick Start

```bash
# 1. Add a monitor
python src/uptime_monitor.py add "Worlds API" http https://worlds.blackroad.io/stats

# 2. Run all checks once
python src/uptime_monitor.py check-all

# 3. Show current status table
python src/uptime_monitor.py status
```

Example output:

```
Worlds API (a1b2c3d4): up (142.3ms)
```

---

## CLI Reference

```
usage: uptime_monitor.py [-h] {add,check-all,status} ...

Uptime monitoring system

subcommands:
  add          Add a new monitor
  check-all    Run all active monitors once
  status       Print current status for all monitors

add arguments:
  name         Human-readable monitor name
  type         Protocol: http | tcp | ping | dns | push
  target       URL, host:port, or IP address
  --interval   Check interval in seconds (default: 60)
  --tags       Space-separated tags

examples:
  python src/uptime_monitor.py add "API" http https://api.blackroad.io
  python src/uptime_monitor.py add "DB"  tcp db.internal:5432
  python src/uptime_monitor.py add "CDN" ping cdn.blackroad.io
```

---

## Configuration

The monitor database is stored at `~/.blackroad/uptime.db` by default. Override with the `db_path` constructor argument or set the environment variable:

```bash
export BLACKROAD_UPTIME_DB=/var/lib/blackroad/uptime.db
```

| Parameter | Default | Description |
|---|---|---|
| `db_path` | `~/.blackroad/uptime.db` | SQLite database path |
| `interval_s` | `60` | Seconds between checks |
| `timeout_s` | `10` | Per-check timeout |
| `retries` | `0` | Retry count before marking down |

---

## Database Schema

All data is stored in a local SQLite database with four tables:

### `monitors`
| Column | Type | Description |
|---|---|---|
| `id` | TEXT PK | Short UUID |
| `name` | TEXT | Human-readable name |
| `type` | TEXT | http / tcp / ping / dns / push |
| `target` | TEXT | URL or host:port |
| `interval_s` | INTEGER | Check frequency |
| `timeout_s` | INTEGER | Request timeout |
| `retries` | INTEGER | Retry count |
| `status` | TEXT | unknown / up / down / paused / maintenance |
| `up_since` | TEXT | ISO timestamp of last recovery |
| `last_check` | TEXT | ISO timestamp of last check |
| `response_time_ms` | REAL | Latest response time |
| `cert_expiry_days` | INTEGER | Days until SSL cert expiry |
| `tags` | TEXT | JSON array of tag strings |
| `created_at` | TEXT | ISO creation timestamp |

### `heartbeats`
| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `monitor_id` | TEXT FK | References `monitors.id` |
| `timestamp` | TEXT | ISO timestamp |
| `status` | TEXT | up / down |
| `response_time_ms` | REAL | Response time for this check |

### `incidents`
| Column | Type | Description |
|---|---|---|
| `id` | TEXT PK | Short UUID |
| `monitor_id` | TEXT FK | References `monitors.id` |
| `started_at` | TEXT | ISO timestamp of downtime start |
| `resolved_at` | TEXT | ISO timestamp of recovery (nullable) |
| `duration_s` | INTEGER | Total downtime seconds |
| `cause` | TEXT | Error message or description |
| `notified` | BOOLEAN | Whether notifications were sent |

### `status_pages`
| Column | Type | Description |
|---|---|---|
| `id` | TEXT PK | Short UUID |
| `name` | TEXT | Page display name |
| `slug` | TEXT UNIQUE | URL-safe identifier |
| `monitors` | TEXT | JSON array of monitor IDs |
| `description` | TEXT | Page description |
| `logo_url` | TEXT | Custom logo URL |
| `theme` | TEXT | light / dark |

---

## Stripe Integration

BlackRoad OS Uptime Kuma supports **Stripe-powered subscription tiers** to gate monitor quotas and feature access. This enables billing-aware deployments where customers are limited to the monitors included in their plan.

### How it works

1. A Stripe webhook delivers subscription events to your BlackRoad backend.
2. The backend sets the active plan on the `UptimeMonitor` instance or database.
3. `add_monitor()` enforces the quota for the customer's tier before inserting.

### Tier limits (reference)

| Plan | Monitor limit | Check interval | Status pages |
|---|---|---|---|
| **Free** | 5 | 5 min | 1 |
| **Pro** | 50 | 1 min | 10 |
| **Business** | Unlimited | 30 s | Unlimited |

### Stripe webhook example

> **Security:** Never commit Stripe secret keys to source control. Supply them via environment variables or a secrets manager (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`).

```python
import os
import stripe
from uptime_monitor import UptimeMonitor

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]  # e.g. sk_test_... or sk_live_...

@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig = request.headers["Stripe-Signature"]
    event = stripe.Webhook.construct_event(payload, sig, os.environ["STRIPE_WEBHOOK_SECRET"])

    if event["type"] == "customer.subscription.updated":
        subscription = event["data"]["object"]
        plan = subscription["items"]["data"][0]["price"]["lookup_key"]
        # Update customer's monitor quota in your user DB
        update_customer_plan(subscription["customer"], plan)

    return "", 200
```

---

## Status Pages

Status pages expose a public, read-only view of selected monitors for a given slug.

```python
from uptime_monitor import UptimeMonitor

monitor = UptimeMonitor()
page = monitor.get_status_page("blackroad-platform")
if page:
    print(page.name, page.monitors)
```

Each status page supports:
- Custom **name** and **description**
- Optional **logo URL**
- **light** or **dark** theme
- Pinned subset of monitors

---

## API Reference

### `UptimeMonitor(db_path=None)`

Instantiates the engine. Creates the database directory and schema on first run.

### `add_monitor(name, type, target, interval_s=60, timeout_s=10, tags=None) → str`

Adds a monitor and returns its short ID.

### `run_check(monitor_id) → bool`

Runs a single check, records a heartbeat, creates an incident if down. Returns `True` if up.

### `run_all_checks() → dict[str, bool]`

Runs checks for all non-paused monitors. Returns a mapping of monitor ID → up/down bool.

### `get_uptime_percent(monitor_id, days=30) → float`

Returns uptime percentage (0–100) over the rolling window.

### `get_response_time_avg(monitor_id, hours=24) → float`

Returns average response time in milliseconds over the last N hours.

### `get_incidents(monitor_id=None, open_only=False) → list[Incident]`

Returns incidents, optionally filtered by monitor or open/resolved state.

### `resolve_incident(incident_id) → bool`

Marks an incident resolved and records duration.

### `get_heartbeat_history(monitor_id, limit=100) → list[dict]`

Returns the most recent heartbeats (oldest-first) with timestamp, status, and response time.

### `get_status_page(slug) → StatusPage | None`

Returns a `StatusPage` dataclass by slug, or `None` if not found.

---

## Testing (E2E & Unit)

The test suite uses **pytest** with coverage reporting.

### Run all tests

```bash
pip install pytest pytest-cov requests
pytest tests/ -v --cov=src --cov-report=term-missing
```

### Run E2E tests only

```bash
pytest tests/ -v -k "e2e"
```

### Run unit tests only

```bash
pytest tests/ -v -k "not e2e"
```

### Coverage

```bash
pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html
```

E2E tests exercise the full monitor lifecycle:
1. Create a monitor
2. Run a check against a live endpoint
3. Verify the heartbeat is recorded
4. Simulate a downtime incident
5. Resolve the incident and verify duration

---

## CI / CD

Every push and pull request triggers the GitHub Actions CI pipeline:

```yaml
# .github/workflows/ci.yml
- Lint with ruff
- Run pytest with coverage
- Smoke-test CLI (--help)
```

[![CI](https://github.com/BlackRoad-OS/blackroad-os-uptime-kuma/actions/workflows/ci.yml/badge.svg)](https://github.com/BlackRoad-OS/blackroad-os-uptime-kuma/actions/workflows/ci.yml)

---

## Security

- All database writes use **parameterised SQLite queries** — no SQL injection vectors.
- SSL certificate inspection uses Python's built-in `ssl` module with default certificate verification.
- Stripe webhook signatures are verified with `stripe.Webhook.construct_event()` before processing.
- Secret keys (Stripe, API tokens) must be provided via **environment variables**, never committed to source.

To report a vulnerability, please open a **private** security advisory at:
https://github.com/BlackRoad-OS/blackroad-os-uptime-kuma/security/advisories

---

## Contributing

1. Fork the repository.
2. Create a feature branch: `git checkout -b feat/my-feature`.
3. Install dev dependencies: `pip install pytest pytest-cov ruff requests`.
4. Make your changes and add tests.
5. Lint: `ruff check src/`.
6. Test: `pytest tests/ -v`.
7. Open a pull request against `main`.

Please follow [Conventional Commits](https://www.conventionalcommits.org/) for commit messages.

---

## License

[MIT](LICENSE) © BlackRoad OS
