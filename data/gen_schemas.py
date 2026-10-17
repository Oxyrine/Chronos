"""Seeded synthetic corpus for the shelf-life classifier (spec 10.1, seed 7). Output: data/generated/columns.jsonl.

One record per column: pre-computed in-DB-style profile (same patterns as profile_column.sql), name, siblings, context, label.
Values exist only inside this script's memory while profiling; nothing but aggregates is written.
"""
import json
import math
import pathlib
import random
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from chronos.shelflife.profile import SAMPLE, profile_values  # noqa: E402
from data.domains import ARCHETYPES, COUNTS, SPLIT, ST_ASTER  # noqa: E402
from data.semantics import SEMANTICS  # noqa: E402

SEED = 7
NOISE_SUFFIX = ["", "", "", "", "_v2", "_col", "_new", "_x", "_tmp"]
MISLEADING = ["misc_field_{n}", "col_{n}", "attr_{n}", "field_{n}", "data_{n}", "val_{n}", "x{n}"]
NULL_RATE = (0.0, 0.0, 0.02, 0.1, 0.3)


def style(name: str, r: random.Random) -> str:
    """Vary naming convention so the model cannot memorise snake_case names."""
    parts = name.split("_")
    k = r.random()
    if k < .55:
        out = name
    elif k < .70:
        out = parts[0] + "".join(p.capitalize() for p in parts[1:])
    elif k < .80:
        out = "".join(p.capitalize() for p in parts)
    elif k < .87:
        out = name.upper()
    elif k < .94:
        out = "".join(p[:3] if len(p) > 4 else p for p in parts)  # abbreviation
    else:
        out = name.replace("_", "")
    return out + r.choice(NOISE_SUFFIX)


def make_values(sem: str, r: random.Random, n: int = SAMPLE, null_rate: float = 0.0) -> list:
    gen = SEMANTICS[sem][3]
    vals = []
    for _ in range(n):
        vals.append(None if null_rate and r.random() < null_rate else gen(r))
    return vals


def token_words(s: str) -> list[str]:
    s = re.sub(r"([a-z])([A-Z])", r"\1_\2", s)
    return [w for w in re.split(r"[^A-Za-z0-9]+", s.lower()) if w]


def column_record(domain, split, table, rows, col_name, sem, siblings, r, misleading, person_fk, expires_like) -> dict:
    cat, sqltype, _, _ = SEMANTICS[sem]
    prof = profile_values(make_values(sem, r, null_rate=r.choice(NULL_RATE)))
    return {"domain": domain, "split": split, "table": table, "column": col_name, "sem": sem, "category": cat, "sqltype": sqltype,
            "misleading": misleading, "profile": prof, "siblings": siblings, "row_count": rows, "person_fk": person_fk, "expires_like": expires_like}


def build_table(domain, split, idx, arch_name, cols_spec, r) -> list[dict]:
    table = arch_name if idx < len(ARCHETYPES[domain]) else f"{arch_name}_{idx}"
    table = style(table, r) if idx >= len(ARCHETYPES[domain]) else table
    sems = []
    for spec in cols_spec:
        opt = spec.endswith("?")
        if opt and r.random() > .6:
            continue
        sems.append(spec.rstrip("?"))
    for _ in range(r.randint(0, 3)):  # unrelated housekeeping columns
        sems.append(r.choice(["status", "country", "version", "created", "flag", "label"]))
    r.shuffle(sems)
    rows = int(10 ** r.uniform(2.3, 6.0))
    names = []
    for s in sems:
        names.append(style(r.choice(SEMANTICS[s][2]), r))
    mis = [r.random() < .10 for _ in sems]
    names = [MISLEADING[r.randrange(len(MISLEADING))].format(n=r.randint(1, 40)) if m else n for n, m in zip(names, mis)]
    expires_like = any(s in ("expires_at",) for s in sems)
    person_fk = any(s == "person_id" for s in sems)
    return [column_record(domain, split, table, rows, n, s, [x for x in names if x != n], r, m, person_fk, expires_like)
            for n, s, m in zip(names, sems, mis)]


def generate(seed: int = SEED, scale: float = 1.0) -> list[dict]:
    out = []
    for domain, count in COUNTS.items():
        r = random.Random(f"{seed}-{domain}")
        arch = list(ARCHETYPES[domain].items())
        for i in range(max(1, int(count * scale))):
            name, spec = arch[i % len(arch)]
            out += build_table(domain, SPLIT[domain], i, name, spec, r)
    return out


def st_aster(seed: int = 42) -> list[dict]:
    """Demo tables with their real column names: evaluation only, never part of training."""
    r = random.Random(seed)
    out = []
    for table, t in ST_ASTER.items():
        names = [c for c, _ in t["cols"]]
        for col, sem in t["cols"]:
            out.append(column_record("st_aster", "demo", table, t["rows"], col, sem, [n for n in names if n != col], r, False,
                                     any(s == "person_id" for _, s in t["cols"]), any(s == "expires_at" for _, s in t["cols"])))
    return out


def write(path="data/generated/columns.jsonl", scale: float = 1.0) -> int:
    recs = generate(scale=scale) + st_aster()
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(x) for x in recs) + "\n")
    return len(recs)


def write_labels(path="data/labels.yaml") -> None:
    import yaml
    from data.semantics import categories
    pathlib.Path(path).write_text("# Team-written mapping: column semantics -> category. Policy periods live in chronos/risk/policy.yaml.\n"
                                  "# Not legal advice; every assignment is an assumption shown on the data-methodology slide.\n"
                                  + yaml.safe_dump(categories(), sort_keys=True))


if __name__ == "__main__":
    scale = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
    write_labels()
    print(write(scale=scale), "columns")
