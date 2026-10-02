# AI usage declaration

IgnitX by Hutch 2026 · Track B 4.2.3 · Team Falconyx
Covers submission items **7** (AI usage declaration) and **11** (AI / token /
forecast assumptions).

---

## Part 1 — AI inside the product

**StaySignal does not call a large language model. Not once, for any customer,
at any point.**

| Question | Answer |
|---|---|
| Does the deployed product call an LLM at runtime? | **No.** |
| Does it call any external AI service? | **No.** Nothing leaves Hutch's network. |
| What model runs in production? | Logistic regression — 24 learned weights, in a 3 KB JSON file. |
| How is a customer scored? | 24 multiplications, 24 additions, one sigmoid. |
| Inference cost per customer | Effectively zero. No tokens, no API call, no per-request billing. |
| Cost to score a 1,000,000-subscriber base | Seconds of CPU on a machine Hutch already owns. |
| Token forecast | **Not applicable — there is nothing to forecast.** |
| Hosting requirement | One commodity VM. No GPU. |
| Does any customer data leave Hutch? | **No.** See [integration-hutch.md](integration-hutch.md). |

### Why this is a design decision, not a shortcut

The challenge requires the system to **explain its decisions**. A linear model
makes that exact rather than approximate: a customer's risk is literally the sum
of each feature's weighted contribution, so the console can rank those
contributions and show an agent precisely why the score is what it is. A deep
model would need a post-hoc approximation (SHAP, LIME) to produce a *guess* at
the same explanation.

We did not assume this was free. We benchmarked against gradient boosting on
identical data, and the linear model **scored higher** (ROC AUC 0.864 vs 0.840).
On this problem, explainability costs nothing. See
[`reports/metrics.md`](../reports/metrics.md).

We also considered temporal models — sequence models and attention over the
weekly series. They are a reasonable future direction and are recorded as such
in [limitations.md](limitations.md). They are not used here, because with 26
weekly observations per subscriber the relative features already capture the
shape of the decline, and nothing in the challenge is improved by a model nobody
in the room can audit.

### The commercial consequence

Most LLM-based retention tools cost money every time they look at a customer.
StaySignal's marginal cost per scored subscriber is **zero**, which means Hutch
can score the entire base nightly rather than a sampled subset monthly. That is
not a small difference: churn signals are weekly, and a monthly sample finds
them after the customer has already gone.

---

## Part 2 — AI used while building this

AI tools were used during development, as permitted under section 15 of the
delegates' booklet. We are stating exactly where, because a panel is entitled to
know which parts of the work the team can defend.

| Area | Tool | How it was used | How we verified it |
|---|---|---|---|
| Code review and refactoring | Claude (Anthropic) | Reviewing our pipeline, suggesting structure, catching bugs | Every script is run end to end; all reported numbers are reproduced from fixed seeds on team members' own machines |
| Data simulator | Claude | Drafting the generator that produces the four tables | Churn rates per hidden profile are inspected after every run; the traveller and mobility distributions are checked for the properties we need to test |
| Documentation | Claude | Drafting and tightening this and other documents | Read, edited and fact-checked against the code by the team; several drafts were rejected for over-claiming |
| Critique of our own design | Claude | Arguing against our choices — including pushing back on our instinct to add a neural network for its own sake | Judgement calls are the team's; the decision to stay linear is ours and we can defend it |
| Model, features, policy | **—** | **No AI chose a feature, a weight or a threshold.** Features come from the four judge questions; weights are fitted by scikit-learn; the threshold is chosen by the revenue optimisation in `train.py`. | — |

### What the team can explain

Every member can explain: why each feature is relative rather than absolute; why
the threshold is tuned on money rather than accuracy; why suppression is rules
rather than learned; and where each number in the README comes from. That was
the test we set ourselves, and it is the reason the system is simple enough to
pass it.

### Honest note on the dependency

A reviewer may reasonably ask how much of this we could rebuild from scratch.
The answer: the pipeline, yes — it is a few hundred lines and we have each run
and modified it. The polish on the documents and the front end took longer than
we could have managed alone in the time available. We would rather say that than
imply otherwise.

---

## Part 3 — Forecast assumptions

Since there is no inference cost, the only assumptions worth forecasting are
commercial ones. All three are **stated, not measured**, and the business case
reports break-even points rather than a single ROI number so that a reader can
substitute their own.

| Assumption | Our value | Break-even | Source |
|---|---|---|---|
| Share of contacted leavers actually retained | 35% | **23.4%** — below this, targeting stops beating doing nothing | Industry-typical retention-campaign response; must be measured with a holdout |
| Margin given up by a retention offer | 15% of that customer's revenue | **22.5%** — above this, targeting stops paying | Stated assumption |
| SMS cost | Rs. 5 | immaterial at this scale | Stated assumption |
| Revenue horizon | 6 months | — | Chosen to match a prepaid planning cycle |

Full sensitivity grid: [`reports/business-case.md`](../reports/business-case.md),
regenerated by `python ml/business_case.py`.

**The honest version:** we do not know Hutch's true save rate, and nobody can
until a pilot runs with a holdout group. What we can show is that the conclusion
survives a wide range of values for it — which is a stronger claim than a single
confident number would be.
