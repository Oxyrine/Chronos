"""Column-category model, decision rule, LLM fallback, overrides, and evaluation (spec 7.3, 10).

The model predicts WHAT KIND of data a column holds. policy.yaml decides how many years it stays confidential.
Backend: Snap ML BoostingMachineClassifier when importable (IBM Z), else scikit-learn HistGradientBoosting (stated on the slide).
Artifacts are written and read on the same machine only; the loader refuses a model trained on a different byte order.
"""
import json
import os
import pathlib
import sys
import time

import numpy as np

from chronos.risk.policy import load_policy, longer, years
from chronos.shelflife.features import FeatureBuilder
from chronos.shelflife.profile import PATTERNS

MODEL_VERSION = "category-1.0.0"
CATEGORIES = list(load_policy()["categories"])
MODEL_DIR = pathlib.Path(__file__).parent / "model"
THRESH_LONGER = 0.30   # prefer a longer-period category at this probability (spec 7.3)
THRESH_LLM = 0.50      # below this top probability, ask the LLM for a second opinion


def make_classifier(seed: int = 7):
    """Snap ML on IBM Z. CHRONOS_ROUNDS lowers its boosting rounds for quick test runs (default 200 for real training)."""
    try:
        from snapml import BoostingMachineClassifier
        kw = dict(num_round=int(os.environ.get("CHRONOS_ROUNDS", 200)), learning_rate=0.1, max_depth=6, random_state=seed)
        try:  # use every core: training is one-off and nothing else may be running then (llama-server and sandbox runs are off)
            return "snapml", BoostingMachineClassifier(n_jobs=int(os.environ.get("CHRONOS_JOBS", os.cpu_count() or 1)), **kw)
        except TypeError:
            return "snapml", BoostingMachineClassifier(**kw)
    except ImportError:
        from sklearn.ensemble import HistGradientBoostingClassifier
        return "sklearn-hgb", HistGradientBoostingClassifier(max_iter=250, learning_rate=0.1, max_leaf_nodes=15, random_state=seed)


MIN_CLASS_SHARE = 0.25  # rare classes are repeated up to this share of the largest class; the long-period classes are the rare ones


