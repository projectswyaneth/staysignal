# StaySignal — source content for the pitch deck

Everything in this file is a real, verified fact from the built project.
Nothing here is aspiration or filler. Use only these facts.

---

## 1. The competition

- IgnitX by Hutch, 2026.
- Track B, challenge 4.2.3 — "Silent Churn Signal".
- Team: [TEAM NAME], University of Sri Jayewardenepura.
- 10 minutes for the pitch, including any demo. Own laptop.
- Judged on: innovation 30%, business value 25%, technical 15%,
  AI and data 10%, UX 10%, presentation 10%.

## 2. The problem

- Prepaid customers do not complain before they leave. They go quiet.
- The gap between reloads stretches. Data use falls. They stop opening the app.
- No complaint is ever filed, so nothing triggers in any system.
- By the time the SIM is dead it is too late to keep them, and nobody knows why
  they went.
- In Sri Lanka a "quiet" customer often has not left at all — they moved their
  traffic to a second SIM. That is a Sri Lanka–specific behaviour worth naming.

## 3. The insight — the core argument of the whole pitch

Four different people go quiet for four different reasons:

1. Network problem — the signal keeps dropping in their area.
2. Bill shock — they were charged extra and got angry.
3. Package too big — they pay for 40GB and use 5GB.
4. Losing interest — nothing is wrong, they just drifted.

The industry response is one blanket discount. A customer in Jaffna whose signal
drops nine times a week takes the free data and leaves anyway, because the signal
is still bad. One discount cannot fix four different problems.

**We proved this with numbers (see section 7): blanket discounting is worse than
doing nothing at all.**

## 4. The solution — StaySignal, four steps

1. **Detect** — a trained model scores each customer 0–100 on the chance they go
   silent within 30 days.
2. **Diagnose** — the system names which of the four reasons it is.
3. **Act** — the offer is chosen to match that reason and written as an SMS in
   Sinhala, Tamil or English.
4. **Track** — the console counts customers kept and rupees protected.

## 5. What is actually built and working

- **Live web console**, deployed on Netlify, opens on any phone or laptop, no
  login. URL: [NETLIFY URL].
- **Trained model** — logistic regression, 11 features, shipped as model.json.
- **The model runs in the browser.** Click a customer and the score is computed
  live from the learned weights, including the per-feature reasons.
- **Scoring API** — FastAPI service with /score, /score/batch, /model, /health
  and auto-generated interactive docs at /docs.
- **Training pipeline** — data generator, training script, evaluation report and
  charts, all in the repository.

## 6. Model results — measured on a held-out test set

| Model | ROC AUC | PR AUC |
|---|---|---|
| Logistic regression (deployed) | **0.857** | 0.673 |
| Gradient boosting (benchmark) | 0.842 | 0.613 |

- Trained on 3,000 simulated customers, 18.7% churn rate.
- 5-fold cross-validation: 0.854 (+/- 0.018).
- At the chosen threshold of 0.67: catches **65%** of real leavers at **61%**
  precision.
- The explainable model **beat** the complex one. We benchmarked rather than
  assumed, and kept logistic regression because the challenge requires the system
  to explain its decisions.
- A score is literally a sum: intercept + each feature's weight × its value. The
  explanation is the model, not a separate estimate bolted on afterwards.
- The feature code is shared between training and the API (one file,
  ml/features.py) so the two can never drift apart. That failure is called
  training/serving skew and it is a common way a working model silently breaks.

## 7. The money argument — the strongest slide in the deck

A retention offer is not the cost of an SMS. It is free data or a package
downgrade: real margin, given away to everyone contacted, including the people
who were never going to leave.

Stated assumptions: the offer gives up 15% of that customer's revenue, we keep
35% of the leavers we contact, counted over 6 months.

| Strategy | Revenue lost on the test set |
|---|---|
| Contact nobody | Rs. 1,004,070 |
| Contact everybody (blanket discount) | Rs. 1,526,004 |
| **Contact who the model flags** | **Rs. 932,656** |

Blanket discounting loses more money than doing nothing. Targeting saves
Rs. 71,414 against doing nothing and Rs. 593,348 against blanket discounting.

We did not tune the threshold for accuracy. We tuned it for rupees.

## 8. The demo data — current figures

120 practice customers, generated with a different random seed from the training
data, so **the model has never seen them**.

- **26 of 120** are above the alert line.
- **Rs. 32,240** of revenue at risk per month.
- Reasons found: Losing interest 60, Package too big 32, Network problem 18,
  Bill shock 10.
- Worst towns this week: Kandy 5, Batticaloa 5, Matara 4, Jaffna 3.

## 9. The worked example — use this customer

Customer HUT100087, Jaffna, Value 15GB package, Rs. 990 a month.

- Risk score **99 / 100**.
- Reload gap: 7.9 days → 13.6 days (up 72%).
- Data use: 6.3GB → 3.8GB (down 40%).
- App opens: 32 → 15 (down 53%).
- Nine network drops last week. One complaint.
- Diagnosis: **network problem**.
- Action: apologise, give the repair status. Not a discount.

The API returns exactly the same score and the same reasons as the browser does.

## 10. The four messages — real, ready to send

All four exist in Sinhala, Tamil and English inside the system. English versions:

**Network problem**
> Dear Valued Customer, we are currently experiencing an unexpected service
> disruption due to a technical error. We sincerely apologize for the
> inconvenience. Our technical team is working to resolve the issue and services
> will be restored as quickly as possible. Thank you. – Hutch

