"""Synthetic hospital JSON service; SQL identifiers are an explicit allow-list."""
import datetime
import decimal
import json
import os
import platform
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import psycopg2
from psycopg2.extras import RealDictCursor

ROUTES = {"patients": ("patients", "patient_id"), "records": ("encounters", "patient_id"),
          "encounters": ("encounters", "patient_id"), "labs": ("lab_results", "patient_id"),
          "genomics": ("genomics_results", "patient_id"), "reminders": ("appointment_reminders", "patient_id")}

def encode(value):
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    raise TypeError(type(value).__name__)

class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, value, count=0):
        body = json.dumps(value, default=encode, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Record-Count", str(count))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/health":
            return self.send_json(200, {"status": "ok", "arch": platform.machine()})
        m = re.fullmatch(r"/api/(patients|records|encounters|labs|genomics|reminders)(?:/(\d+|export))?", url.path)
        if not m:
            return self.send_json(404, {"error": "unknown route"})
        table, key = ROUTES[m[1]]
        try:
            limit = int(parse_qs(url.query).get("limit", ["100"])[0])
            if not 1 <= limit <= 10000:
                raise ValueError()
        except ValueError:
            return self.send_json(400, {"error": "limit must be an integer from 1 to 10000"})
        value = m[2]
        if value and value != "export" and (len(value) > 10 or not 1 <= int(value) <= 2147483647):
            return self.send_json(400, {"error": "id must be a positive 32-bit integer"})
        where, args = (f" WHERE {key} = %s", [int(value)]) if value and value != "export" else ("", [])
        try:
            with psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=5) as db:
                with db.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(f"SELECT * FROM {table}{where} ORDER BY 1 LIMIT %s", args + [limit])
                    rows = [dict(row) for row in cur.fetchall()]
            self.send_json(200, rows, len(rows))
        except psycopg2.Error:
            self.send_json(503, {"error": "database unavailable"})

if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
