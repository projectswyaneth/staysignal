# Predictive Model Disclosure

**StaySignal · Team Falconyx · IgnitX by Hutch 2026**

Answering sections **6.1–6.6** of the Final Submission Guidelines. StaySignal is a
risk-scoring solution, so **§6.3 Forecasting & Predictive Model Disclosure** applies
directly and is answered in full below.

---

## 6.1 · AI / LLM disclosure

| Field | Answer |
|---|---|
| **AI / LLM provider** | **None.** No LLM or generative model is called at runtime, for any customer, ever. |
| **Model name & version** | Not applicable. The deployed model is a logistic regression fitted by scikit-learn ≥ 1.4. |
| **Purpose of using an LLM** | Not applicable — none is used. |
| **LLM calls per customer journey** | **0** |
| **Average input tokens per request** | **0** |
| **Average output tokens per request** | **0** |
| **Average total tokens per request** | **0** |
| **RAG / external knowledge sources** | **None.** No vector store, no retrieval, no knowledge base. |
| **Prompting approach** | Not applicable. There are no prompts anywhere in the product. |
| **AI-generated vs rule-based** | **Learned:** the risk score only — 24 weights fitted from labelled data. **Rule-based:** cause diagnosis, suppression policy, action selection, message text, team routing. The boundary is deliberate and is described in §6.3.9. |
| **Fallback mechanism** | There is no AI service to be unavailable. If the nightly scoring batch fails, the previous night's queue remains valid and the failure is logged. No customer-facing degradation. Full behaviour in §6.3.10. |
| **Known limitations** | No hallucination surface — the model emits a probability, not text, and all customer-facing copy is fixed templates written and reviewed by the team. The real limitations are data-related and are listed in §6.3.11 and in [`limitations.md`](limitations.md). |

### Why no LLM — measured, not assumed

We benchmarked the alternative rather than asserting a preference.
`HistGradientBoostingClassifier` was trained on **identical data, identical features
and an identical split**:

| Model | ROC AUC | PR AUC |
|---|---|---|
| **Logistic regression (deployed)** | **0.864** | **0.607** |
| Gradient boosting benchmark | 0.840 | 0.556 |

The simple, fully explainable model scored higher. Structured weekly telecom
aggregates are precisely the shape of problem linear models handle well. An LLM
would add per-customer cost, latency, an external dependency and a hallucination
surface — and, on this evidence, would not score better.

**Where a language model genuinely would add value** is free-text call-centre
complaint notes, which no numeric feature in our set captures. That is a sensible
phase-2 addition contributing *one additional feature* to the same model. It is not
a replacement for the scoring layer.

---

## 6.2 · Token usage and scalability

| Measure | Value |
|---|---|
| Tokens per customer | **0** |
| Tokens per day at 1,000,000 subscribers | **0** |
| Token cost per month | **Rs. 0** |
| Operations per customer scored | 24 multiplications, 24 additions, one sigmoid |
| Scoring cost, 1,000,000 subscribers | **under one second of CPU**, estimated from the operation count |
| Hardware required | One commodity VM. **No GPU.** |

The heavy step in the nightly job is one group-by per source table, not the model.

**This is not a cosmetic saving.** Zero per-customer inference cost is what makes it
economically sensible to score the *entire* base *nightly* rather than a sample
monthly. Churn signals are weekly; a monthly sample finds a customer after they have
already gone.

---

## 6.3 · Forecasting and predictive model disclosure

### 6.3.1 What is predicted

The probability that a given prepaid subscriber **goes silent within the next 30
days** — that is, produces no revenue-generating activity in that window.

Output: a single probability in [0, 1], presented to users as a 0–100 risk score.

### 6.3.2 Model type and architecture

**Binary logistic regression.** 24 input features, 24 coefficients, one intercept,
one sigmoid link.

```
z     = intercept + Σ (wᵢ × xᵢ)      for i = 1..24
risk  = 1 / (1 + e^(−z))
```

Features are standardised (mean 0, unit variance) using statistics computed on the
training set and stored in `models/model.json`, so serving applies exactly the
training-time transform.

No ensembling, no stacking, no hidden layers. The complete deployed model — all 24
weights, the intercept, the scaler statistics and the threshold — is a single
human-readable JSON file of under 4 KB.

### 6.3.3 Input data and feature construction

Four tables (see [`technical-document.md`](technical-document.md) §4):

