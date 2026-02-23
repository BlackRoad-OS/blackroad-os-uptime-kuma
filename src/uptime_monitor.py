"""
Uptime monitoring system inspired by Uptime Kuma.
Provides HTTP/TCP/Ping/DNS/Push monitoring with incident tracking and status pages.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import sqlite3
import json
import socket
import subprocess
import ssl
from pathlib import Path
import requests


@dataclass
class Monitor:
    """Represents a monitor configuration."""
    id: str
    name: str
    type: str  # http, tcp, ping, dns, push
    target: str
    interval_s: int = 60
    timeout_s: int = 10
    retries: int = 0
    status: str = "unknown"  # up, down, paused, maintenance
    up_since: Optional[datetime] = None
    last_check: Optional[datetime] = None
    response_time_ms: Optional[float] = None
    cert_expiry_days: Optional[int] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class Incident:
    """Represents a downtime incident."""
    id: str
    monitor_id: str
    started_at: datetime
    resolved_at: Optional[datetime] = None
    duration_s: Optional[int] = None
    cause: str = ""
    notified: bool = False


@dataclass
class StatusPage:
    """Represents a public status page."""
    id: str
    name: str
    slug: str
    monitors: List[str]
    description: str = ""
    logo_url: str = ""
    theme: str = "light"


class UptimeMonitor:
    """Core uptime monitoring engine."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = Path.home() / ".blackroad" / "uptime.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database schema."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS monitors (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                target TEXT NOT NULL,
                interval_s INTEGER DEFAULT 60,
                timeout_s INTEGER DEFAULT 10,
                retries INTEGER DEFAULT 0,
                status TEXT DEFAULT 'unknown',
                up_since TEXT,
                last_check TEXT,
                response_time_ms REAL,
                cert_expiry_days INTEGER,
                tags TEXT,
                created_at TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS heartbeats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                monitor_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                status TEXT,
                response_time_ms REAL,
                FOREIGN KEY(monitor_id) REFERENCES monitors(id)
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                monitor_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                resolved_at TEXT,
                duration_s INTEGER,
                cause TEXT,
                notified BOOLEAN DEFAULT 0,
                FOREIGN KEY(monitor_id) REFERENCES monitors(id)
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS status_pages (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                monitors TEXT,
                description TEXT,
                logo_url TEXT,
                theme TEXT DEFAULT 'light'
            )
        ''')
        conn.commit()
        conn.close()

    def add_monitor(self, name: str, monitor_type: str, target: str,
                    interval_s: int = 60, timeout_s: int = 10,
                    tags: Optional[List[str]] = None) -> str:
        """Add a new monitor."""
        import uuid
        monitor_id = str(uuid.uuid4())[:8]
        tags = tags or []

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            INSERT INTO monitors
            (id, name, type, target, interval_s, timeout_s, tags, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (monitor_id, name, monitor_type, target, interval_s, timeout_s,
              json.dumps(tags), datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return monitor_id

    def check_http(self, monitor_id: str) -> Dict:
        """Check HTTP(S) endpoint."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT target, timeout_s FROM monitors WHERE id = ?', (monitor_id,))
        row = c.fetchone()
        conn.close()

        if not row:
            return {"status": "error", "reason": "monitor not found"}

        target, timeout = row
        try:
            start = datetime.now()
            response = requests.get(target, timeout=timeout)
            response_time = (datetime.now() - start).total_seconds() * 1000
            status = "up" if response.status_code < 400 else "down"
            
            # Check SSL cert expiry if HTTPS
            if target.startswith("https://"):
                try:
                    cert_expiry = self._get_cert_expiry(target)
                except:
                    cert_expiry = None
            else:
                cert_expiry = None
            
            return {
                "status": status,
                "response_time_ms": response_time,
                "status_code": response.status_code,
                "cert_expiry_days": cert_expiry
            }
        except Exception as e:
            return {"status": "down", "reason": str(e)}

    def check_tcp(self, monitor_id: str) -> Dict:
        """Check TCP port connectivity."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT target, timeout_s FROM monitors WHERE id = ?', (monitor_id,))
        row = c.fetchone()
        conn.close()

        if not row:
            return {"status": "error", "reason": "monitor not found"}

        target, timeout = row
        try:
            parts = target.split(':')
            host = parts[0]
            port = int(parts[1]) if len(parts) > 1 else 80

            start = datetime.now()
            sock = socket.create_connection((host, port), timeout=timeout)
            response_time = (datetime.now() - start).total_seconds() * 1000
            sock.close()
            return {"status": "up", "response_time_ms": response_time}
        except Exception as e:
            return {"status": "down", "reason": str(e)}

    def check_ping(self, monitor_id: str) -> Dict:
        """Check ICMP ping."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT target FROM monitors WHERE id = ?', (monitor_id,))
        row = c.fetchone()
        conn.close()

        if not row:
            return {"status": "error", "reason": "monitor not found"}

        target = row[0]
        try:
            result = subprocess.run(['ping', '-c', '1', '-W', '5', target],
                                  capture_output=True, timeout=10)
            if result.returncode == 0:
                # Extract response time from ping output
                import re
                match = re.search(r'time=([\d.]+)\s*ms', result.stdout.decode())
                response_time = float(match.group(1)) if match else 0
                return {"status": "up", "response_time_ms": response_time}
            else:
                return {"status": "down"}
        except Exception as e:
            return {"status": "down", "reason": str(e)}

    def check_cert(self, monitor_id: str) -> Dict:
        """Check SSL certificate expiry."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT target FROM monitors WHERE id = ?', (monitor_id,))
        row = c.fetchone()
        conn.close()

        if not row:
            return {"status": "error", "reason": "monitor not found"}

        target = row[0]
        try:
            cert_expiry_days = self._get_cert_expiry(target)
            return {"status": "up", "cert_expiry_days": cert_expiry_days}
        except Exception as e:
            return {"status": "error", "reason": str(e)}

    def _get_cert_expiry(self, url: str) -> Optional[int]:
        """Get SSL certificate expiry days remaining."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.netloc.split(':')[0]

        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                import ssl as ssl_module
                expiry_str = cert.get('notAfter')
                # Parse SSL date format
                from email.utils import parsedate_to_datetime
                expiry_dt = parsedate_to_datetime(expiry_str)
                days_left = (expiry_dt - datetime.now(expiry_dt.tzinfo)).days
                return days_left

    def run_check(self, monitor_id: str) -> bool:
        """Run check for a monitor; create incident if down."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT type, status FROM monitors WHERE id = ?', (monitor_id,))
        row = c.fetchone()
        
        if not row:
            return False

        monitor_type, old_status = row

        # Dispatch to appropriate check
        if monitor_type == "http":
            result = self.check_http(monitor_id)
        elif monitor_type == "tcp":
            result = self.check_tcp(monitor_id)
        elif monitor_type == "ping":
            result = self.check_ping(monitor_id)
        elif monitor_type == "dns":
            result = self.check_ping(monitor_id)  # Simplified
        else:
            result = {"status": "unknown"}

        new_status = result.get("status", "unknown")
        response_time = result.get("response_time_ms")
        cert_expiry = result.get("cert_expiry_days")

        # Update monitor
        now = datetime.now().isoformat()
        if new_status == "up":
            up_since = up_since if (up_since := c.execute(
                'SELECT up_since FROM monitors WHERE id = ?', (monitor_id,)).fetchone()[0]) else now
        else:
            up_since = None

        c.execute('''
            UPDATE monitors
            SET status = ?, last_check = ?, response_time_ms = ?, cert_expiry_days = ?, up_since = ?
            WHERE id = ?
        ''', (new_status, now, response_time, cert_expiry, up_since, monitor_id))

        # Record heartbeat
        c.execute('''
            INSERT INTO heartbeats (monitor_id, timestamp, status, response_time_ms)
            VALUES (?, ?, ?, ?)
        ''', (monitor_id, now, new_status, response_time))

        # Create incident if status changed from up to down
        if old_status == "up" and new_status == "down":
            import uuid
            incident_id = str(uuid.uuid4())[:8]
            c.execute('''
                INSERT INTO incidents (id, monitor_id, started_at, cause)
                VALUES (?, ?, ?, ?)
            ''', (incident_id, monitor_id, now, result.get("reason", "Monitor down")))

        conn.commit()
        conn.close()
        return new_status == "up"

    def run_all_checks(self) -> Dict[str, bool]:
        """Run checks for all active monitors."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT id FROM monitors WHERE status != ?', ('paused',))
        monitors = c.fetchall()
        conn.close()

        results = {}
        for (monitor_id,) in monitors:
            results[monitor_id] = self.run_check(monitor_id)
        return results

    def get_status_page(self, slug: str) -> Optional[StatusPage]:
        """Get a status page with current monitor statuses."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT * FROM status_pages WHERE slug = ?', (slug,))
        row = c.fetchone()
        
        if not row:
            return None
        
        conn.close()
        return StatusPage(*row)

    def get_uptime_percent(self, monitor_id: str, days: int = 30) -> float:
        """Calculate uptime percentage from incident history."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        c.execute('''
            SELECT SUM(duration_s) FROM incidents
            WHERE monitor_id = ? AND started_at > ?
        ''', (monitor_id, cutoff))
        
        downtime = c.fetchone()[0] or 0
        conn.close()

        total_seconds = days * 86400
        return max(0, (1 - downtime / total_seconds) * 100)

    def get_response_time_avg(self, monitor_id: str, hours: int = 24) -> float:
        """Get average response time in ms over last N hours."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

        c.execute('''
            SELECT AVG(response_time_ms) FROM heartbeats
            WHERE monitor_id = ? AND timestamp > ? AND response_time_ms IS NOT NULL
        ''', (monitor_id, cutoff))
        
        avg = c.fetchone()[0] or 0
        conn.close()
        return avg

    def get_incidents(self, monitor_id: Optional[str] = None,
                     open_only: bool = False) -> List[Incident]:
        """Get incidents, optionally filtered."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        query = 'SELECT * FROM incidents'
        params = []
        if monitor_id:
            query += ' WHERE monitor_id = ?'
            params.append(monitor_id)
        if open_only:
            if params:
                query += ' AND resolved_at IS NULL'
            else:
                query += ' WHERE resolved_at IS NULL'

        c.execute(query, params)
        rows = c.fetchall()
        conn.close()

        incidents = []
        for row in rows:
            incidents.append(Incident(
                id=row[0], monitor_id=row[1],
                started_at=datetime.fromisoformat(row[2]),
                resolved_at=datetime.fromisoformat(row[3]) if row[3] else None,
                duration_s=row[4],
                cause=row[5],
                notified=bool(row[6])
            ))
        return incidents

    def resolve_incident(self, incident_id: str) -> bool:
        """Manually resolve an incident."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        now = datetime.now()
        
        c.execute('SELECT started_at FROM incidents WHERE id = ?', (incident_id,))
        row = c.fetchone()
        if not row:
            return False

        started = datetime.fromisoformat(row[0])
        duration = int((now - started).total_seconds())

        c.execute('''
            UPDATE incidents
            SET resolved_at = ?, duration_s = ?
            WHERE id = ?
        ''', (now.isoformat(), duration, incident_id))

        conn.commit()
        conn.close()
        return True

    def get_heartbeat_history(self, monitor_id: str,
                             limit: int = 100) -> List[Dict]:
        """Get time series of heartbeats (up/down/response_time)."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            SELECT timestamp, status, response_time_ms FROM heartbeats
            WHERE monitor_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (monitor_id, limit))
        
        rows = c.fetchall()
        conn.close()

        history = []
        for ts, status, response_time in reversed(rows):
            history.append({
                "timestamp": ts,
                "status": status,
                "response_time_ms": response_time
            })
        return history


# CLI interface
if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Uptime monitoring system")
    subparsers = parser.add_subparsers(dest="command")

    add_parser = subparsers.add_parser("add", help="Add a monitor")
    add_parser.add_argument("name")
    add_parser.add_argument("type")
    add_parser.add_argument("target")
    add_parser.add_argument("--interval", type=int, default=60)
    add_parser.add_argument("--tags", nargs="+", default=[])

    check_parser = subparsers.add_parser("check-all", help="Run all checks")
    status_parser = subparsers.add_parser("status", help="Show status")

    args = parser.parse_args()
    monitor = UptimeMonitor()

    if args.command == "add":
        mid = monitor.add_monitor(args.name, args.type, args.target,
                                 interval_s=args.interval, tags=args.tags)
        print(f"Monitor added: {mid}")
    elif args.command == "check-all":
        results = monitor.run_all_checks()
        for mid, status in results.items():
            print(f"{mid}: {'✓' if status else '✗'}")
    elif args.command == "status":
        conn = sqlite3.connect(monitor.db_path)
        c = conn.cursor()
        c.execute('SELECT id, name, status, response_time_ms FROM monitors')
        for mid, name, status, response_time in c.fetchall():
            print(f"{name} ({mid}): {status} ({response_time}ms)")
        conn.close()
