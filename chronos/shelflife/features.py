"""Feature builder for the column-category model (spec 7.3). Input is a column record (profile statistics + names + context);
no cell value is ever an input. Same builder for training and serving."""
import math
import re

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer

from chronos.shelflife.profile import STAT_NAMES

SQL_TYPES = ["text", "integer", "numeric", "date", "timestamp", "boolean", "other"]
_TYPE_MAP = {"character varying": "text", "varchar": "text", "char": "text", "bpchar": "text", "uuid": "text", "bigint": "integer", "smallint": "integer",
             "int": "integer", "int4": "integer", "int8": "integer", "double precision": "numeric", "real": "numeric", "decimal": "numeric",
             "timestamp without time zone": "timestamp", "timestamp with time zone": "timestamp", "timestamptz": "timestamp", "bool": "boolean"}


def norm_type(t: str) -> str:
    t = t.lower()
    t = _TYPE_MAP.get(t, t)
    return t if t in SQL_TYPES else "other"


def words(s: str) -> list[str]:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s)
    return [w for w in re.split(r"[^A-Za-z0-9]+", s.lower()) if w]


def name_text(rec: dict) -> str:
    return " ".join(words(rec["table"])) + " | " + " ".join(words(rec["column"]))


def sibling_text(rec: dict) -> str:
    return " ".join(w for s in rec["siblings"] for w in words(s))


def dense(rec: dict) -> list[float]:
    p = rec["profile"]
    onehot = [1.0 if norm_type(rec["sqltype"]) == t else 0.0 for t in SQL_TYPES]
    stats = [p[k] for k in STAT_NAMES]
    stats[STAT_NAMES.index("mean_len")] = math.log1p(p["mean_len"])
    sib = " ".join(rec["siblings"]).lower()
    return onehot + stats + [math.log10(max(rec["row_count"], 1)), float(rec["person_fk"]),
                             float(rec["expires_like"] or bool(re.search(r"expir|valid_until|ttl", sib)))]


DENSE_NAMES = [f"type:{t}" for t in SQL_TYPES] + [f"pattern:{k}" for k in STAT_NAMES] + ["ctx:log_rows", "ctx:person_fk", "ctx:expires_like"]


class FeatureBuilder:
    def __init__(self, name_dims: int = 64, sib_dims: int = 16, seed: int = 7):
        self.tfidf = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, sublinear_tf=True)
        self.name_svd = TruncatedSVD(name_dims, random_state=seed)
        self.bow = CountVectorizer(min_df=2)
        self.sib_svd = TruncatedSVD(sib_dims, random_state=seed)
        # whole-word presence keeps rare but decisive tokens ("vaccine", "currency") that the SVD would blur
        self.col_words = CountVectorizer(binary=True, min_df=3, analyzer=words)
        self.tab_words = CountVectorizer(binary=True, min_df=3, analyzer=words)

    def fit(self, recs: list[dict]) -> "FeatureBuilder":
        self.name_svd.fit(self.tfidf.fit_transform([name_text(r) for r in recs]))
        self.sib_svd.fit(self.bow.fit_transform([sibling_text(r) for r in recs]))
        self.col_words.fit([r["column"] for r in recs])
        self.tab_words.fit([r["table"] for r in recs])
        return self

    def transform(self, recs: list[dict]) -> np.ndarray:
        n = self.name_svd.transform(self.tfidf.transform([name_text(r) for r in recs]))
        s = self.sib_svd.transform(self.bow.transform([sibling_text(r) for r in recs]))
        cw = self.col_words.transform([r["column"] for r in recs]).toarray()
        tw = self.tab_words.transform([r["table"] for r in recs]).toarray()
        return np.hstack([n, s, cw, tw, np.array([dense(r) for r in recs])])

    def feature_names(self) -> list[str]:
        return ([f"name_svd{i}" for i in range(self.name_svd.n_components)] + [f"sib_svd{i}" for i in range(self.sib_svd.n_components)]
                + [f"col_word:{w}" for w in self.col_words.get_feature_names_out()] + [f"table_word:{w}" for w in self.tab_words.get_feature_names_out()] + DENSE_NAMES)