| Table | Grain | Production source |
|---|---|---|
| Customer weekly behaviour | customer × week | CDR/xDR + prepaid data warehouse |
| Customer static attributes | customer | Prepaid warehouse / CRM |
| Cell weekly KPIs | cell × week | OSS / NMS |
| Market weekly pressure | district × week | MNP port-out counts + public campaign calendar |

All 24 features are defined once, in `ml/features.py`, which is imported by the
training script, the scoring API and the console data builder alike. **A second
implementation would permit training/serving skew** — a silent and common failure
in deployed models — so there is exactly one definition.

**Every feature is a ratio or a delta. None is an absolute level.** The four
reference frames are: the customer's own history, the cell's own history, the
population baseline for that week, and the customer's own usual mobility.

### 6.3.4 Training data

| | |
|---|---|
| Customers | 4,000 |
| Observation window | 26 weeks |
| Customer-weeks | 104,000 |
| Cells | 144 across 12 districts |
| Positive class rate | **18.5%** |
| Provenance | **Simulated** — generated by `ml/generate.py` with a fixed seed |

The competition released no dataset and no Hutch production data, credentials or
integration environment were available to any team. Cell KPIs follow standard
telecom definitions and realistic operating ranges, but the values are generated.

Every figure in this document must be re-measured on Hutch's own extracts before
any operational decision is taken on it.

### 6.3.5 Validation approach

- **Held-out test set** of 1,000 customers the model never sees during fitting
- **Stratified 5-fold cross-validation** on the training portion
- **Demonstration set** of 150 customers generated with a *different random seed*,
  used by the console — so the prototype is not showing customers from training

Class stratification is applied to every split because the positive class is a
minority.

### 6.3.6 Metrics

| Metric | Value | What it means |
|---|---|---|
| **ROC AUC** | **0.864** | Given one real leaver and one real stayer, the model ranks the leaver higher 86.4% of the time |
| **PR AUC** | **0.607** | Precision–recall area. A random model scores ≈ 0.185 at this base rate |
| **5-fold CV** | **0.857 ± 0.008** | The small spread indicates a stable fit, not a favourable split |
| **Precision at threshold** | **65%** | 93 real leavers among 144 flagged |
| **Recall at threshold** | **50%** | 93 caught of the 185 who left |

Confusion matrix on the held-out set:

```
                  Predicted stay    Predicted leave
Actually stayed         764                51
Actually left            92                93
```

**Accuracy is deliberately not reported as a headline.** At an 18.5% base rate,
predicting "nobody leaves" yields 81.5% accuracy while being operationally useless.

### 6.3.7 Baseline comparison

| Model | Features | ROC AUC | PR AUC |
|---|---|---|---|
| v1 — behaviour only | 4 | 0.825 | 0.499 |
| v2 — plus network, travel, seasonality | 18 | 0.864 | 0.593 |
| **v3 — deployed** | **24** | **0.864** | **0.607** |
| Gradient boosting benchmark | 24 | 0.840 | 0.556 |

**On v2 → v3:** ROC AUC is unchanged and this is expected rather than
disappointing. ROC AUC measures ranking across the whole population, while two of
the three faults v3 corrects are structurally invisible to it — one is a
*suppression* defect that never reaches the score at all, and one affects only the
~4% of the base a competitor promotion reaches. PR AUC, which is more sensitive to
the minority class, does improve (0.593 → 0.607). A version that raised ROC AUC
while leaving 20 real leavers silently suppressed would be a worse system.

### 6.3.8 Decision threshold

**0.43**, and it is computed rather than chosen.

`ml/train.py` evaluates every candidate threshold from 0.05 to 0.95 in steps of
0.01. For each, it computes the total revenue outcome:

```
missed  = revenue lost on leavers not flagged
caught  = revenue still lost on flagged leavers not saved (1 − save rate)
offers  = margin given away on every customer flagged, leaver or not
```

The threshold retained is the one that **loses the least revenue** — explicitly not
the one maximising F1 or accuracy, because those treat a missed leaver and a wasted
offer as equally costly, which they are not.

The threshold is recomputed at each monthly retrain and is held fixed between
retrains. A threshold that moved nightly would flag a customer on Monday, not on
Tuesday and again on Wednesday with nothing about them having changed, which would
make the work queue untrustworthy.

**Stated assumptions in this calculation:** offer cost 15% of that customer's
revenue; save rate 35% of contacted leavers; SMS cost Rs. 5; horizon 6 months. All
four are assumptions, not measurements. Break-even sensitivity on each is in
[`../reports/business-case.md`](../reports/business-case.md).

### 6.3.9 Learned versus rule-based — the exact boundary

