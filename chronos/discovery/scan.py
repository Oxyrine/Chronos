"""Run all six scanners, merge, write the CBOM. Entry point for POST /scan and `python -m chronos.discovery.scan`."""
import json
import pathlib
import time

from chronos.discovery import cbom_writer, certs_keys, configs, java_src, live_probe, llm_assist, merge, python_ast


def run(root, topology: dict, base=None, probe=None, llm=None, use_llm: bool = False) -> dict:
    """Returns {"findings", "cbom", "stats"}. probe: runner for live_probe (None skips it); llm: callable for llm_assist."""
    t0 = time.perf_counter()
    roots = [pathlib.Path(r) for r in ([root] if isinstance(root, (str, pathlib.Path)) else root)]
    base = pathlib.Path(base or roots[0])
    raw = []
    for r in roots:  # e.g. [repo/demo, repo/infra] with base=repo, so paths read demo/portal/nginx.conf
        raw += certs_keys.scan(r, base) + configs.scan(r, base) + python_ast.scan(r, base) + java_src.scan(r, base)
    if probe is not None:
        raw += live_probe.scan(topology, probe)
    if use_llm:
        covered = {a["path"] for a in raw}
        for r in roots:
            raw += llm_assist.scan_files(llm_assist.unparsed_files(r, base, covered), llm or llm_assist.granite)
    findings = merge.to_findings(merge.merge(raw), topology)
    cbom = cbom_writer.build(findings)
    return {"findings": findings, "cbom": cbom,
            "stats": {"raw_assets": len(raw), "findings": len(findings), "scan_seconds": round(time.perf_counter() - t0, 3)}}


if __name__ == "__main__":
    import sys
    import yaml
    root, topo_path, out = sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "out/cbom.json"
    res = run(root, yaml.safe_load(open(topo_path)))
    cbom_writer.validate(res["cbom"])
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(out).write_text(json.dumps(res["cbom"], indent=2))
    print(json.dumps(res["stats"]))
