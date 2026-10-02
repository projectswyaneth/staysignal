# Known limitations

Submission item 9. We would rather state these plainly than be asked about them.
Each one is listed with what it would take to close.

---

## 1. The data is simulated

**The limitation.** Every number in this repository comes from
[`ml/generate.py`](../ml/generate.py). Cell KPIs follow standard telecom
definitions and realistic value ranges, and the schema matches what an operator
would actually export — but the data is generated, and a model trained on
generated data has learned the generator.

**Why it is this way.** The guidelines state that no Hutch APIs, credentials,
production systems or data are shared during the hackathon. The alternative to
simulating was to build nothing testable.

**What we did about it.** The simulator was built to contain the specific traps a
real base contains — a holiday inside the scoring window, travellers who are not
leaving, high-mobility customers, three physically different cell fault types, a
regional competitor promotion — so that the fixes could be *measured* rather than
claimed. The four regression tests in [`reports/metrics.md`](../reports/metrics.md)
are only meaningful because the traps are there.

**What closes it.** Re-run the pipeline on Hutch extracts. Only
[`integrations/oss_adapter.py`](../integrations/oss_adapter.py) changes. Expect
every number to move; expect the *ordering* of the strategies — targeted beats
nothing beats blanket — to hold, because that ordering comes from the economics
rather than from the model.

---

## 2. Offer cost and save rate are assumptions

**The limitation.** We assume a retention offer gives up 15% of a customer's
revenue and retains 35% of contacted leavers. Neither is measured.

**What we did about it.** [`ml/business_case.py`](../ml/business_case.py) reports
break-even points instead of a single ROI figure. Targeting stays ahead of
blanket discounting down to a **23.4%** save rate and up to a **22.5%** offer
cost — comfortably wide margins around our assumptions.

**What closes it.** A pilot with a holdout group: some flagged customers
deliberately not contacted. This is the single most valuable thing a pilot can
produce, and it is the only way the save rate becomes a measurement.

---

## 3. Interference is inferred, not measured

**The limitation.** The `cell_interference` feature says *this cell lost signal
quality that our own traffic load does not explain*. It does not prove that a
specific neighbouring operator is responsible. Physical obstruction, external
RF sources and equipment ageing produce a similar fingerprint.

**What we did about it.** We never name a competitor. A high interference reading
is routed as an **investigation work order** to the RF team, alongside the
`shared_site` flag from Hutch's own site database. A failing cell also shows
unexplained SINR loss — a cell carrying less traffic explains nothing either — so
outage minutes and a *falling* PRB are what separate hardware from interference.

**What closes it.** Drive tests, or the operator's own spectrum monitoring. These
exist; we are simply not able to run them from a hackathon.

---

## 4. Market pressure requires an external feed

**The limitation.** The competitor feature is zero unless somebody supplies
district-level market data. Without it, the model degrades to its previous
behaviour on competitor-driven churn — roughly a 4-point drop in capture of
promotion-driven leavers in our test.

**What closes it.** MNP port-out reports (Hutch already has these) plus the
competitor campaign calendar (public). Neither needs new measurement.

---

## 5. Customers with short history cannot be scored

**The limitation.** Features compare each customer to their own baseline window,
weeks 5–16. A subscriber with under ~17 weeks of history has no such window.

**What we did about it.** They are **excluded and counted**, not guessed at. The
adapter reports how many there are on every load.

**What closes it.** A separate cold-start treatment for new subscribers — a
different problem with different signals (first-30-day behaviour, acquisition
channel), and out of scope for this challenge. Honestly: it is a second project.

---

## 6. Causes and suppression rules are not learned

**The limitation.** The five causes and the three suppression rules are written
by us, not fitted from data.

**Why, deliberately.** They encode *business policy*, not statistics. Hutch must
be able to change "do not contact anyone twice in 30 days" without retraining a
model, and must be able to explain to a regulator or a customer why an offer was
or was not sent. A model that cannot be overruled by the business does not get
deployed by the business.

**What would change our mind.** Enough outcome data to learn which suppression
rules actually preserve revenue. That is a post-pilot question.

---

## 7. The holiday fix depends on the base moving together

**The limitation.** The population baseline cancels seasonality by asking whether
a customer fell *further than everyone else fell*. It works when an event moves
the whole base. It does **not** work for an event that moves only one segment —
and that is precisely why family F (market context) exists, because a district
promotion barely moves a national median.

**Residual risk.** A segment-level event that is neither national nor
district-shaped — say, a campaign aimed only at high-value subscribers — would
still be missed. A segment-aware baseline is the obvious extension.

---

## 8. A traveller detected late is still a wasted offer

**The limitation.** Suppression works on weekly aggregates. Someone who leaves on
Saturday and is flagged on Monday can be contacted before the mobility signal is
visible.

**What we did about it.** The scoring window is the last four weeks, so a short
trip rarely moves someone over the threshold at all. At our operating point, no
traveller at all reaches the contact list — though that margin is thin and we
would not promise it on real data.

**What closes it.** Daily rather than weekly aggregation. The pipeline supports
it; nothing in the feature definitions assumes a week specifically.

---

## 9. No temporal model

**The limitation.** We use aggregates over windows rather than a model that reads
the weekly sequence directly. A sequence model — or attention over the weekly
series — could in principle detect the *shape* of a decline rather than its size.

**Why not here.** With 26 observations per subscriber and a requirement to
explain every decision, the cost is real and the benefit is speculative. The
relative features already encode the comparison that matters. We would rather
ship something the team can defend line by line than something that scores
marginally better and cannot be audited.

**Recorded as future work**, with the data pipeline already shaped for it: the
tables are weekly time series, not snapshots, precisely so this is possible later
without rebuilding anything.

---

## 10. Single-operator view

**The limitation.** We see Hutch's network and Hutch's subscribers. We cannot see
what a customer experiences on a competitor's network, which is the obvious
counterfactual for "would they be better off elsewhere".

**Why it is acceptable.** No operator can see this, and the market feed is the
closest legitimate proxy.

---

## 11. Fairness and conduct

**The limitation.** A model that targets retention offers decides who gets a
discount. If it systematically favoured particular districts or languages, that
would be a conduct problem, not merely a technical one.

**What we did about it.** No protected attribute is an input. Region enters only
through the market feed and the cell join, never as a risk factor in itself, and
`language` is used solely to choose which SMS template is sent.

**What closes it.** A per-district and per-language audit of flag rates on real
data, before any pilot goes live. We have not been able to run it on simulated
data in a way that would mean anything.
