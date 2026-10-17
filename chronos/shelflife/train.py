"""Train on the synthetic corpus (train split), report validation / held-out / demo metrics, save the model. Run on the VM.

    python -m chronos.shelflife.train [data/generated/columns.jsonl] [out/shelflife_metrics.json]
"""
import json
import pathlib
import sys

from chronos.shelflife import model as M


def main(data="data/generated/columns.jsonl", out="out/shelflife_metrics.json") -> dict:
    by = M.load_records(data)
    mdl = M.CategoryModel().fit(by["train"])
    mdl.save()
    res = {"model_version": M.MODEL_VERSION, "backend": mdl.backend, "synthetic": True,
           "train_columns": len(by["train"]), **{split: M.evaluate(mdl, by[split]) for split in ("validation", "test", "demo") if split in by}}
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(out).write_text(json.dumps(res, indent=2))
    return res


def leave_one_domain_out(data="data/generated/columns.jsonl") -> dict:
    """Train on seven domains, test on the eighth, for all eight. Less sensitive to any one split than the fixed School hold-out."""
    by = M.load_records(data)
    allrecs = [r for split in ("train", "validation", "test") for r in by.get(split, [])]
    out = {}
    for dom in sorted({r["domain"] for r in allrecs}):
        m = M.CategoryModel().fit([r for r in allrecs if r["domain"] != dom])
        e = M.evaluate(m, [r for r in allrecs if r["domain"] == dom])
        out[dom] = {k: e[k] for k in ("n", "macro_f1", "under_protection_rate", "over_protection_rate")} | {"keyword_baseline": e["keyword_baseline"]}
    out["_mean"] = {k: round(sum(v[k] for d, v in out.items()) / len(out), 4) for k in ("macro_f1", "under_protection_rate", "over_protection_rate")}
    return out


if __name__ == "__main__":
    if sys.argv[1:2] == ["--lodo"]:
        for d, v in leave_one_domain_out().items():
            print(d, {k: v[k] for k in v if k != "keyword_baseline"})
        sys.exit()
    r = main(*sys.argv[1:3])
    for split in ("validation", "test", "demo"):
        if split in r:
            s = r[split]
            print(f"{split:10s} n={s['n']:5d} macroF1={s['macro_f1']:.3f} under={s['under_protection_rate']:.3f} over={s['over_protection_rate']:.3f} "
                  f"baseline F1={s['keyword_baseline']['macro_f1']:.3f} under={s['keyword_baseline']['under_protection_rate']:.3f}")
