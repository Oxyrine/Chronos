# Model card: Chronos column-category classifier

**Intended use.** Suggest what kind of data each column of a relational database holds (10 categories), so an explicit, approved policy table can assign how long it must stay confidential. A human can override any prediction. It does not set retention periods, does not decide legal obligations, and does not apply changes.

**Inputs.** Aggregate statistics computed inside the database container (pattern hit rates, mean length, uniqueness, null ratio), the column and table names, sibling column names, row count, and whether the table links to a person. No cell value is an input, and the optional Granite second opinion also sees no values.

**Training data.** Synthetic only. Eight generated domains (Hospital, Bank, HR, E-commerce, Government, Telecom, Humanitarian NGO, School; about 1,200 tables, seed 7), 50 column semantics, varied naming styles, 10% deliberately misleading names. Labels are a team-written mapping (`data/labels.yaml`); policy years come from `chronos/risk/policy.yaml` and are demonstration assumptions. St. Aster General is never trained on.

**Model.** Snap ML BoostingMachineClassifier on s390x; scikit-learn HistGradientBoosting where Snap ML is unavailable (the backend used is written into every metrics file). Decision rule: a longer-period category with probability >= 0.30 beats the top prediction; when the top probability is < 0.5, Granite's answer is kept only if its period is longer.

**Results.** Measured on IBM LinuxONE III (s390x, CPU-only, no NNPA accelerator). Numbers are from `out/metrics.json`:

| Split | n (columns) | Macro F1 | Accuracy | Under-Protection Rate | Baseline Keyword F1 |
|---|---|---|---|---|---|
| **Validation** | 1,418 | **0.9187** | 94.64% | 2.54% | 0.6549 |
| **Test (Held-out)** | 675 | **0.8207** | 93.48% | 4.15% | 0.5910 |
| **Demo (St. Aster)** | 36 | **0.9000** | 100.0% | 0.00% | 0.8381 |

Inference latency: **0.094 ms / column** using Snap ML (`category-1.0.0`). Misleading names subset: 71.4% F1 vs 4.9% keyword baseline.
*Caveat: All evaluations are on synthetic data with team-authored regulatory policies.*

**Known limits.**
- English column names only; relational databases only.
- Labels are policy assumptions; a different hospital policy needs different labels.
- One shared vocabulary of column semantics across domains: the held-out domain tests new tables and combinations, not new kinds of column. Genetic data appears only in the Hospital domain, so with Hospital held out under-protection rises to about 20%.
- The School hold-out was inspected once during development; treat that figure as optimistic and prefer the leave-one-domain-out mean.
- Salient features shown to users are readable cues, not model attributions.
- It cannot see a privileged administrator of the machine; this is data minimisation, not differential privacy.

**Human in the loop.** Overrides are logged; every remediation still passes the deterministic validator, sandbox verification and human approval.
