"""Scanner: negotiated TLS group / SSH KEX, probed only against channels listed in topology.yaml.

The probe commands must run where OpenSSL 3.5 / OpenSSH 10 live (the verifier container), because chronos-api's
python:3.12-slim ships OpenSSL 3.0 and cannot name ML-KEM groups. Set CHRONOS_PROBE_PREFIX, e.g. "docker exec chronos-verifier".
"""
import os
import re
import shlex
import subprocess
import json
import urllib.parse
import urllib.request

from chronos.discovery.common import asset
from chronos.risk.catalog import kex_class

SOURCE = "live_probe"
TLS_GROUP = re.compile(r"(?:Negotiated TLS1\.3 group|Server Temp Key|Peer Temp Key):\s*([A-Za-z0-9_\-]+)")
TLS_PROTO = re.compile(r"Protocol version:\s*(\S+)|Protocol\s*:\s*(\S+)")
SSH_KEX = re.compile(r"kex: algorithm:\s*(\S+)")


def parse_s_client(text: str) -> dict | None:
    g = TLS_GROUP.search(text)
    if not g:
        return None
    p = TLS_PROTO.search(text)
    return {"group": g.group(1), "protocol": next((x for x in (p.groups() if p else ()) if x), None)}


def parse_ssh(text: str) -> dict | None:
    m = SSH_KEX.search(text)
    return {"group": m.group(1), "protocol": "ssh"} if m else None


def shell_runner(cmd: list[str], timeout: int = 15) -> str:
    prefix = shlex.split(os.environ.get("CHRONOS_PROBE_PREFIX", ""))
    r = subprocess.run([*prefix, *cmd], capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    return r.stdout + r.stderr


def http_runner(cmd: list[str], timeout: int = 15) -> str:
    """Translate our two fixed probe commands to the internal allow-listed worker."""
    if cmd[:2] == ["openssl", "s_client"]:
        host, port = cmd[cmd.index("-connect") + 1].rsplit(":", 1)
        protocol = "tls"
    elif cmd[0] == "ssh":
        host, port = cmd[-2].split("@", 1)[1], cmd[cmd.index("-p") + 1]
        protocol = "ssh"
    else:
        raise ValueError("unsupported probe command")
    url = os.environ["CHRONOS_PROBE_URL"].rstrip("/") + "/probe/" + protocol + "?" + urllib.parse.urlencode({"host": host, "port": port})
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + os.environ["CHRONOS_WORKER_TOKEN"]})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.load(response)
    if body.get('returncode', 0):
        raise OSError('authenticated protocol probe failed')
    return body.get("output", body.get("stdout", ""))


def probe_channel(ch: dict, run=shell_runner) -> dict | None:
    host, port = ch["dst"], ch.get("port", 443)
    if ch["protocol"] == "tls":
        return parse_s_client(run(["openssl", "s_client", "-connect", f"{host}:{port}", "-brief"]))
    return parse_ssh(run(["ssh", "-vv", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-p", str(port), f"probe@{host}", "true"]))


def scan(topology: dict, run=shell_runner) -> list[dict]:
    out = []
    for ch in topology["channels"]:
        if ch.get("probe", True) is False:
            continue
        try:
            got = probe_channel(ch, run)
        except (subprocess.SubprocessError, OSError):
            got = None
        if not got:
            continue
        cls = kex_class(got["group"])
        out.append(asset(path=f"live://{ch['dst']}:{ch.get('port', '')}", line=None, asset_type="protocol",
                         algorithm=got["group"], usage="key_exchange", source=SOURCE,
                         status="vulnerable" if cls == "classical" else "resistant",
                         params={"channel": ch["id"], "negotiated_group": got["group"], "protocol": got["protocol"] or ch["protocol"]}))
    return out
