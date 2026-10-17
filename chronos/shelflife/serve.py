"""Classify a live database: profile each column INSIDE the database container, then predict.

Only aggregate statistics cross the container boundary (see profile.py). Granite, if used, sees names/types/aggregates only.
"""
import json
import re

from chronos.shelflife import model as M
from chronos.shelflife.profile import context_sql, profile_sql, psql_runner

TABLES_SQL = "SELECT json_agg(table_name ORDER BY table_name) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';"
PERSON_ID = re.compile(r"(patient|person|people|user|customer|employee|student|subscriber|beneficiar|citizen|member|staff|child)_?(id|ref)", re.I)
PERSON_TABLE = re.compile(r"patient|person|people|user|customer|employee|student|subscriber|beneficiar|citizen|member|staff", re.I)
EXPIRES = re.compile(r"expir|valid_until|ttl", re.I)


def list_tables(run=psql_runner) -> list[str]:
    return json.loads(run(TABLES_SQL) or "[]")


def column_records(table: str, run=psql_runner) -> list[dict]:
    ctx = json.loads(run(context_sql(table)))
    cols = ctx["columns"] or []
    names = [c["name"] for c in cols]
    rows = ctx["row_count"]
    if not rows or rows <= 0:  # never ANALYZEd
        rows = int(run(f'SELECT count(*) FROM "{table}";') or 0) if re.match(r"^[A-Za-z_]\w*$", table) else 0
    person_fk = any(PERSON_TABLE.search(t) for t in ctx["fk_tables"] or []) or any(PERSON_ID.search(n) for n in names)
    expires = any(EXPIRES.search(n) for n in names)
    out = []
    for c in cols:
        out.append({"table": table, "column": c["name"], "sqltype": c["type"], "profile": json.loads(run(profile_sql(table, c["name"]))),
                    "siblings": [n for n in names if n != c["name"]], "row_count": rows, "person_fk": person_fk, "expires_like": expires,
                    "misleading": False})
    return out


def classify_database(model: M.CategoryModel, run=psql_runner, tables=None, llm=None, overrides=None, store="records-db") -> list[dict]:
    recs = [r for t in (tables or list_tables(run)) for r in column_records(t, run)]
    return M.predict(model, recs, store=store, llm=llm, overrides=overrides)


def table_facts(run=psql_runner, tables=None) -> dict:
    """{table: {"records": n, "store": ...}} for the risk engine's topology.tables (when topology.yaml lacks counts)."""
    out = {}
    for t in tables or list_tables(run):
        rows = column_records(t, run)
        out[t] = {"records": rows[0]["row_count"] if rows else 0}
    return out
