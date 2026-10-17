import re
import sys

import numpy as np
import pytest

from chronos.common import samples
from chronos.risk.policy import rollup, years
from chronos.shelflife import model as M
from chronos.shelflife import profile
from data import gen_schemas


@pytest.fixture(scope="module")
def corpus():
    return gen_schemas.generate(scale=0.25) + gen_schemas.st_aster()


@pytest.fixture(scope="module")
def mdl(corpus):
    return M.CategoryModel().fit([r for r in corpus if r["split"] in ("train", "validation")])


def probs(**kw):
    p = np.zeros(len(M.CATEGORIES))
    for k, v in kw.items():
        p[M.CATEGORIES.index(k)] = v
    return p


# ---- decision rule (spec 7.3 / 9.5) ----
def test_longer_period_category_wins_at_030():
    assert M.decide(probs(clinical=0.55, genetic=0.30, identity=0.15))[0] == "genetic"
    assert M.decide(probs(clinical=0.60, genetic=0.29, identity=0.11))[0] == "clinical"


def test_picks_longest_among_qualifying_and_ignores_shorter():
    assert M.decide(probs(identity=0.40, clinical=0.31, genetic=0.30))[0] == "genetic"
    assert M.decide(probs(clinical=0.70, scheduling=0.30))[0] == "clinical"  # never moves to a shorter period


def test_llm_second_opinion_keeps_longer_period(mdl, corpus):
    rec = next(r for r in corpus if r["split"] == "demo" and r["column"] == "code")
    weak = lambda p: {"category": "genetic", "reason": "looks like a variant"}
    shorter = lambda p: {"category": "non_sensitive", "reason": "x"}
    # only consulted when the model is unsure; force that by patching the threshold
    old = M.THRESH_LLM
    M.THRESH_LLM = 1.01
    try:
        assert M.predict(mdl, [rec], llm=weak)[0]["category"] == "genetic" and M.predict(mdl, [rec], llm=weak)[0]["decided_by"] == "llm"
        base = M.predict(mdl, [rec])[0]["category"]
        assert M.predict(mdl, [rec], llm=shorter)[0]["category"] == base
        assert M.predict(mdl, [rec], llm=lambda p: 1 / 0)[0]["category"] == base  # LLM down: model answer stands
    finally:
        M.THRESH_LLM = old


def test_llm_never_receives_cell_values(corpus):
    seen = []
    rec = next(r for r in corpus if r["split"] == "demo")
    M.llm_second_opinion(rec, lambda p: seen.append(p) or {"category": "clinical"})
    assert seen and "profile" not in seen[0] and rec["column"] in seen[0]


def test_override_wins_and_is_marked(mdl, corpus):
    rec = next(r for r in corpus if r["split"] == "demo")
    ov = {f"{rec['table']}.{rec['column']}": {"category": "genetic", "by": "secops"}}
    p = M.predict(mdl, [rec], overrides=ov)[0]
    assert p["category"] == "genetic" and p["decided_by"] == "override" and p["policy_years"] == 75


# ---- predictions follow the contract ----
def test_prediction_matches_contract_and_policy(mdl, corpus):
    demo = [r for r in corpus if r["split"] == "demo"]
    out = M.predict(mdl, demo)
    for p in out:
        samples.validate("shelflife_prediction", p)
        assert p["policy_years"] == years(p["category"])  # the model never sets a period
        assert len(p["top_features"]) <= 3


def test_rollup_uses_longest_column_not_database_max(mdl, corpus):
    out = M.predict(mdl, [r for r in corpus if r["split"] == "demo"])
    tx = rollup(out)
    assert set(tx) == set(gen_schemas.ST_ASTER)
    for t, v in tx.items():
        assert v["x"] == max(p["policy_years"] for p in out if p["table"] == t)


def test_model_beats_nothing_on_validation(mdl, corpus):
    val = [r for r in corpus if r["split"] == "validation"]
    e = M.evaluate(mdl, val)
    assert e["macro_f1"] > e["keyword_baseline"]["macro_f1"]


# ---- byte order guard (never load an x86 pickle on s390x) ----
def test_loader_refuses_foreign_byteorder(mdl, tmp_path):
    mdl.byteorder = "big" if sys.byteorder == "little" else "little"
    try:
        mdl.save(tmp_path / "m.joblib")
        with pytest.raises(RuntimeError, match="endian"):
            M.CategoryModel.load(tmp_path / "m.joblib")
    finally:
        mdl.byteorder = sys.byteorder


# ---- in-DB profiling: SQL and Python share one pattern table ----
def test_profile_values_known_cases():
    p = profile.profile_values(["J45.909", "I10", None, "C50.1"])
    assert p["icd10"] == 1.0 and p["null_ratio"] == 0.25 and p["uniqueness"] == 1.0
    assert profile.profile_values(["+91 98765 43210", "9876543210"])["phone"] == 1.0
    assert profile.profile_values(["123456"])["six_digit"] == 1.0 and profile.profile_values(["1234567"])["six_digit"] == 0.0
    assert profile.profile_values(["1985-03-12"])["dob_like"] == 1.0 and profile.profile_values(["2025-03-12 10:00:00"])["dob_like"] == 0.0


def test_sql_embeds_every_pattern_and_selects_no_cell_values():
    sql = profile.profile_sql("otp_codes", "phone")
    for k in profile.PATTERNS:
        assert f"AS {k}" in sql
    assert sql.count("random() LIMIT 200") == 1
    final = sql.split("SELECT row_to_json(r) FROM")[1]
    assert not re.search(r"SELECT\s+v\b", final)  # only aggregates leave the CTE
    assert "'" in sql and "''" in profile.profile_sql("t", "c")  # alpha_only pattern's quote is escaped


@pytest.mark.parametrize("bad", ["x; DROP TABLE t", 'a"b', "1abc", "", "a" * 80, "a b"])
def test_sql_rejects_unsafe_identifiers(bad):
    with pytest.raises(ValueError):
        profile.profile_sql(bad, "c")
    with pytest.raises(ValueError):
        profile.profile_sql("t", bad)


def test_postgres_regex_compat_of_patterns():
    # patterns must stay inside the syntax Python re and Postgres ARE agree on: no lookaround, no \d \w shorthands
    for k, p in profile.PATTERNS.items():
        assert not re.search(r"\(\?|\\[dwsDWS]", p), k


def test_context_sql_validates_table():
    assert "otp_codes" in profile.context_sql("otp_codes")
    with pytest.raises(ValueError):
        profile.context_sql("a;b")


def test_corpus_is_seeded_and_label_noise_matches_spec(corpus):
    again = gen_schemas.generate(scale=0.25)
    assert [(r["table"], r["column"]) for r in again[:50]] == [(r["table"], r["column"]) for r in corpus[:50]]
    train = [r for r in corpus if r["split"] == "train"]
    assert 0.07 < sum(r["misleading"] for r in train) / len(train) < 0.13
    assert {r["split"] for r in corpus} == {"train", "validation", "test", "demo"}
    assert not any(r["domain"] == "st_aster" for r in corpus if r["split"] != "demo")
