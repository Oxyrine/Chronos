"""policy.yaml loader and table / store roll-up (spec 7.3)."""
import functools
import pathlib

import yaml

_PATH = pathlib.Path(__file__).parent / "policy.yaml"


@functools.lru_cache(maxsize=1)
def load_policy() -> dict:
    return yaml.safe_load(_PATH.read_text())


def years(category: str) -> float:
    return float(load_policy()["categories"][category]["years"])


def longer(cat_a: str, cat_b: str) -> str:
    """Whichever category has the longer policy period (ties keep a)."""
    return cat_b if years(cat_b) > years(cat_a) else cat_a


def rollup(predictions: list[dict]) -> dict:
    """table -> {"x": longest column period, "driving_column": that column, "category": its category}.

    A table's period is its longest column, with that column named (otp_codes inherits 10y from phone, not 1d from code).
    """
    out: dict[str, dict] = {}
    for p in predictions:
        y = p["policy_years"]
        cur = out.get(p["table"])
        if cur is None or y > cur["x"]:
            out[p["table"]] = {"x": y, "driving_column": p["column"], "category": p["category"]}
    return out


def store_period(table_periods: dict) -> float:
    return max((t["x"] for t in table_periods.values()), default=0.0)
