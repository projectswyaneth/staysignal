# StaySignal — the business model

Every figure in sections 3, 5 and 6 comes from the deployed model's own output
on the 750-customer held-out test set, re-costed by `ml/business_case.py`.
The market figures in section 2 are cited. Everything that is an assumption is
labelled as one.

---

## 1. What kind of business model this is

StaySignal is not a product sold to the public. It is an internal decision
system for a mobile operator. So the business model has two layers, and they
should not be confused with each other:

**Layer 1 — the value case for Hutch.** Why switching this on makes Hutch money.
This is the layer the competition is judging, and it is the layer we have
measured.

**Layer 2 — the commercial model, if this became a venture.** How a team like
ours would charge for it. This is the layer we can reason about but have not
tested, and we say so.

Most retention pitches only do Layer 1 and call it a business model. Most
student pitches only do Layer 2 and have no numbers. We separate them.

---

## 2. Why retention, and why now

Two facts about the Sri Lankan market decide the whole business case.

**The market is full.** There were 30.3 million mobile connections in Sri Lanka
in late 2025 — about 130% of the population — and the number **fell by 314,000,
or 1.0%, during 2025.** Hutch has roughly 3.6–3.8 million subscribers, an
estimated 10–12% share.

The consequence is not subtle. In a market that is shrinking, an operator cannot
grow by finding new people, because there are no new people. Every subscriber
gained is a subscriber taken from a competitor or kept from leaving. Retention
stops being a cost centre and becomes the only available growth channel.

**Penetration above 100% means multi-SIM is normal.** 130% penetration is not
130% of people owning a phone — it is the same people holding more than one SIM.
This matters because it changes what "going quiet" means. A quiet prepaid
customer in Sri Lanka has often not left at all; they have moved their traffic
to a second SIM they already own. They are still reachable, still holding the
SIM, and still winnable. A dead-SIM report would have written them off.

That is the window StaySignal sells into: the period after a customer has
started leaving and before they have finished.

---

## 3. Unit economics

Measured on 750 held-out customers, 140 of whom actually left (18.7%), revenue
counted six months ahead.

| Measure | Value |
|---|---|
| Revenue protected per customer, 6 months | **Rs. 96.45** |
| Revenue protected per customer per month | **Rs. 16.07** |
| Offers sent per 1,000 customers | 144 |
| Of every 144 offers, sent to someone who was not leaving | 51 |

The three strategies, side by side:

| Strategy | Revenue lost | Against doing nothing |
|---|---|---|
| Contact nobody | Rs. 1,614,006 | — |
| Contact everybody (blanket discount) | Rs. 2,324,699 | **Rs. 710,693 worse** |
| **Contact who the model flags** | **Rs. 1,517,559** | **Rs. 96,447 better** |

Two things to notice.

The **51 wasted offers out of 144** are not an embarrassment to be hidden. They
are the price of a 65%-precise model, they are already subtracted inside the
Rs. 1,517,559, and they are the reason the threshold sits where it does rather
than lower. Any pitch that claims no wasted offers has not done the arithmetic.

**Blanket discounting is worse than doing nothing.** Contacting everybody costs
Rs. 710,693 more than sitting on your hands, because the discount goes to the
81% who were never leaving. This is the single most useful finding in the
project, and it is a business finding, not a technical one.

### Scaling the case

Rs. 16.07 per customer per month, applied to a 3.6 million prepaid base, is
roughly **Rs. 58 million a month**.

That number is arithmetic, not a measurement, and it is honest only with its
conditions attached:

- It assumes Hutch's real monthly quiet-rate resembles our simulated 18.7%. If
  the real rate is half that, halve the figure.
- **Our simulated customers spend an average of Rs. 1,288 a month.** That is
  high for Sri Lankan prepaid. Since the whole calculation is proportional to
  revenue, a real prepaid base spending half that protects half as much. This is
  the caveat most likely to matter, so say it first.
- It assumes the whole base is prepaid, which it is not.

State it as a ceiling, never as a forecast. The per-customer figure is the
defensible unit; the total is whatever the real base turns out to be.

---

## 4. The cost side

This is where the model choice becomes a business decision rather than a
technical preference.

A logistic regression score is eleven multiplications, one addition and one
sigmoid. That is the entire computation. Consequences:

- **No GPU, ever.** Not for training, not for scoring.
- Scoring the whole base is a nightly batch job on one ordinary server.
- The console scores customers **in the browser**, so a demo costs nothing to
  serve and cannot be broken by a sleeping server.