| Component | Learned or rules | Why |
|---|---|---|
| Risk score | **Learned** | 24 weights fitted by maximum likelihood |
| Decision threshold | **Computed** | Revenue optimisation, not a learned parameter |
| Cause diagnosis | **Rules** | Policy must change without retraining |
| Suppression (travel, seasonal, fatigue) | **Rules** | Same — these are business decisions |
| Action and offer selection | **Rules** | Marketing owns the offer catalogue |
| Message text | **Fixed templates** | Written and reviewed by the team; no generation |
| Team routing | **Rules** | Organisational, not statistical |

This boundary is a deliberate architectural decision. If Hutch's retention policy
changes — a different win-back offer, a different fatigue window, a new cause
category — that is a configuration change. It does not require retraining a model,
revalidating it, or involving a data scientist.

### 6.3.10 Handling of incorrect and low-confidence outputs

The guidelines ask specifically how incorrect or low-confidence outputs are
handled. Six mechanisms, all implemented:

**1 · Insufficient history → excluded, not guessed.**
A customer needs roughly 17 weeks of history for their own baseline window to
exist. Below that they are **excluded from scoring entirely** and reported as
excluded. The system does not substitute a population average and present it as a
personal score.

**2 · Below threshold → no action at all.**
A score beneath the revenue-optimal line produces no contact, no offer and no cost.
The default behaviour of the system is to do nothing.

**3 · Suppression overrides a high score.**
Three rules can hold back a customer the model scored highly: travelling (away from
usual towers but still attaching), seasonal (the whole base fell and this customer
fell no further than the base did), and contact fatigue (contacted within 30 days).
A confident score is not sufficient grounds for contact.

**4 · Suppressions are visible, never silent.**
Every held-back customer appears in a dedicated queue with the reason displayed.
This is not cosmetic: the mobility defect described in
[`judge-questions.md`](judge-questions.md) remained undetected precisely because
nothing surfaced suppressed customers. A system that conceals its own suppressions
cannot be audited or debugged.

**5 · Ambiguous cause → the lowest-cost action.**
Where no specific cause is identifiable from the features, the case falls back to
"Losing interest", whose action is the cheapest in the catalogue. The system does
not guess at an expensive remedy on weak evidence.

**6 · Impossible recommendation → reported as a product gap.**
Where the recommended plan equals the customer's current plan — a customer already
on the largest package who still exhausts it — the system does **not** emit a
nonsensical "switch to the plan you already have". It reports **"demand above the
catalogue"** to the product team. An out-of-range recommendation is surfaced as a
finding rather than issued as an instruction.

**Confidence is intrinsic.** The model emits a calibrated probability, so every
score carries its own confidence. A score of 0.44 and a score of 0.91 are both above
the line, but the console ranks by score and the business case weights by expected
value, so marginal cases are worked last.

**What a production deployment should add, and we have not built:** monitoring of
the score distribution and per-feature distributions between retrains, with an alert
when either shifts materially. We have specified this; it is not implemented.

### 6.3.11 Known biases and limitations of the model

1. **Simulated training data.** Definitions and ranges are realistic; the values are
   generated. Nothing here is validated on real subscriber behaviour.

2. **Class imbalance, and in an unusual direction.** Our simulated base rate of
   18.5% is *higher* than a typical real monthly prepaid churn rate. The threshold
   is re-optimised on the operator's own base rather than carried over, because the
   optimal operating point depends on the base rate.

3. **Collinearity between `cell_sinr_delta` and `cell_interference`.** Interference
   is derived from SINR delta, so the two share information and the fit distributes
   the effect between them — `cell_interference` carries a negative coefficient
   (−0.109) while `cell_sinr_delta` carries +0.429. The *net* effect on an
   interference-affected cell remains strongly positive and the ranking is correct,
   but the individual coefficients are not independently interpretable. Ridge
   regularisation or orthogonalising the derived feature would resolve this and is
   recommended before production.

4. **Interference is inferred, never measured.** The feature states that our own
   load does not account for the observed signal loss. That is a strong indication
   and a legitimate RF work order. It is **not** evidence that a specific
   neighbouring operator is responsible, and must never be presented as such.

5. **Market pressure requires an external feed.** Without MNP port-out data the
   feature reads zero and the model degrades to v2 behaviour on competitor-driven
   churn. The remainder continues to function.

6. **Survivorship in the labels.** Customers who left before the observation window
   opened are absent from the training data by construction.

7. **No causal claim.** The model identifies association, not causation. A customer
   on a degrading cell is at elevated risk; we do not claim the cell *caused* the
   departure, only that the association is strong enough to act on and that fixing
   the cell is independently worthwhile.

