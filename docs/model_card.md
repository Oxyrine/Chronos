# Model card: Chronos column-category classifier

**Intended use.** Suggest what kind of data each column of a relational database holds (10 categories), so an explicit, approved policy table can assign how long it must stay confidential. A human can override any prediction. It does not set retention periods, does not decide legal obligations, and does not apply changes.

**Inputs.** Aggregate statistics computed inside the database container (pattern hit rates, mean length, uniqueness, null ratio), the column and table names, sibling column names, row count, and whether the table links to a person. No cell value is an input, and the optional Granite second opinion also sees no values.

**Training data.** Synthetic only. Eight generated domains (Hospital, Bank, HR, E-commerce, Government, Telecom, Humanitarian NGO, School; about 1,200 tables, seed 7), 50 column semantics, varied naming styles, 10% deliberately misleading names. Labels are a team-written mapping (`data/labels.yaml`); policy years come from `chronos/risk/policy.yaml` and are demonstration assumptions. St. Aster General is never trained on.

**Model.** Snap ML BoostingMachineClassifier on s390x; scikit-learn HistGradientBoosting where Snap ML is unavailable (the backend used is written into every metrics file). Decision rule: a longer-period category with probability >= 0.30 beats the top prediction; when the top probability is < 0.5, Granite's answer is kept only if its period is longer.

**Results.** `out/metrics.json` is the only source for numbers. They measure agreement with our own labels on generated data, not accuracy against real hospital obligations. Current laptop run: see `docs/HANDOFF_B.md`.

**Known limits.**
- English column names only; relational databases only.
- Labels are policy assumptions; a different hospital policy needs different labels.
- One shared vocabulary of column semantics across domains: the held-out domain tests new tables and combinations, not new kinds of column. Genetic data appears only in the Hospital domain, so with Hospital held out under-protection rises to about 20%.
- The School hold-out was inspected once during development; treat that figure as optimistic and prefer the leave-one-domain-out mean.
- Salient features shown to users are readable cues, not model attributions.
- It cannot see a privileged administrator of the machine; this is data minimisation, not differential privacy.

**Human in the loop.** Overrides are logged; every remediation still passes the deterministic validator, sandbox verification and human approval.
