<div align="center">

<br>

# StaySignal

### Prepaid customers don't complain before they leave.<br>They go quiet.

<br>

**A Customer Experience Management module for prepaid.**

It detects silent experience failures, works out *why* from network, usage, billing
and market data, and triggers the one action that matches the cause — in the
customer's own language.

<br>

[![IgnitX by Hutch 2026](https://img.shields.io/badge/IgnitX_by_Hutch-2026_FINALIST-E8490B?style=for-the-badge&labelColor=12100E)](https://github.com/projectswyaneth/staysignal)
[![Track B · 4.2.3](https://img.shields.io/badge/Track_B-4.2.3_Silent_Churn_Signal-12100E?style=for-the-badge)](https://github.com/projectswyaneth/staysignal)

### [▶ Open the live console](https://staysignal.netlify.app)

<br>

![ROC AUC](https://img.shields.io/badge/ROC_AUC-0.864-E8490B?labelColor=12100E)
![PR AUC](https://img.shields.io/badge/PR_AUC-0.607-E8490B?labelColor=12100E)
![LLM cost](https://img.shields.io/badge/LLM_inference_cost-Rs._0-2E7D32?labelColor=12100E)
![Explainable](https://img.shields.io/badge/every_score-fully_decomposable-2E7D32?labelColor=12100E)
![Features](https://img.shields.io/badge/features-24-666?labelColor=12100E)
![Python](https://img.shields.io/badge/python-3.11-3776AB?labelColor=12100E)
![Licence](https://img.shields.io/badge/licence-MIT-999?labelColor=12100E)

<br>

**Team Falconyx** · University of Sri Jayewardenepura

</div>

---

<div align="center">

## The one number

</div>

A blanket retention discount is not the cautious choice.
On our held-out test set it is **worse than doing nothing at all.**

<div align="center">

| Strategy | Revenue lost over 6 months | |
|---|---:|---|
| Contact nobody | Rs. 1,614,006 | |
| Contact everybody — the blanket discount | Rs. 2,324,699 | 🔴 **worse** |
| **Contact who StaySignal flags** | **Rs. 1,517,559** | 🟢 **best** |

</div>

Targeting saves **Rs. 807,139 against blanket discounting** and Rs. 96,447 against
doing nothing. That gap is the entire argument for this project. Everything below
exists to make it trustworthy.

> [!NOTE]
> **All data in this repository is simulated.** No Hutch API, credential,
> production system or customer record was used. The pipeline is built so that
> exactly one adapter file changes when real extracts arrive.

---

<div align="center">

## Why a quiet customer is hard

</div>

Four people. **Identical in the data** — usage down, reloads down, app opens down.

| | What is really happening | What a naive system does |
|:--:|---|---|
| 🧳 | On holiday in Jaffna for two weeks | Sends a discount to a loyal customer |
| 🎊 | At home for a national holiday, like everyone | Sends 400,000 discounts in one week |
| 🚗 | A sales rep on twelve towers a week — *as always* | Holds him back as "travelling" **forever** |
| 🚪 | **Actually leaving** | Misses him in the noise |

Telling these four apart is the whole problem. StaySignal does it with a single
idea, applied everywhere:

> ### Nothing is judged in absolute terms.
>
> A **customer** is measured against their own past.
> A **cell** is measured against its own past.
> A **week** is measured against what the whole base did that week.
> A **traveller** is measured against their own normal travel.

8 GB is a collapse for one subscriber and a busy month for another. 55% congestion
is routine in Colombo and alarming in a village. Absolute numbers are not
comparable across subjects, so the system never uses one.

---

<div align="center">

## Architecture

</div>

![StaySignal architecture](docs/architecture.png)

Six layers, all **inside Hutch's boundary**: sources → adapter → features → model →
policy → action, with outcomes written back for the next retrain.
*Editable source: [`docs/architecture.html`](docs/architecture.html).*

---

<div align="center">

## The four tests that matter

</div>

Accuracy is not the headline. These are — because each one is a question a judging
panel actually asked, turned into a number that either moves or doesn't. All four
re-run on every training run and are written to
[`reports/metrics.md`](reports/metrics.md).

<table>
<tr>
<th width="22%">Test</th><th width="38%">The question behind it</th><th width="40%">Result</th>
</tr>

<tr><td><b>1 · The holiday test</b></td>
<td><i>"What happens when the customer is just on holiday?"</i></td>
<td>At an equal contact budget of 144, wasted offers fall <b>12 → 0</b> and real
leavers caught rise <b>81 → 93</b>. Travellers drop from the 64th risk percentile
to the 26th.</td></tr>

<tr><td><b>2 · The sales rep test</b></td>
<td><i>"A sales rep uses different towers every day. Did you consider that?"</i></td>
<td><b>We had not.</b> Absolute mobility thresholds labelled <b>88 of 88</b> field
workers "travelling" and held them back every week — including when they really
were leaving. Real leavers silently lost: <b>20 → 0</b>, with genuine travellers
held <i>more</i> reliably than before, not less.</td></tr>

<tr><td><b>3 · The shared tower test</b></td>
<td><i>"Those towers are shared with Mobitel and Dialog. Their congestion hurts
your customer. How would you identify that?"</i></td>
<td>We cannot see a rival's traffic — but we can see signal loss <i>our own load
does not explain</i>. Congestion cells: +25.7pp PRB, 3.0 dB lost,
<b>0.0 dB unexplained</b>. Interference cells: +0.6pp PRB, 4.5 dB lost,
<b>4.1 dB unexplained</b>.</td></tr>

<tr><td><b>4 · The competitor test</b></td>
<td><i>"Dialog's and Mobitel's promotions can hit Hutch churn hard."</i></td>
<td>Correct, and <b>no internal data can see it</b>. District-level market pressure
(MNP port-outs + public campaign calendar) raises capture of promotion-driven
leavers <b>48% → 52%</b>.</td></tr>
</table>

<details>
<summary><b>How the model got here — and an honest reading of the table</b></summary>

<br>

| Version | Features | Added because a panel asked | ROC AUC | PR AUC |
|---|:--:|---|:--:|:--:|
| v1 — idea pitch | 4 | — | 0.825 | 0.499 |
| v2 — first technical panel | 18 | network evidence, travel, seasonality | 0.864 | 0.593 |
| **v3 — finalist panel (deployed)** | **24** | own-mobility baseline, interference, competitor pressure | **0.864** | **0.607** |
| Gradient boosting benchmark | 24 | — | 0.840 | 0.556 |

5-fold cross-validation: **0.857 ± 0.008**.

**v2 → v3 barely moves AUC, and that is expected.** AUC measures ranking across the
whole base, while two of the three faults v3 fixes are invisible to it — one never
reaches the score at all (it is a suppression bug), and one touches only the 4% of
the base a rival's promotion reaches. A version that improved AUC while leaving
those in place would be worse, not better.

The linear model **beats** gradient boosting on this data, so the explainability the
challenge requires costs us nothing. That is measured, not assumed.

</details>

---

<div align="center">

## How it works · five steps

</div>

```
┌─ 1 DETECT ─────────────────────────────────────────────────────────┐
│  Logistic regression scores every customer 0–100 on the chance     │
│  they go silent in the next 30 days — 24 features, six families.   │
└────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─ 2 DIAGNOSE ───────────────────────────────────────────────────────┐
│  The same features name the cause: network fault · bill shock ·    │
│  package too big · package too SMALL · losing interest ·           │
│  competitor offer.  "Too small" makes money instead of saving it.  │
└────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─ 3 DECIDE ─────────────────────────────────────────────────────────┐
│  Threshold tuned on MONEY, not accuracy. Then suppression:         │
│  travelling · whole base fell too · contacted recently             │
│  → held back in a VISIBLE queue, never silently dropped.           │
└────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─ 4 ACT ────────────────────────────────────────────────────────────┐
│  One cause → one action. SMS in Sinhala, Tamil or English from     │
│  the account record. A faulty cell gets a repair update and an RF  │
│  work order — a discount does not fix a dropped signal.            │
└────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─ 5 LEARN ──────────────────────────────────────────────────────────┐
│  Every contact, outcome and suppression reason is written back,    │
│  so the save rate stops being an assumption and becomes a          │
│  measurement.                                                       │
└────────────────────────────────────────────────────────────────────┘
```

---

<div align="center">

## Reviewing this in three minutes?

</div>

| Open this | To see |
|---|---|
| **[The live console](https://staysignal.netlify.app)** | The whole thing working. Open **HUT100101** — data fell 49 GB → 21 GB and he scores **9**. |
| **[`ml/features.py`](ml/features.py)** | Where the thinking lives. 24 features, one definition, shared by training and scoring. |
| **[`reports/metrics.md`](reports/metrics.md)** | Where the claims are checked. Every number in this README, regenerated. |
| **[`docs/judge-questions.md`](docs/judge-questions.md)** | Every question a panel asked us, and what we changed because of it. |

---

<div align="center">

## Quickstart

</div>

```bash
git clone https://github.com/projectswyaneth/staysignal.git
cd staysignal/ml
pip install -r requirements.txt

python generate.py            # four simulated tables: cells, customers, static, market
python generate.py demo       # the smaller set the console runs on
python train.py               # trains v1/v2/v3 + benchmark, runs all four tests
python business_case.py       # break-even sensitivity on every assumption
python build_console_data.py  # rebuilds the console's data file

python ../integrations/oss_adapter.py   # validates the extracts, proves the SQL path
                                        # matches the file path, and proves it
                                        # rejects a broken extract
```

Everything regenerates deterministically from fixed seeds, so **every number in this
README can be reproduced on any machine in about a minute.** The console is a single
static page — open `frontend/index.html`. No build step, no server, no login.

---

<div align="center">

## What's in here

</div>

```
staysignal/
│
├── ml/
│   ├── features.py          ★ the 24 features — ONE definition, shared by training
│   │                          and scoring, so the two cannot drift apart
│   ├── generate.py            simulated OSS + CDR + warehouse + market tables
│   ├── train.py               trains v1/v2/v3 + GBM, runs the four tests
│   ├── business_case.py       break-even sensitivity on every assumption
│   └── build_console_data.py  builds frontend/data.js from the same features
│
├── integrations/
│   └── oss_adapter.py       the socket Hutch's real extracts plug into
│
├── frontend/                the console — static files, no install, no login
├── backend/                 optional scoring API (FastAPI)
├── data/                    generated tables (104,000 customer-weeks)
├── models/model.json        the deployed model: 24 weights, human-readable
├── reports/                 metrics, business case, learned weights
└── docs/                    architecture, integration spec, AI declaration,
                             limitations, implementation plan, business model,
                             judge Q&A
```

---

<div align="center">

## Integration with Hutch

</div>

Confirmed with Hutch IT on **1 October 2026**. Every source StaySignal needs
already exists.

| What we need | Hutch system | |
|---|---|:--:|
| Per-cell KPIs — drop rate, SINR, PRB utilisation, handover, outages | OSS / NMS | ✅ |
| Subscriber-to-serving-cell history | CDR / xDR | ✅ |
| Prepaid recharge and usage history | Data warehouse | ✅ |
| Integration style | REST, Kafka **or** warehouse batch | ✅ any |
| CEM platform | exists, but **data is not exposed to third-party systems** | ⚠️ |

That last row shaped the design, and we think it is the right constraint.
**StaySignal runs inside Hutch's boundary.** It reads from OSS, CDR and the
warehouse — never from the CEM — and no subscriber record is sent anywhere to be
scored. The only external input is district-level market data, which contains no
personal information at all.

[`integrations/oss_adapter.py`](integrations/oss_adapter.py) is the single file that
changes when real extracts arrive: a declarative mapping from Hutch's own field
names to the four canonical tables, with range validation and an explicit report of
anything missing. Field-level spec in
[`docs/integration-hutch.md`](docs/integration-hutch.md).

---

<div align="center">

## AI usage declaration

</div>

| Question | Answer |
|---|---|
| Does the product call an LLM at runtime? | **No.** Not once, for any customer. |
| What model runs in production? | Logistic regression — 24 multiplications and one sigmoid. |
| Inference cost per customer | **Effectively zero.** No tokens, no API, no per-call billing. |
| Token / cost forecast | **Not applicable.** There is nothing to forecast. |
| Where was AI used? | Development only — Claude (Anthropic) for code review, documentation drafting and critique of our own design, as permitted under section 15 of the delegates' booklet. **No AI chose a feature, a weight or a threshold.** |
| Can the team explain every decision? | Yes. That is the reason the model is linear and the policy layer is rules. |

Full declaration, including which files were AI-assisted and how each was verified:
[`docs/ai-usage-declaration.md`](docs/ai-usage-declaration.md).

---

<div align="center">

## Known limitations

</div>

We would rather state these than be asked about them.

- **The data is simulated.** Cell KPIs follow standard telecom definitions and
  realistic ranges, but they are generated. Every number here must be re-run on
  Hutch's own extracts before anyone acts on it.
- **Offer cost and save rate are assumptions**, not measurements. The business case
  therefore reports break-even points rather than a single ROI figure: targeting
  stays ahead of blanket discounting down to a **23.4% save rate** (we assume 35%)
  and up to a **22.5% offer cost** (we assume 15%).
- **Interference is inferred, not measured.** The feature says *our own load does
  not explain this signal loss.* That is a strong hint and a work order for the RF
  team — never proof that a specific neighbouring carrier is responsible.
- **Market pressure needs an external feed.** Without it the feature is zero and the
  model degrades to v2 behaviour on competitor-driven churn.
- **Customers with under ~17 weeks of history cannot be scored** — their own
  baseline window does not exist yet. They are excluded, not guessed at.
- **Causes and suppression rules are business rules, not learned.** Deliberately:
  Hutch must be able to change retention policy without retraining a model.

Expanded, with what we would do about each:
[`docs/limitations.md`](docs/limitations.md).

---

<div align="center">

## Submission checklist

</div>

| # | Required item | Where |
|:--:|---|---|
| 1 | Working prototype | [`frontend/`](frontend) · [live console](https://staysignal.netlify.app) |
| 2 | Source code repository | this repository |
| 3 | README | this file |
| 4 | Solution / technical document | [`docs/technical-document.md`](docs/technical-document.md) |
| 5 | Presentation deck | submitted via the IgnitX portal |
| 6 | Demo video (3–7 min) | submitted via the IgnitX portal |
| 7 | AI usage declaration | [`docs/ai-usage-declaration.md`](docs/ai-usage-declaration.md) |
| 8 | Architecture diagram | [`docs/architecture.png`](docs/architecture.png) |
| 9 | Known limitations | above, and [`docs/limitations.md`](docs/limitations.md) |
| 10 | Hutch integration demonstration | [`docs/integration-hutch.md`](docs/integration-hutch.md) · [`integrations/oss_adapter.py`](integrations/oss_adapter.py) |
| 11 | AI / token / forecast assumptions | [`docs/ai-usage-declaration.md`](docs/ai-usage-declaration.md) — no LLM, nothing to forecast |
| 12 | Implementation plan + Gantt chart | [`docs/implementation-plan.md`](docs/implementation-plan.md) |

Judging-panel questions and our answers, with the evidence for each:
[`docs/judge-questions.md`](docs/judge-questions.md).

---

<div align="center">

## Team Falconyx

**University of Sri Jayewardenepura**
Department of Electrical and Electronic Engineering

</div>

| | Role |
|---|---|
| **Yaneth De Alwis** | Team lead · **AI / ML** — feature engineering, model design, training pipeline |
| **Thamindu Nisal** | Data and integration |
| **Uchitha Samaranayake** | Front end and console |
| **Yohara Perera** | Business case and documentation |
| **Thuvini Mahagamage** | Research and presentation |

---

<div align="center">

## Licence

MIT — see [LICENSE](LICENSE).

Built for **IgnitX by Hutch 2026** · Track B · challenge 4.2.3 *Silent Churn Signal*

<br>

### [▶ Open the live console](https://staysignal.netlify.app)

</div>
