# BlackRoad Uptime Kuma

Uptime monitoring system inspired by Uptime Kuma. Provides HTTP/TCP/Ping/DNS/Push monitoring with incident tracking and status pages.

## Features

- **Multiple check types**: HTTP, TCP, Ping, DNS, Push
- **Incident tracking**: Automatic detection and resolution of downtime
- **Status pages**: Public status page display with customizable themes
- **Response time tracking**: Monitor performance metrics
- **SSL certificate expiry checking**: Track certificate expiration dates
- **SQLite backend**: Persistent storage at `~/.blackroad/uptime.db`

## Installation

```bash
pip install requests
```

## Usage

```bash
# Add a monitor
python src/uptime_monitor.py add "worlds API" http https://worlds.blackroad.io/stats

# Run all checks
python src/uptime_monitor.py check-all

# Show status
python src/uptime_monitor.py status
```

## Database Schema

- `monitors`: Monitor configurations
- `heartbeats`: Time series of check results
- `incidents`: Downtime incidents
- `status_pages`: Public status page configurations