**Bill shock**
> Dear Valued Customer, you spent an extra Rs. 793/- on data last month by
> exceeding your package limit. Switch to our "Unlimited" package to enjoy more
> data for the same amount. Reply YES to switch. – Hutch

**Package too big**
> Dear Valued Customer, you used only 3.3GB of your 15GB package last month.
> Switch to our "Lite 5GB" package and save Rs. 500/- monthly. Reply YES to
> switch. – Hutch

**Losing interest**
> Dear Valued Customer, a special offer to welcome you back. Enjoy an extra 5GB
> of Night Data completely free with your next reload. Reply YES to activate.
> – Hutch

Note the third one: we recommend the customer pays us **less**, because they stay.

## 11. What we are honest about

- The model is trained on **simulated** data, because the competition dataset had
  not been released when this was built. The pipeline is written so that only the
  input file changes when the real data arrives.
- The 15% offer cost and the 35% save rate are stated assumptions, not measured
  values. A proper A/B test would replace them.
- The four reasons are currently assigned by rules over the same features. With
  labelled outcomes per offer type, we would learn them instead.

Say these out loud. A judge who catches an unstated assumption stops believing
everything else.

## 12. What comes next

- Re-run everything on Hutch's dataset the day it arrives.
- The risk engine becomes a service reading Hutch's own data warehouse; offers go
  out through Hutch's own SMS gateway.
- Train on real churn history instead of simulated.
- Test which offers actually keep people, and let the model learn from the result.

## 13. Writing rules for the deck

- Short sentences. No sentence longer than about 15 words on a slide.
- Every claim carries a number or a name. "Revenue at risk" is weak.
  "Rs. 32,240 a month" is strong.
- Use real town names: Jaffna, Kandy, Batticaloa, Matara.
- Never write "leverage", "seamless", "robust", "cutting-edge", "empower",
  "revolutionise", "game-changing", "holistic", "synergy".
- Do not use a triple when a single will do.
- Maximum 25 words of body text per slide. The speaker says the rest.
- No sentence that would be true of any other project. If it could describe a
  food delivery app, delete it.

---

## 14. The business model — added detail

Full version: `docs/business-model.md`. Numbers from `ml/business_case.py`.

### Market context (cited, not assumed)

- Sri Lanka had **30.3 million** mobile connections in late 2025, about **130%**
  of the population, and the number **fell by 314,000 (1.0%) during 2025**.
- Hutch has roughly **3.6–3.8 million** subscribers, an estimated 10–12% share.
- Source: Operator Watch, June 2026.

Two consequences, and they are the business case:

1. In a shrinking market there are no new customers to win. Retention is the
   only growth channel left.
2. Penetration above 100% means multi-SIM is normal. So a quiet customer has
   often not left — they moved traffic to a second SIM. Still reachable, still
   winnable. That is the window we sell into.

### Unit economics

- **Rs. 95.22** revenue protected per customer over 6 months.
- **Rs. 15.87** per customer per month.
- **200 offers per 1,000 customers**, not 1,000.
- Of every 150 offers, **59** go to someone who was not leaving. That cost is
  already inside the Rs. 932,656. Do not hide it.
- Blanket discounting costs **Rs. 521,934 more than doing nothing.**

Scaling: Rs. 15.87 × 3.6 million ≈ **Rs. 57 million a month.** Arithmetic, not a
measurement. Our simulated customers average Rs. 1,288 a month, which is high
for prepaid — a real base spending half that protects half as much. Quote the
per-customer figure as fact and the total as a ceiling.

### Margin of safety — the answer when a judge attacks the assumptions

| Assumption | We assume | Break-even | Headroom |
|---|---|---|---|
| Save rate | 35% | **24.4%** | can fall 30% |
| Offer cost | 15% of revenue | **21.6%** | can rise 44% |

Across every save rate from 5% to 70%, contacting everybody loses more than
contacting nobody. That conclusion does not depend on our assumptions at all.

### Cost to run

Eleven multiplications, one sigmoid. No GPU, for training or scoring. A nightly
batch job on one ordinary server. The console scores in the browser, so the demo
costs nothing to serve. Marginal cost per extra customer scored is effectively
zero — the only real variable cost is the offer itself.

The complex model cost more and scored worse (0.842 against 0.857).

### The deliberate ARPU cut

One of the four messages recommends the customer pays **less** — a 5GB package
instead of an unused 15GB one, Rs. 500 a month cheaper.

> A customer paying Rs. 990 a month for three years beats one paying Rs. 1,490
> for one more month.

Lifetime value, not this month's ARPU. Hardest part of the pitch for a
competitor to copy, because it means giving up revenue on purpose.

### Operating model

- Engine reads Hutch's own warehouse. **Customer data never leaves Hutch.**
- Offers go through Hutch's existing SMS gateway. No new channel.
- Integration is one call: `POST /score/batch`, up to 5,000 customers.
- Phase 1: four weeks, one region, flagged customers split into treated and
  holdout. This replaces both assumptions with measured values.
- Phase 2: learn which offer works, instead of choosing it by rule.
- Phase 3: national and nightly, threshold re-tuned on real revenue.

### The strategic weakness — name it before a judge does

Hutch could build this. Eleven features and a logistic regression is not a moat.
What is hard to copy is the framing: four causes not one, blanket discounting
loses money, and a smaller package can be the right answer.

### Also honest about

Offer fatigue is not modelled — a production system needs a contact frequency
cap. Marketing SMS needs consent checking against a do-not-contact list, which
we have not built.