def oversample(X: np.ndarray, y: np.ndarray, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """Deterministic random oversampling. Without it a class that is 1.5% of the data (genetic) is learned as noise."""
    rng = np.random.RandomState(seed)
    counts = np.bincount(y, minlength=len(CATEGORIES))
    floor = int(counts.max() * MIN_CLASS_SHARE)
    idx = [np.arange(len(y))]
    for c, n in enumerate(counts):
        if 0 < n < floor:
            idx.append(rng.choice(np.where(y == c)[0], floor - n, replace=True))
    keep = np.concatenate(idx)
    return X[keep], y[keep]


class CategoryModel:
    def __init__(self):
        self.fb = FeatureBuilder()
        self.backend, self.clf = make_classifier()
        self.byteorder = sys.byteorder

    def fit(self, recs: list[dict]) -> "CategoryModel":
        X = self.fb.fit(recs).transform(recs)
        self.clf.fit(*oversample(X, np.array([CATEGORIES.index(r["category"]) for r in recs])))
        return self

    def proba(self, recs: list[dict]) -> np.ndarray:
        """(n, len(CATEGORIES)) with columns in CATEGORIES order, even when a class was absent from training."""
        raw = self.clf.predict_proba(self.fb.transform(recs))
        out = np.zeros((len(recs), len(CATEGORIES)))
        for j, c in enumerate(self.clf.classes_):
            out[:, int(c)] = raw[:, j]
        return out

    def save(self, path=MODEL_DIR / "model.joblib"):
        import joblib
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @staticmethod
    def load(path=MODEL_DIR / "model.joblib") -> "CategoryModel":
        import joblib
        m = joblib.load(path)
        if m.byteorder != sys.byteorder:
            raise RuntimeError(f"model trained on a {m.byteorder}-endian machine; retrain here (never load x86 pickles on s390x)")
        return m


def decide(probs: np.ndarray) -> tuple[str, float]:
    """Top category, unless a longer-period category has probability >= 0.30, then the longest such one (spec 7.3, 9.5)."""
    top = CATEGORIES[int(np.argmax(probs))]
    longer_ok = [c for i, c in enumerate(CATEGORIES) if years(c) > years(top) and probs[i] >= THRESH_LONGER]
    if longer_ok:
        top = max(longer_ok, key=lambda c: (years(c), probs[CATEGORIES.index(c)]))
    return top, float(probs[CATEGORIES.index(top)])


def llm_second_opinion(rec: dict, llm) -> dict | None:
    """Granite gets the column name, type and pattern summary. Never values (there are none in a record)."""
    hits = {k: round(rec["profile"][k], 2) for k in PATTERNS if rec["profile"][k] >= 0.3}
    prompt = (f"Column {rec['table']}.{rec['column']} type {rec['sqltype']}; pattern hit rates {hits}; "
              f"mean length {rec['profile']['mean_len']:.0f}. Reply JSON {{\"category\": one of {CATEGORIES}, \"reason\": short}}.")
    try:
        out = llm(prompt)
        return out if out.get("category") in CATEGORIES else None
    except Exception:
        return None


def salient(rec: dict) -> list[str]:
    """Up to 3 readable features: strongest value patterns, then the column name, then the person link. Indicative, not attribution."""
    hits = sorted(((rec["profile"][k], k) for k in PATTERNS if rec["profile"][k] >= 0.5 and k not in ("has_space", "alpha_only", "numeric")), reverse=True)
    out = [f"pattern:{k}={v:.2f}" for v, k in hits[:2]]
    out.append("name:" + rec["column"])
    if rec["person_fk"]:
        out.append("fk:person")
    return out[:3]


def predict(model: CategoryModel, recs: list[dict], store="records-db", llm=None, overrides: dict | None = None) -> list[dict]:
    """ShelfLifePrediction[] (spec 8.3)."""
    P = model.proba(recs)
    out = []
    for rec, p in zip(recs, P):
        cat, _ = decide(p)
        decided_by = "model"
        if llm and p.max() < THRESH_LLM and (op := llm_second_opinion(rec, llm)):
            both = longer(cat, op["category"])
            if both != cat:
                cat, decided_by = both, "llm"
        override = (overrides or {}).get(f"{rec['table']}.{rec['column']}")
        if override:
            cat, decided_by = override["category"], "override"
        order = np.argsort(-p)[:4]
        out.append({"store": store, "table": rec["table"], "column": rec["column"], "category": cat, "policy_years": years(cat),
                    "policy_version": load_policy()["version"], "probabilities": {CATEGORIES[i]: round(float(p[i]), 4) for i in order},
                    "decided_by": decided_by, "top_features": salient(rec), "model_version": MODEL_VERSION, "override": override})
    return out


# ---- evaluation ----

KEYWORDS = [  # name-only baseline (spec 10.3), deliberately generous
    (r"gene|variant|hgvs|genotype|zygos|snp|allele", "genetic"), (r"vacc|immun|growth|muac|grade|report|teacher|conduct", "child_health"),
    (r"diagnos|icd|clinic|note|blood|lab|loinc|medic|drug|allerg|admit|visit|result|unit", "clinical"),
    (r"dob|birth|name|national|ssn|aadhaar|address|passport|licen|gender|sex", "identity"), (r"phone|mobile|email|mail|msisdn|tel", "contact"),
    (r"amount|currency|salary|card|pay|insur|balance|income|invoice|iban|account", "financial"), (r"token|otp|code|expir|session|hash|csrf|pin", "auth_secret"),
    (r"sms|remind|slot|schedul|timetable|cart|draft|send", "scheduling"), (r"_id$|id$|ref$", "pseudonymous_id"),
]


def keyword_baseline(rec: dict) -> str:
    import re
    from chronos.shelflife.features import words
    text = " ".join(words(rec["column"])) + " " + rec["column"].lower()
    return next((c for rx, c in KEYWORDS if re.search(rx, text)), "non_sensitive")


def metrics(true: list[str], pred: list[str]) -> dict:
    from sklearn.metrics import f1_score
    ty, py = [years(t) for t in true], [years(p) for p in pred]
    n = max(len(true), 1)
    cm = {t: {p: 0 for p in CATEGORIES} for t in CATEGORIES}
    for t, p in zip(true, pred):
        cm[t][p] += 1
    return {"n": len(true), "macro_f1": round(float(f1_score(true, pred, labels=CATEGORIES, average="macro", zero_division=0)), 4),
            "accuracy": round(sum(t == p for t, p in zip(true, pred)) / n, 4),
            "under_protection_rate": round(sum(p < t for t, p in zip(ty, py)) / n, 4),
            "over_protection_rate": round(sum(p > t for t, p in zip(ty, py)) / n, 4), "confusion_matrix": cm}


def evaluate(model: CategoryModel, recs: list[dict]) -> dict:
    t0 = time.perf_counter()
    preds = [p["category"] for p in predict(model, recs)]
    ms = (time.perf_counter() - t0) * 1000 / max(len(recs), 1)
    true = [r["category"] for r in recs]
    mis = [i for i, r in enumerate(recs) if r["misleading"]]
    base = [keyword_baseline(r) for r in recs]
    out = metrics(true, preds)
    out["keyword_baseline"] = {k: v for k, v in metrics(true, base).items() if k != "confusion_matrix"}
    if mis:
        out["misleading_names"] = {"n": len(mis), "model": {k: v for k, v in metrics([true[i] for i in mis], [preds[i] for i in mis]).items() if k != "confusion_matrix"},
                                   "keyword_baseline": {k: v for k, v in metrics([true[i] for i in mis], [base[i] for i in mis]).items() if k != "confusion_matrix"}}
    out["predict_ms_per_column"] = round(ms, 3)
    out["backend"] = model.backend
    return out


def load_records(path="data/generated/columns.jsonl") -> dict[str, list[dict]]:
    by: dict[str, list[dict]] = {}
    for line in pathlib.Path(path).read_text().splitlines():
        r = json.loads(line)
        by.setdefault(r["split"], []).append(r)
    return by
