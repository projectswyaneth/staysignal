# StaySignal — model results

Trained on simulated data: **4,000 customers x 26 weekly observations**,
18.6% churn. Every number below comes from a held-out test set of
**1000 customers** the model never saw.

> All data in this repository is simulated. The pipeline is written so that
> only the input tables change when Hutch's own extracts arrive.

## How the model got here

| Version | Features | Added because a panel asked | ROC AUC | PR AUC |
|---|---|---|---|---|
| v1 — idea pitch | 4 | — | 0.825 | 0.499 |
| v2 — first technical panel | 18 | network evidence, travel, seasonality | 0.864 | 0.593 |
| **v3 — finalist panel (deployed)** | **24** | own-mobility baseline, interference, competitor pressure | **0.864** | **0.607** |
| Gradient boosting benchmark | 24 | — | 0.840 | 0.556 |

5-fold cross-validation: v2 0.856 (+/- 0.009),
v3 0.857 (+/- 0.008).

**Read that table honestly: v2 to v3 barely moves AUC, and that is expected.**
AUC measures ranking across the whole base. Two of the three faults the
finalist panel found are invisible to it — one is a *suppression* bug that never
reaches the score at all, and one affects the 4% of the base a rival's promotion
touches. A version that improved AUC while leaving those in place would be worse,
not better. The four tests below are where v3 earns its place.

The linear model still beats gradient boosting on this data, so the
explainability the challenge requires costs nothing. That is measured, not assumed.

## Test 1 — the holiday test

A customer on holiday reloads less, uses less data and opens the app less.
Every signal v1 watched goes down, so v1 chases them and wastes the offer.
All three systems are given the same contact budget of 144 customers.

| System | Offers wasted on travellers | Real leavers caught |
|---|---|---|
| v1 — 4 behaviour features | **12** | 81 |
| v2 — 18 features | **0** | 91 |
| **v3 — 24 features** | **0** | **93** |

Travellers sit at the **64th** risk percentile under v1 — squarely in
the danger zone. Under v3 they sit at the **26th**, correctly judged safe.

## Test 2 — the sales rep test

*"Some people use the same towers every day, home to office and back. A sales
representative uses completely different towers every day. Did you consider
that?"*

We had not, and the cost was not a wasted offer — it was the opposite, and
worse. v2's suppression rules used **absolute** thresholds, so a field worker
looked permanently *away from home* and was held back every week, including the
weeks he genuinely was leaving. Nothing ever surfaces a suppressed customer, so
that failure is silent.

v3 rewrites every mobility rule against the customer's **own** mobility
baseline.

| | v2 absolute rules | v3 relative rules |
|---|---|---|
| High-mobility customers labelled "travelling" | 88 of 88 | 4 of 88 |
| **Real leavers silently held back** | **20** | **0** |
| Genuine travellers correctly held back | 71 of 105 | 74 of 105 |

(The traveller row is not 105 of 105 in either
column, and should not be: a customer whose trip ended three weeks ago is home
and behaving normally again, so there is nothing left to hold back. The rule
exists for people who are away *now* — and at the operating point only
0 traveller in 144 contacts slips through.)

So the fix is not a trade: v3 stops mislabelling field workers **without** losing
a meaningful number of genuine travellers. That is what you get from changing the reference
point rather than loosening the threshold — a looser absolute threshold would
have had to give one up for the other.

## Test 3 — the shared tower test

*"Those towers are shared with Mobitel, Dialog, Airtel. Congestion there causes
a network loss for your customer. How would you identify that?"*

We cannot see another operator's traffic and never will. We can see signal loss
that **our own load does not explain**, and that is the fingerprint. Cells are
grouped below by the shape of their own KPI history.

| Cell group | n | PRB change | SINR lost | Unexplained (interference feature) |
|---|---|---|---|---|
| healthy | 121 | -0.3 pp | 0.0 dB | **0.1 dB** |
| our own congestion | 11 | +25.7 pp | 3.0 dB | **0.0 dB** |
| external interference | 7 | +0.6 pp | 4.5 dB | **4.1 dB** |
| hardware / outage | 5 | -13.0 pp | 2.8 dB | **2.8 dB** |

Congestion and interference are indistinguishable in SINR alone. They separate
cleanly once SINR is read against our own PRB — and they need different fixes:
capacity for the first, RF planning and inter-operator coordination for the
second.

Two honest caveats. A failing cell also shows unexplained SINR loss, because a
cell carrying *less* traffic explains nothing either; outage minutes and a
falling PRB are what tell hardware apart from interference. And the feature says
only *our own load does not explain this*. It is a strong hint and a work order
for the RF team, never proof that a named neighbouring carrier is responsible.

## Test 4 — the competitor test

*"Look at what Dialog and Mobitel are doing — their promotions can hit Hutch
churn hard."*

Correct, and no internal data can see it, because the cause is outside Hutch.
So competitive pressure enters as an external district-week input, built in
production from MNP port-out reports and the competitor campaign calendar.

Note that the national population baseline does **not** cover this: it cancels
national events, but a district-level promotion barely moves a national median.

| | Leavers pulled by a rival's promotion |
|---|---|
| In the test set | 40 |
| Share caught by v2 | 48% |
| **Share caught by v3** | **52%** |

Learned weight on market pressure: +0.177 (positive, as expected).

## Operating point (0.43)

|  | Predicted stay | Predicted leave |
|---|---|---|
| **Actually stayed** | 764 | 51 |
| **Actually left** | 92 | **93** |

Recall 50% — we catch 93 of the 185 who really left.
Precision 65% — of 144 flagged, 93 really left.
Of the 144 flagged, 7 are held back by policy
(0 of them for travel) and 137 are contacted.

## Money (test set, 6 months)

Assumptions, stated: an offer gives up 15% of that
customer's revenue, and we keep 35% of the leavers we contact.

| Strategy | Revenue lost |
|---|---|
| Contact nobody | Rs. 1,614,006 |
| Contact everybody (blanket discount) | Rs. 2,324,699 |
| **Contact who the model flags** | **Rs. 1,517,559** |

Targeting saves Rs. 96,447 against doing nothing and
Rs. 807,139 against blanket discounting. Blanket discounting is
worse than doing nothing — that is the argument for this project in one line.

The threshold is not the one with the best F1 score. It is the one that loses
the least money, which is a different question and the only one that matters
commercially.

## Honest limitations

- **Simulated data.** Cell KPIs follow standard telecom definitions and
  realistic ranges, but they are simulated. Every number here must be re-run on
  Hutch's own extracts before anyone acts on it.
- The offer cost and save rate are stated assumptions, not measurements. Only a
  controlled holdout can establish them.
- Causes and suppression rules are business rules, not learned. They are
  deliberately rules so Hutch can change them without retraining anything.
- Customers with under ~17 weeks of history cannot be scored: their own baseline
  window does not exist yet.
- Market pressure requires an external feed. Without it the feature is zero and
  the model degrades to v2 behaviour on competitor-driven churn.
- Interference is inferred, not measured. It says *our own load does not explain
  this*, which is a strong hint and a work order for the RF team — not proof of
  a specific neighbouring carrier.