- The marginal cost of scoring one more customer is effectively zero.

So the cost structure is almost entirely fixed, and the fixed part is small. The
only meaningful variable cost is the offer itself — which means the business
case cannot be spoiled by infrastructure cost at any scale. A deep learning
approach would have added inference cost, hosting cost and a monitoring burden
in exchange for a model that scored **worse** (ROC AUC 0.842 against 0.857) and
could not explain itself.

We did not choose the simple model to save effort. We chose it, benchmarked
against the complex one, because it wins on accuracy, on explainability and on
cost at the same time.

---

## 5. Margin of safety — how wrong can we be?

Two assumptions carry the whole case: that a retention offer costs 15% of the
customer's revenue, and that we keep 35% of the leavers we contact. A judge is
right to press on both. So we measured how far they can move before targeting
stops paying.

| Assumption | We assume | Break-even | Headroom |
|---|---|---|---|
| Save rate (leavers we keep) | 35% | **24.4%** | can fall 30% and still pay |
| Offer cost (share of revenue given up) | 15% | **21.6%** | can rise 44% and still pay |

Read the first row carefully: we could be keeping only a quarter of the people
we contact — well below what retention teams typically report — and targeting
would still beat doing nothing.

And across the **entire** range we tested, from a 5% save rate to a 70% one,
contacting everybody loses more money than contacting nobody. Blanket
discounting does not break even until the save rate reaches **about 87%** — and
no retention programme keeps 87% of the people it contacts.

That conclusion does not depend on our assumptions at all. It is the one claim
in the pitch we can make without hedging.

Full tables: `reports/business-case.md`.

---

## 6. The counter-intuitive part: we recommend charging less

One of the four messages tells a customer on a 15GB package that they used
3.3GB, and offers to move them to a 5GB package that costs Rs. 500 a month
less. We are recommending that Hutch **reduce** that customer's bill.

This is deliberate, and it is a business-model argument rather than a kindness:

> A customer paying Rs. 990 a month for three more years is worth more than a
> customer paying Rs. 1,490 for one more month.

The metric that matters is lifetime value, not this month's ARPU. A customer who
notices they are paying for 40GB and using 5GB does not negotiate — they leave,
quietly, and they blame the operator for letting it happen. Being the one who
points it out first is how the relationship survives, and a smaller package
renewed for years beats a larger one abandoned.

This is also the part of the pitch that is hardest for a competitor to copy,
because it requires giving up revenue this quarter on purpose.

---

## 6b. A second revenue stream: the system finds gaps in the catalogue

Everything above is about *protecting* revenue. The same detection also *finds*
revenue, and this came out of a case we originally got wrong.

The system sizes each customer's package against what they actually use. Most of
the time that produces a straightforward recommendation: downgrade someone paying
for 40 GB and using 3, upgrade someone capped at 5 GB and topping up every week.

But some customers sit at the **edge of the catalogue**, and there the
recommendation has nowhere to go:

| Situation | What a naive system says | What is actually true |
|---|---|---|
| Heavy user already on the largest package | "Switch to Unlimited" — the plan they already have | **Hutch has no package for this customer** |
| Very light user already on the smallest package | "Switch to Lite 5GB" — the plan they already have | There is no cheaper entry point to offer |

These are not customer problems. They are **product gaps**, and the second column
is a message nobody should ever receive. StaySignal now labels them as such and
routes them to the product team instead of to retention.

### Why this is commercially interesting

A customer who has outgrown the top of the catalogue is, by definition, among the
highest-spending customers in the base — and there is nothing left to sell them.
They are simultaneously the most valuable and the most exposed: a competitor
launching a larger package is speaking directly to them.

In the demo base of 150 customers, 9 sit at a catalogue edge and together
represent **Rs. 10,496 of monthly spend**, Rs. 6,979 of it at the top of the
range. Two individual customers paying Rs. 3,876 and Rs. 3,103 a month have no
upgrade available to them.

### The recommendation to Hutch

**Widen the top of the data catalogue.** A tier between the current largest
package and true unlimited — or several unlimited variants differentiated by
speed, night-time allowance or family sharing — converts a retention problem into
an upsell. Today those customers can only be given a loyalty bonus, which costs
margin and sells nothing.

This is a product decision for Hutch, not something StaySignal can implement. What
StaySignal contributes is the evidence: a monthly count of customers pressing
against each edge of the catalogue, their spend, and how fast that group is
growing. Demand that appears outside the product range is normally invisible,
because no system is looking for a package that does not exist.

