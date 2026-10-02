# Questions the panels asked, and our answers

Every question below was actually put to us — at the idea pitch, the first
technical panel, or the finalist panel. Each answer points at the code or the
number that backs it, so none of this has to be taken on trust.

---

## "Isn't this really a Customer Experience Management tool?"

Yes — and that is a better description than the one we started with, so we have
adopted it.

> **StaySignal is a Customer Experience Management module for prepaid.** It
> detects silent customer-experience failures, identifies the cause from
> network, usage, billing and market data, and triggers the matching recovery
> action.

CEM means measuring what each customer actually experiences and then acting on
it. That is exactly what we do: network experience, usage behaviour, billing
experience and market context combine into one per-customer picture that
triggers an action. "Churn prediction" described the output; CEM describes the
job.

---

## "How do you actually know it is a network problem?"

We join two things Hutch already has.

1. **From CDR / xDR**, which cells served each customer, week by week.
2. **From OSS / NMS**, each cell's own quality history — drop rate, SINR, PRB
   utilisation, handover success, outage minutes.

Then: *"This customer spent 80% of last month on cell KAN_07. That cell's drop
rate went from 0.4% to 3.1% over three weeks, and this customer's data use fell
in the same weeks."*

That is not a guess. It is evidence with a cause and a timeline, and **we can
name the tower.**

Crucially, each cell is compared to **its own** past, not to other cells — a
cell in Colombo is permanently busier than one in Anuradhapura, and what matters
is whether a cell got worse than it normally is.

*Code:* `cell_baselines()` in [`ml/features.py`](../ml/features.py).
*Evidence:* network-profile customers churn at 63% in the simulation, and the
network features carry real weight in `reports/weights.png`.

---

## "What happens when the customer is travelling?"

The network still sees them — just on different towers. That is the whole
distinction:

> **A customer who is leaving is at home, but silent.
> A customer on holiday is away, but still active somewhere else.**

So we track how much of their time is spent on their usual towers, how many
districts they appear in, and how long it has been since they attached to the
network at all. A leaver's home-tower share stays high while everything else
falls. A traveller's collapses while they keep attaching every day.

*Evidence — the holiday test.* At an equal contact budget of 144 customers:

| | Offers wasted on travellers | Real leavers caught |
|---|---|---|
| 4 behaviour features (idea pitch) | 12 | 81 |
| **24 features (deployed)** | **0** | **93** |

Travellers move from the **64th** risk percentile to the **26th**.

---

## "What about someone on holiday — a national holiday, when everyone is quiet?"

We stopped asking *"did their usage fall?"* and started asking *"did it fall
further than everyone else's fell that week?"*

| Everyone dropped | They dropped | Verdict |
|---|---|---|
| 30% | 30% | Nothing. Ignore. |
| 30% | 80% | Real signal. Flag. |
| 0% | 40% | Real signal. Flag. |

One feature does this — their change divided by the median change of the whole
base that week. **Seasonality cancels itself out.** No holiday calendar, no
manual rules, and it works for holidays nobody told us about.

*Code:* `population_baseline()` in [`ml/features.py`](../ml/features.py).

---

## "Some people use the same towers every day — home to office and back. A sales rep uses different towers every day. Did you consider that?"

We had not, and the consequence was worse than we first assumed.

The obvious worry is a false alarm. The real problem was the opposite. Our
suppression rules used **absolute** thresholds — "home-tower share below 0.35
means travelling" — and a field worker's home-tower share is *permanently* below
0.35, because his sessions are spread across a dozen towers. So the system
labelled him "travelling" and held the offer back **every single week**,
including the weeks he genuinely was leaving. Nothing surfaces a suppressed
customer, so that failure never shows up in any accuracy metric.

The fix is the same idea we use everywhere else: compare each person to **their
own** normal.

```
mobility_ratio    = towers visited recently ÷ towers they normally visit
regions_ratio     = districts visited recently ÷ districts they normally visit
home_share_ratio  = time on home tower recently ÷ their own normal
```

A sales rep: 12 ÷ 12 = 1.0 → normal, contact him.
An office worker on holiday: 11 ÷ 2 = 5.5 → travelling, hold.

*Evidence — the sales rep test:*

| | Absolute rules | Relative rules |
|---|---|---|
| High-mobility customers labelled "travelling" | 88 of 88 | 4 of 88 |
| **Real leavers silently held back** | **20** | **0** |
| Genuine travellers still correctly held | 71 | 74 |

It is not a trade-off: we stopped mislabelling field workers **without** giving
up the holiday fix. That is what you get from changing the reference point
rather than loosening the threshold.

---

## "Those towers are shared with Mobitel, Dialog, Airtel. Congestion there causes a network loss for your customer. How would you identify that?"