### 6.3.12 Retraining and monitoring

| | |
|---|---|
| **Scoring** | Nightly. Loads saved weights and threshold. Changes nothing. |
| **Retraining** | Monthly. Weights refitted, **threshold recomputed**, all four regression tests re-run. |
| **Trigger for an unscheduled retrain** | A material shift in the score distribution, or a change to the offer economics |
| **Regression gate** | The four tests in `ml/train.py` run on every training run and are written to `reports/metrics.md`. A regression cannot be committed unnoticed. |

Scoring is nightly while the underlying evidence is weekly, by design: features are
weekly aggregates, so a day-to-day score would largely track noise — which day of
the week it is, whether the subscriber was on wifi. Nightly scoring over weekly
evidence surfaces a genuine change within a day or two of it becoming real, without
reacting to a quiet Tuesday.

---

## 6.4 · Assumptions and simulated values

Every figure produced by this project carries one of five labels. The complete
labelled inventory is in [`../reports/metrics.md`](../reports/metrics.md) and
[`../reports/business-case.md`](../reports/business-case.md).

| Label | Meaning | Examples |
|---|---|---|
| **SIMULATED** | Generated by `ml/generate.py` | 4,000 customers, 144 cells, 18.5% churn rate |
| **MEASURED** | Computed by code from simulated data; exactly reproducible | ROC AUC 0.864, threshold 0.43, all four test results |
| **ASSUMED** | A value we chose and stated | Offer cost 15%, save rate 35%, SMS Rs. 5, fatigue 30 days, 0.22 dB per PRB point |
| **CONFIRMED** | Stated to us by Hutch IT on 1 October 2026 | OSS/NMS, CDR/xDR and warehouse availability; integration options; the CEM constraint |
| **EXTRAPOLATED** | Arithmetic applied beyond our data | Rs. 58 million/month at a 3.6 million base |

---

## 6.5 · Business impact and forecast claims

**No figure in this submission is a confirmed Hutch production result.** Nothing has
been measured on Hutch data, because no Hutch data was available.

The headline commercial findings, with their labels:

| Finding | Label |
|---|---|
| Blanket discounting loses Rs. 2,324,699 against Rs. 1,614,006 for doing nothing | **MEASURED on SIMULATED data under ASSUMED parameters** |
| Targeting loses Rs. 1,517,559 — Rs. 807,139 better than blanket discounting | **MEASURED on SIMULATED data under ASSUMED parameters** |
| Break-even save rate 23.4%; break-even offer cost 22.5% | **MEASURED given the stated assumptions** |
| Rs. 16.07 protected per customer per month | **MEASURED on SIMULATED data** |
| ≈ Rs. 58 million per month at a 3.6 million base | **EXTRAPOLATED** — arithmetic, not a measurement, and conditional on Hutch's churn rate resembling our simulated 18.5% |

We make **no percentage claim** of churn reduction or revenue increase. The business
case deliberately reports **break-even points rather than a single ROI figure**,
because the two parameters carrying the case — offer cost and save rate — are
assumptions. Both become measurements after a four-week controlled holdout, which
requires no new technology.

The one finding that does **not** depend on either assumption, and is therefore the
most robust statement in this submission:

> **Contacting everybody loses more than contacting nobody — at every save rate we
> tested, from 5% to 70%.**

---

## 6.6 · AI cost and commercial feasibility

| Item | Cost |
|---|---|
| LLM / generative AI API | **Rs. 0** — none used |
| GPU compute | **Rs. 0** — none required |
| Per-customer inference | **Rs. 0** |
| Training compute | Minutes of CPU, monthly |
| Serving infrastructure | One commodity VM for a 1,000,000-subscriber base |
| SMS delivery | Existing Hutch platform — not a new cost of this system |

The only variable operating cost at scale is the **offer margin** given away, which
is the quantity the threshold optimises and which is already subtracted from every
revenue figure reported above.

---

## Development-time AI usage

Distinct from runtime, and declared in full in
[`ai-usage-declaration.md`](ai-usage-declaration.md).

**Claude (Anthropic)** was used during development for code review, documentation
drafting and critique of our own design, as permitted under section 15 of the
delegates' booklet.

**No AI system selected a feature, fitted a weight or set a threshold.** Every
feature was specified by the team from telecom reasoning; the weights are fitted by
scikit-learn; the threshold is produced by our own revenue optimiser. The team can
explain every file in the repository and remains responsible for the correctness,
security and originality of the submission.