## 7. How it operates inside Hutch

**Nothing about the architecture asks Hutch to change how it works.**

- The risk engine reads Hutch's own data warehouse. StaySignal adds no new
  destination for customer data — it does not leave
  Hutch's systems — which also removes the data-protection objection before it
  is raised.
- Offers go out through Hutch's existing SMS gateway. No new channel.
- The integration point is the API we built: `POST /score/batch` takes up to
  5,000 customers per call. A nightly job scores the base and writes the flags
  into the CRM. That is the whole integration.
- The six messages already exist in Sinhala, Tamil and English, because a
  retention message in the wrong language is not a retention message.

### Rollout, in the order that de-risks it

**Phase 1 — four weeks, one region.** Score the base. Split the flagged
customers into a treated group and an untreated holdout. Send offers to the
treated group only.

This phase is the most valuable thing in this document, because it replaces
both of our assumptions with measured values: the holdout tells us the real save
rate, and the billing system tells us the real offer cost. After four weeks the
business case stops being a model and becomes a result.

**Phase 2 — learn the offers.** Right now the four causes are assigned by rules
over the same features. Once Phase 1 has recorded which offer worked on which
kind of customer, the offer choice becomes a second learned model instead of a
rule.

**Phase 3 — national, nightly, automatic.** With the threshold re-tuned on
Hutch's real revenue rather than our simulated revenue.

---

## 8. If this became a venture

Honest assessment of three ways to charge, and the objection each one meets.

**Per-subscriber-per-month licence.** Fractions of a rupee per subscriber
scored. Predictable for both sides, and it scales with the value delivered.
Objection: an operator will compare it against building it themselves, and at
this level of complexity, building it is cheap.

**Flat platform fee.** Simpler to sell and to budget. Objection: it is
disconnected from results, so it is the first line cut in a bad quarter.

**Share of measured saved revenue.** The most attractive-sounding, and the
hardest to actually sell. Operators dispute attribution — they will argue the
customer would have stayed anyway. It only becomes sellable if the Phase 1
holdout is part of the contract, because a holdout is the only clean answer to
"prove it was you". Our rollout design happens to make this model possible;
that is not an accident.

**The strategic weakness, named.** Hutch could build this. Eleven features and a
logistic regression is not a moat. What is hard to copy is not the code — it is
the framing: that there are four causes and not one, that blanket discounting
loses money, and that a smaller package can be the right recommendation. That is
why we would sell the method and the rollout design, not the algorithm.

**Where else it applies.** Any subscription business with usage signals and
without complaints as an early warning: other operators, utilities, streaming,
insurance renewals, gyms. The engine is the same; the four causes change.

---

## 9. What we are honest about

- The model is trained on **simulated** data. The competition dataset had not
  been released when this was built. Only the input file changes when it
  arrives — the pipeline is already written for it.
- The 15% offer cost and 35% save rate are **stated assumptions**, not measured
  values. Section 5 is our answer to that, and Phase 1 is our fix.
- The Rs. 58 million a month is **extrapolation**, with its conditions printed
  next to it in section 3.
- **Offer fatigue is capped, not measured.** A 30-day contact window stops the
  same customer being messaged repeatedly, but the right length of that window
  is a guess until it is tested.
- Marketing SMS is subject to consent rules. A real deployment has to check the
  do-not-contact list before it sends anything, and we have not built that.
- 39% of our offers reach people who were not leaving. That cost is counted, but
  it is a cost.

Say all of this out loud. A judge who finds an unstated assumption stops
believing the numbers that were true.

---

## 10. The sixty-second version

> The Sri Lankan mobile market shrank 1% last year. There are no new customers
> to win, so the only growth left is keeping the ones you have. The industry's
> answer is a blanket discount — and we measured it: on 1,000 customers, blanket
> discounting lost Rs. 710,693 *more* than doing nothing at all, because the
> discount goes to the 81% who were never leaving. Targeting the customers our
> model flags saves Rs. 96,447 against doing nothing, which is Rs. 16.07 per
> customer per month. Our save-rate assumption could fall from 35% to 23.4%
> before that stops being true. It costs no GPU and no new infrastructure,
> because the model is 24 multiplications. And in four weeks with one
> holdout region, every assumption in this pitch becomes a measurement.

---

**Sources for section 2:**
Sri Lanka mobile market size, decline and Hutch subscriber estimate —
[Operator Watch, June 2026](https://www.operatorwatch.com/2026/06/sri-lankas-mobile-market-enters-5g-era.html).
