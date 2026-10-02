# StaySignal — solution and technical document

**IgnitX by Hutch 2026 · Track B · Challenge 4.2.3 — Silent Churn Signal**
Team Falconyx · University of Sri Jayewardenepura
Repository: <https://github.com/projectswyaneth/staysignal>
Live prototype: <https://staysignalbyfalconyx.netlify.app>

> All data in this document is simulated. No Hutch API, credential, production
> system or customer record was used, in line with the hackathon guidelines.

---

## Contents

1. [Executive summary](#1-executive-summary)
2. [Problem statement](#2-problem-statement)
3. [Solution overview](#3-solution-overview)
4. [Data sources and integration](#4-data-sources-and-integration)
5. [Feature engineering](#5-feature-engineering)
6. [Model and evaluation](#6-model-and-evaluation)
7. [Business logic and policy layer](#7-business-logic-and-policy-layer)
8. [System architecture](#8-system-architecture)
9. [Prototype](#9-prototype)
10. [AI usage, cost and forecast assumptions](#10-ai-usage-cost-and-forecast-assumptions)
11. [Limitations and risks](#11-limitations-and-risks)
12. [Implementation plan](#12-implementation-plan)

---

## 1. Executive summary

Prepaid customers rarely complain before they leave. They go quiet — reloading
later, using less data, opening the app less — and by the time the revenue drop
is visible in a report, they are gone.

**StaySignal is a Customer Experience Management module for prepaid.** It detects
silent customer-experience failures, identifies the cause from network, usage,
billing and market data, and triggers the matching recovery action in the
customer's own language.

The commercial case rests on one comparison, measured on a held-out test set of
1,000 customers:

| Strategy | Revenue lost over 6 months |
|---|---|
| Contact nobody | Rs. 1,614,006 |
| Contact everybody — the blanket discount | Rs. 2,324,699 |
| **Contact who StaySignal flags** | **Rs. 1,517,559** |

A blanket discount is **worse than doing nothing**: it gives margin away to
customers who were never going to leave. Targeting beats it by Rs. 807,139 on
this test set. That is the argument for the project, and the rest of this
document exists to make it trustworthy rather than merely stated.

Three things distinguish the approach:

- **Everything is relative.** No customer, cell or week is judged in absolute
  terms. Each is compared to its own history, which is what lets the system tell
  a leaver from a traveller, a holiday from a decline, and a congested cell from
  an interfered one.
- **Flagged is not contacted.** A risk score and a decision to spend money are
  separate, and the second is governed by business rules Hutch can change without
  retraining anything.
- **No LLM, anywhere.** The deployed model is 24 weights. Scoring a million
  subscribers costs seconds of CPU and nothing per customer, so the whole base
  can be scored nightly rather than a sample monthly.

---

## 2. Problem statement

### The challenge

Identify prepaid customers who are drifting away *before* they stop reloading,
understand why, and act in a way that is worth more than it costs.

### Why it is hard

Four customers can look identical in the data — usage down, reloads down, app
opens down:

| | What is really happening | What a naive system does |
|---|---|---|
| On holiday for two weeks | Away, still active elsewhere | Sends a discount to a loyal customer |
| A national holiday | The whole base is quiet at once | Sends hundreds of thousands of discounts in one week |
| A sales rep | Always uses many towers, as he always has | Holds him back as "travelling" — permanently |
| Actually leaving | At home, and silent | Gets lost in the noise above |

Separating these four is the entire technical problem.

### The cost of getting it wrong

Both directions cost money, and they are not symmetrical in how visible they are.
A wasted offer is visible in the campaign budget. A customer silently suppressed
by a policy rule appears in no report at all — which is why the second failure
survived two review rounds in our own system before a panel found it.

---

## 3. Solution overview

Five stages.

**1 · Detect.** Every customer is scored 0–100 on the chance they go silent in
the next 30 days, from 24 features across six families.

**2 · Diagnose.** The same features name the most likely cause: network fault,
bill shock, a package that is too big, a package that is too *small*, losing
interest, or a competitor's offer. The package-too-small case is an upsell, not
a rescue — the same machinery finding revenue instead of protecting it.

**3 · Decide.** The alert threshold is tuned on *money*, not accuracy. Suppression
rules then decide whether to actually spend: travelling, seasonal and
recently-contacted customers are held back and shown in a separate queue rather
than silently dropped.

**4 · Act.** Each cause maps to a different action, written as an SMS in Sinhala,
Tamil or English. A customer on a degraded cell gets a repair update and the
fault becomes an RF work order — *a discount does not fix a dropped signal*.

**5 · Learn.** Every contact, outcome and suppression reason is written back, so
the save rate stops being an assumption and becomes a measurement.

### The organising idea

> Nothing is judged in absolute terms. A customer is compared to their own past.
> A cell is compared to its own past. A week is compared to what the whole base
> did that week. A traveller is compared to their own normal travel.

8 GB is a lot for one person and nothing for another. 55% congestion is routine
for a Colombo cell and alarming for a rural one. Twelve towers in a week is
alarming for an office worker and ordinary for a sales representative. Every
threshold that is absolute is a bug waiting to be found.

---

## 4. Data sources and integration

Confirmed with Hutch IT on 1 October 2026.

| Input | Hutch system | Status |
|---|---|---|
| Per-cell KPIs: drop rate, SINR, PRB utilisation, handover, outages | OSS / NMS | ✅ available |
| Subscriber-to-serving-cell history | CDR / xDR | ✅ available |
| Prepaid recharge and usage history | Data warehouse | ✅ available |
| Integration style | REST, Kafka or warehouse batch | ✅ any |
| CEM platform | exists, **data not exposed to third-party systems** | ⚠️ constraint |

### What the constraint means

A CEM that does not expose data to third parties rules out StaySignal as an
external service consuming CEM output — and we think Hutch is right to hold that
line. The design follows it:

- StaySignal **runs inside Hutch's boundary**. It is not a SaaS product.
- It **never reads from the CEM** — its inputs are OSS, CDR and the warehouse.
- **No subscriber record leaves to be scored.** No LLM, no external API, no
  vendor telemetry.
- The only external input is **district-level market data** with no personal
  information in it at all.

### The four canonical tables

Everything downstream consumes exactly four tables: `cells_weekly`,
`customers_weekly`, `customers_static` and `market_weekly`. Field-level
definitions, types and physical ranges are in
[`integrations/oss_adapter.py`](../integrations/oss_adapter.py), which is
executable and self-testing.

### Privacy

No message content. No packet inspection. No location beyond the cell the
network already records for billing. Mobility enters as weekly *counts* — how
many cells, how many districts — never as a movement trail, because a count is
enough to tell a traveller from a leaver and is the least invasive form of the
signal that still works.

Full specification: [integration-hutch.md](integration-hutch.md).

---

## 5. Feature engineering

24 features in six families. Three families exist because a judging panel asked a
question the previous version could not answer.

| Family | n | What it measures | Exists because |
|---|---|---|---|
| **A** · vs their own past | 4 | data, app opens, reloads, quota use against this customer's own baseline | the original idea |
| **B** · vs the whole base | 2 | did they fall *further than everyone else fell* that week | "what about a holiday?" |
| **C** · presence and mobility | 7 | home-tower share, districts seen, weeks since attach — and all of it against **their own** normal | "what if they are travelling?" and "what about a sales rep?" |
| **D** · network on their own cells | 6 | each serving cell against its own healthy level, including signal loss our own load cannot explain | "how do you *know* it is the network?" and "what about shared towers?" |
| **E** · commercial | 4 | overage, complaints, tenure, spend | bill shock and customer value |
| **F** · market context | 1 | competitor campaign pressure in their district | "what about Dialog's promotions?" |

### Three mechanisms worth describing precisely

**The population baseline (family B).** Instead of asking *did their usage fall*,
we ask *did it fall more than the median customer's fell that week*. If the whole
base dropped 30% during Avurudu and this customer dropped 30%, that is zero
signal. Seasonality cancels itself out — no holiday calendar, and it works for
holidays nobody told us about.

**Mobility against one's own normal (family C).** A field worker's home-tower
share is permanently low, because his sessions spread across a dozen towers. Any
absolute threshold therefore classifies him as permanently travelling. The fix is
ratios: towers visited ÷ towers normally visited, districts ÷ normal districts,
home share ÷ normal home share. A rep scores 1.0; an office worker on holiday
scores 5.5.

**Unexplained signal loss (family D).** We cannot see another operator's traffic.
We can see SINR loss our own PRB growth does not account for:

| PRB | SINR | Diagnosis | Fix |
|---|---|---|---|
| High | Low | our own congestion | add capacity |
| Flat | Low | something outside our traffic | RF planning, inter-operator coordination |
| Falling, with outages | Low | failing hardware | truck roll |

Implementation: [`ml/features.py`](../ml/features.py). The same module builds
features for training and for scoring, so the two cannot drift apart.

---

## 6. Model and evaluation

### Choice of model

Logistic regression, 24 weights. The challenge requires explainable decisions,
and a linear model makes that *exact* rather than approximate: risk is literally
the sum of each feature's weighted contribution, so the console can rank those
contributions and show an agent the real reason.

We benchmarked the cost of that choice rather than assuming it was free.

| Model | Features | ROC AUC | PR AUC |
|---|---|---|---|
| v1 — idea pitch | 4 | 0.825 | 0.499 |
| v2 — after the first technical panel | 18 | 0.864 | 0.593 |
| **v3 — deployed** | **24** | **0.864** | **0.607** |
| Gradient boosting benchmark | 24 | 0.840 | 0.556 |

5-fold cross-validation: 0.857 ± 0.008. The linear model **beats** gradient
boosting here, so explainability costs nothing.

**v2 → v3 barely moves AUC, and that is the expected result.** AUC measures
ranking across the whole base, while two of the three faults v3 fixes are
invisible to it: one never reaches the score at all (it is a suppression bug) and
one affects only the ~4% of the base a district promotion touches. A version that
improved AUC while leaving those in place would be worse.

### The four regression tests

Re-run on every training run and written to
[`reports/metrics.md`](../reports/metrics.md).

**Test 1 — the holiday test.** At an equal contact budget of 144: wasted offers
on travellers fall 12 → 0, real leavers caught rise 81 → 93. Travellers move
from the 64th risk percentile to the 26th.

**Test 2 — the sales rep test.** Absolute mobility rules labelled **88 of 88**
field workers "travelling", holding them back every week including when they were
genuinely leaving. Real leavers silently lost: **20 → 0**, while genuine
travellers are held slightly *more* reliably than before (71 → 74). Not a
trade-off — a change of reference point.

**Test 3 — the shared tower test.** Cells grouped by KPI fingerprint:

| Cell group | n | PRB change | SINR lost | Unexplained |
|---|---|---|---|---|
| Healthy | 121 | −0.3 pp | 0.0 dB | 0.1 dB |
| Our own congestion | 11 | +25.7 pp | 3.0 dB | **0.0 dB** |
| External interference | 7 | +0.6 pp | 4.5 dB | **4.1 dB** |
| Hardware / outage | 5 | −13.0 pp | 2.8 dB | 2.8 dB |

**Test 4 — the competitor test.** Capture of promotion-driven leavers rises
48% → 52% at equal budget; learned weight on market pressure +0.177.

### Operating point

Threshold 0.43 — flags 144 of 1,000. Recall 50%, precision 65%.

|  | Predicted stay | Predicted leave |
|---|---|---|
| **Actually stayed** | 764 | 51 |
| **Actually left** | 92 | **93** |

Of the 144 flagged, 7 are held back by policy and 137 are contacted.

---

## 7. Business logic and policy layer

### The threshold is tuned on money, not accuracy

The alert line is not the best F1 score. It is the point that loses the least
revenue, given that an offer gives up real margin and is wasted on anyone who was
never leaving. These are different questions with different answers, and only one
of them is commercially meaningful.

### Suppression — flagged is not contacted

| Rule | Why |
|---|---|
| Away from **their own** usual towers, still attaching | Wait until they are home; the dip is a trip |
| The whole base is down this week | A holiday, not churn |
| Contacted in the last 30 days | Offer fatigue — people stop reading |

Suppressed customers appear in a **separate visible queue**, never silently
dropped. That is a direct consequence of test 2: the failure we could not see was
the one that survived longest.

### Causes and actions

| Cause | Evidence | Action | Owner |
|---|---|---|---|
| Network fault | their cells degraded against their own baseline, usage fell in the same weeks | repair update, named tower | RF team |
| Bill shock | overage charged, reloads fell afterwards | explain the charge, offer better value | Retention |
| Plan too big | baseline quota use far below the plan size | offer a smaller, cheaper package | Retention |
| Plan too small | baseline quota use at the cap, reloading more than usual | **upsell** a larger package — revenue, not rescue | Retention |
| Losing interest | gradual fade with no other cause | re-engagement offer | Marketing |
| Competitor offer | district under campaign pressure, price-sensitive customer | competitive counter-offer | Retention |

Causes and suppression rules are **rules, not learned weights** — deliberately.
They encode business policy, and Hutch must be able to change retention policy
without retraining a model or explaining a weight to a regulator.

### Sensitivity

Offer cost and save rate are assumptions, so the business case reports break-even
points: targeting beats blanket discounting down to a **23.4% save rate** (we
assume 35%) and up to a **22.5% offer cost** (we assume 15%). Full grid:
[`reports/business-case.md`](../reports/business-case.md).

---

## 8. System architecture

![StaySignal architecture](architecture.png)

Six layers, all inside Hutch's boundary: source systems → adapter → features →
model → policy → action, with outcomes written back for the next retrain.

Nightly batch. The heavy step is one group-by per table, not the model. A
one-million-subscriber base is a single commodity VM with no GPU.

Editable source: [`architecture.html`](architecture.html).

---

## 9. Prototype

Live: <https://staysignalbyfalconyx.netlify.app>

A static console — no install, no login, no server. It shows the ranked queue,
the evidence behind each score (the model's actual contributions, computed in the
browser from the exported weights), the named tower where a network fault is the
cause, the suggested message in the customer's language, and the held-back queue
with the reason for each hold.

The console runs on a demo set generated with a **different random seed** from the
training data, so every score on screen is the model predicting on customers it
has never seen.

Reproduce everything in about a minute:

```bash
cd ml
pip install -r requirements.txt
python generate.py && python generate.py demo
python train.py && python business_case.py
```

---

## 10. AI usage, cost and forecast assumptions

**StaySignal makes no LLM call at runtime. Not once, for any customer.**

| Question | Answer |
|---|---|
| Model in production | logistic regression, 24 weights, 3 KB of JSON |
| Cost per scored customer | effectively zero — no tokens, no API, no per-call billing |
| Token forecast | not applicable; there is nothing to forecast |
| Infrastructure | one commodity VM, no GPU |
| Does customer data leave Hutch? | no |

AI tools (Claude, Anthropic) were used **during development** for code review,
drafting and critique, as permitted under section 15 of the delegates' booklet. No
AI chose a feature, a weight or a threshold. Full declaration, including how each
AI-assisted artefact was verified:
[ai-usage-declaration.md](ai-usage-declaration.md).

The commercial consequence of having no inference cost is not cosmetic: Hutch can
score the entire base nightly rather than a sample monthly. Churn signals are
weekly, so a monthly sample finds them after the customer has already gone.

---

## 11. Limitations and risks

Stated in full, with what would close each one, in
[limitations.md](limitations.md). The headline items:

- **The data is simulated.** Every number here must be re-run on Hutch extracts
  before anyone acts on it. We expect the numbers to move and the *ordering* of
  strategies to hold, because that ordering comes from the economics.
- **Offer cost and save rate are assumptions**, which is why break-even points are
  published rather than a single ROI figure.
- **Interference is inferred, not measured.** The feature says *our own load does
  not explain this* — a work order for the RF team, never an accusation against a
  named operator.
- **Market pressure needs an external feed**; without it the model degrades
  gracefully to its previous behaviour.
- **Customers with under ~17 weeks of history cannot be scored** and are excluded
  and counted, not guessed at.
- **No temporal model.** Sequence models are recorded as future work, and the
  pipeline is already shaped for them — the tables are weekly time series, not
  snapshots.

---

## 12. Implementation plan

Nine phases over eight months, from data access to handover, with a controlled
pilot carrying a holdout group at its centre — because that is the only way the
save rate stops being an assumption.

![Implementation plan](gantt.png)

Phase table, owners, milestones, dependencies and risks:
[implementation-plan.md](implementation-plan.md).

---

## Appendix — where to look in the repository

| What | Where |
|---|---|
| The thinking | [`ml/features.py`](../ml/features.py) |
| The claims, checked | [`reports/metrics.md`](../reports/metrics.md) |
| The economics, stress-tested | [`reports/business-case.md`](../reports/business-case.md) |
| The integration contract | [`integrations/oss_adapter.py`](../integrations/oss_adapter.py) |
| Panel questions and answers | [judge-questions.md](judge-questions.md) |

---

**Team Falconyx** — Yaneth De Alwis · Thamindu Nisal · Uchitha Samaranayake ·
Yohara Perera · Thuvini Mahagamage
University of Sri Jayewardenepura, Department of Electronics and Telecommunication