Honestly: we cannot see another operator's traffic, and we never will.

What we can see is **signal quality loss that our own load does not explain** —
and that has a distinguishable fingerprint:

| PRB utilisation | SINR | Diagnosis | Fix |
|---|---|---|---|
| **High** | Low | Our own congestion — our cell is full | Add capacity |
| **Flat** | Low | Something outside our traffic | RF planning, inter-operator coordination |
| **Falling** | Low, with outages | Failing hardware | Truck roll |

So the feature is *SINR loss minus the loss our own PRB growth accounts for*.

*Evidence — the shared tower test:*

| Cell group | n | PRB change | SINR lost | Unexplained |
|---|---|---|---|---|
| Healthy | 121 | −0.3 pp | 0.0 dB | 0.1 dB |
| Our own congestion | 11 | **+25.7 pp** | 3.0 dB | **0.0 dB** |
| External interference | 7 | **+0.6 pp** | 4.5 dB | **4.1 dB** |
| Hardware / outage | 5 | −13.0 pp | 2.8 dB | 2.8 dB |

Two groups look nearly identical in SINR alone, and separate cleanly once SINR
is read against our own PRB.

We also carry the `shared_site` flag from Hutch's own site database, so an
investigation can be prioritised toward co-located towers. **We never name a
competitor** — the output is a work order for the RF team, not an accusation.

---

## "What about Dialog's and Mobitel's promotions? Those can hit Hutch churn hard."

Entirely correct, and nothing inside Hutch can explain it — the cause is outside
the company. So it enters as an **external, district-level input**, built from:

- **MNP port-out reporting.** Hutch knows exactly how many numbers left each
  district and to which operator. That is measured ground truth for competitive
  loss, not an inference.
- **The competitor campaign calendar.** Promotions are publicly announced, so
  dates are known rather than guessed.

Note why the population baseline does not already cover this: that baseline is a
**national** median, so it cancels national events but barely moves for a
district-level campaign. The two mechanisms are complementary, not redundant.

*Evidence — the competitor test:* capture of promotion-driven leavers rises from
**48% to 52%** at an equal contact budget, and the learned weight on market
pressure is positive (+0.177) as expected.

It also changes the *action*: a customer leaving because a rival got cheaper
needs a competitive counter-offer, not an apology for a tower.

---

## "Why not a neural network, or an LLM, or a transformer?"

Because the challenge requires the system to explain its decisions, and a linear
model makes that **exact** rather than approximate. A customer's risk is
literally the sum of each feature's weighted contribution, so the console shows
an agent the real reason rather than a post-hoc approximation of it.

We did not assume this was free — we benchmarked it. Gradient boosting on
identical features scored **0.840**; the linear model scored **0.864**. On this
problem, explainability costs nothing.

Temporal models and attention over the weekly series are a genuine future
direction, and the data pipeline is already shaped for them: the tables are
weekly time series, not snapshots. We did not use them because with 26
observations per subscriber the benefit is speculative and the auditability loss
is certain.

And one commercial point: StaySignal makes **no LLM call at all**, so scoring a
million subscribers costs seconds of CPU and no token bill. That is why Hutch
could score the whole base nightly rather than a sample monthly — and churn
signals are weekly, so a monthly sample finds them after the customer has gone.

---

## "What if you don't have the data?"

Then we say so and say how we would get it. Our integration design is built
against sources Hutch IT confirmed on 1 October 2026 — OSS/NMS cell KPIs,
CDR/xDR serving-cell history, and prepaid recharge and usage from the data
warehouse are **all available**, and any integration style is acceptable.

The one constraint they gave us — the CEM platform does not expose data to
third-party systems — shaped the architecture for the better: StaySignal runs
**inside** Hutch's boundary, reads from OSS, CDR and the warehouse rather than
the CEM, and never sends a subscriber record anywhere to be scored.

Full field-level spec: [integration-hutch.md](integration-hutch.md).

---

## "How much of this is real?"

The code is real and runs. The data is simulated, and we say so on the first
screen of the README, in the architecture diagram, in every report the pipeline
generates, and here.

What the simulation is *for* is testing the fixes. It deliberately contains a
holiday inside the scoring window, travellers who are not leaving, high-mobility
field workers, three physically different cell fault types, and a regional
competitor promotion — because a fix you cannot measure is a claim, not an
engineering result.

What we are not claiming: that these numbers will hold on Hutch's data. They
will move. What should survive is the *ordering* — targeted beats doing nothing,
and both beat a blanket discount — because that comes from the economics rather
than from the model.

---

## If we still do not know

Say so, then say how we would find out. *"I don't have that figure — it would
come from the OSS KPI export, and here is how we would use it."*

Going blank is only a problem if you pretend.
