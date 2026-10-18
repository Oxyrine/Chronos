import http.client
import json
import os
import platform
import re
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

class Handler(BaseHTTPRequestHandler):
    def reply(self, status, value):
        data = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            return self.reply(200, {"status": "ok", "arch": platform.machine()})
        self.reply(404, {"error": "unknown route"})

    def do_POST(self):
        url = urlparse(self.path)
        m = re.fullmatch(r"/forward/(\d+)", url.path)
        if not m:
            return self.reply(404, {"error": "unknown route"})
        trace = parse_qs(url.query).get("trace", ["manual"])[0]
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", trace):
            return self.reply(400, {"error": "invalid trace"})
        try:
            db = http.client.HTTPConnection("portal-app", 8000, timeout=10)
            db.request("GET", f"/api/labs/{int(m[1])}?limit=1")
            source = db.getresponse()
            payload = source.read()
            db.close()
            if source.status != 200:
                return self.reply(502, {"error": "source unavailable"})
            ctx = ssl.create_default_context(cafile=os.environ.get("CA_FILE", "/keys/ca.pem"))
            peer = http.client.HTTPSConnection("partner-lab", 8443, context=ctx, timeout=10)
            peer.connect()
            tls = {"openssl": ssl.OPENSSL_VERSION, "peer": peer.sock.getpeercert().get("subject"), "tls": peer.sock.version()}
            records = json.loads(payload)
            if not isinstance(records, list):
                raise ValueError("source response must be a record list")
            peer.request("POST", "/ingest?" + urlencode({"trace": trace}), payload,
                         {"Content-Type": "application/json", "X-Record-Count": str(len(records))})
            response = peer.getresponse()
            response.read()
            peer.close()
            print(json.dumps({"trace": trace, "status": response.status, **tls}), flush=True)
            self.reply(response.status, {"trace": trace, "forwarded": response.status == 200, **tls})
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            self.reply(502, {"error": type(exc).__name__, "trace": trace})

if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8001), Handler).serve_forever()
