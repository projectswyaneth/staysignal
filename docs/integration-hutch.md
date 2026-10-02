# Integrating StaySignal with Hutch

> **Status:** designed against sources Hutch IT confirmed on 1 October 2026.
> No Hutch API, credential, production system or data was used during the
> hackathon, in line with the guidelines. Every field name below is either
> confirmed by Hutch or clearly labelled as our assumption.

---

## 1. What we asked, and what Hutch answered

| # | Question put to Hutch IT | Answer |
|---|---|---|
| 1 | Does Hutch use a CEM platform? | **Yes — but its data is not exposed to third-party systems.** |
| 2 | Which system holds per-cell KPIs (drop rate, SINR, PRB)? | **OSS / NMS — available.** |
| 3 | Is subscriber-to-serving-cell history available from CDR / xDR? | **Yes.** |
| 4 | Which system holds prepaid recharge and usage history? | **The data warehouse.** |
| 5 | Preferred integration style — REST, Kafka or warehouse batch? | **Any of the three.** |

Four of the five answers confirm that every input StaySignal needs already
exists. The fifth is a constraint, and it is the one that shaped the
architecture.

### What answer 1 means for the design

A CEM platform that does not expose data to third-party systems rules out one
architecture completely: StaySignal as an external service that consumes CEM
output. We think that is the right call by Hutch, and the design follows it:

- StaySignal **runs inside Hutch's boundary** — their VM, their container
  platform, their data centre. It is not a SaaS product and there is no vendor
  endpoint.
- It **never reads from the CEM.** Its inputs are OSS, CDR and the warehouse.
- **No subscriber record leaves the building to be scored.** There is no LLM
  call, no external API, no vendor telemetry. The model is 24 numbers in a JSON
  file; scoring is arithmetic.
- The only external input is **district-level market data** containing no
  personal information whatsoever — counts and dates, by district.

StaySignal is therefore better understood as a **component Hutch runs**, and
whose output can feed their CEM, than as a system that reads from it.

---

## 2. The four tables

Everything downstream of the adapter consumes exactly four tables. Their full
machine-readable contract — every column, type and physical range — is in
[`integrations/oss_adapter.py`](../integrations/oss_adapter.py), which is
executable and self-testing:

```bash
python integrations/oss_adapter.py
```

### 2.1 `cells_weekly` — from OSS / NMS ✅ confirmed

One row per cell per week. These are numbers Hutch's own network engineers
already look at every day; we are not asking anyone to build or measure
anything new.

| Column | Meaning | Physical range |
|---|---|---|
| `cell_id` | must match `serving_cell` in the CDR extract | — |
| `region` | district, for the market join | — |
| `week` | ISO week index | 1–520 |
| `call_drop_rate_pct` | share of calls on that cell that cut off | 0–100 |
| `avg_sinr_db` | signal quality | −20 to 40 |
| `prb_utilisation_pct` | congestion — how full the cell is | 0–100 |
| `handover_success_pct` | optional; calls surviving a move between cells | 0–100 |
| `outage_minutes` | per week | 0–10080 |
| `shared_site` | optional; from the site database — is this tower shared or co-located with another operator | 0/1 |

`shared_site` is the only field here that may need a join Hutch does not run
today, and it is **optional**. It is used to read interference honestly, never
to attribute a fault to a named competitor.

### 2.2 `customers_weekly` — from CDR / xDR, joined to recharge and app logs ✅ confirmed

One row per subscriber per week. **No message content and no packet inspection.**
Everything here is already recorded for billing and network operations.

| Column | Meaning |
|---|---|
| `customer_id` | pseudonymous subscriber key |
| `week` | ISO week index |
| `data_gb`, `voice_minutes`, `recharges`, `app_opens` | behaviour that week |
| `serving_cell` | the **dominant** cell that week |
| `home_cell_share` | share of sessions on their modal cell |
| `distinct_cells` | how many different cells served them that week |
| `distinct_regions` | how many districts those cells sat in |
| `attached` | did they attach to the network at all that week |

The last four are the mobility footprint. They are weekly **aggregates** — we
never need, store or want a subscriber's movement trail. A count of cells and a
count of districts is enough to tell a traveller from a leaver, and it is the
least invasive form of the signal that still works.

### 2.3 `customers_static` — from the prepaid data warehouse ✅ confirmed

One row per subscriber: `region`, `language`, `plan`, `data_quota_gb`,
`monthly_spend_lkr`, `months_with_hutch`, `overage_charges_lkr`,
`complaints_last_month`.

`language` drives which SMS template is used. It is chosen from the customer's
own language field rather than translated at send time.

### 2.4 `market_weekly` — external

One row per district per week: `competitor_promo_intensity` and, preferred where
available, `port_out_rate_pct`.

Built from two things:

- **MNP port-out reporting.** Hutch knows exactly how many numbers left each
  district and to which operator. This is the ground truth for competitive loss,
  and it is *measured* rather than announced.
- **The competitor campaign calendar.** Promotions are publicly advertised, so
  start and end dates are known, not guessed.

This table contains **no personal data** — district totals only.

---

## 3. The adapter

[`integrations/oss_adapter.py`](../integrations/oss_adapter.py) is the only file
that changes when real extracts arrive. A Hutch integrator fills in one mapping
per source:

```python
"cells_weekly": FieldMap(
    rename={
        "CELL_NAME":        "cell_id",
        "AVG_SINR_DL":      "avg_sinr_db",
        "DL_PRB_UTIL":      "prb_utilisation_pct",
        "CELL_UNAVAIL_SEC": "outage_minutes",
    },
    scale={
        "prb_utilisation_pct": 100.0,   # if exported as a 0-1 fraction
        "outage_minutes":      1 / 60,  # if exported in seconds
    },
)
```

Nothing else in the repository is touched — not the features, not the model, not
the console.

### It refuses bad extracts rather than scoring them

What usually derails a telecom pilot is not the model. It is three months of
discovering that a column was renamed upstream, or that outages are in seconds,
or that PRB is a fraction in one table and a percentage in another. So the
adapter validates before anything is scored, and says so loudly:

- **Missing required columns** — named, and the load fails.
- **Physically impossible values** — a drop rate above 100%, SINR below −20 dB.
  These are not statistical outliers, they are broken exports, and the
  difference matters: we clip the first kind and reject the second.
- **Broken joins** — serving cells with no OSS record. This is the failure that
  matters most, because it is *silent*: such a customer gets scored as though
  their towers were fine.
- **Insufficient history** — subscribers with under 17 weeks have no baseline
  window of their own, so they are excluded rather than guessed at.

The file ships with a negative test that corrupts a known-good extract and
confirms both failures are caught.

---

## 4. Deployment

### Recommended: nightly warehouse batch

```
02:00  warehouse export        ->  /staysignal/inbox/*.parquet
02:20  adapter + validation    ->  four canonical tables (or a rejection report)
02:30  feature build           ->  one row per subscriber
02:35  score + suppress        ->  ranked queue + held-back queue
02:40  publish                 ->  CEM console / campaign system
```

The whole run is minutes of CPU on one machine. The heavy step is a `group by`
per table — not the model, which is 24 multiplications per subscriber.

REST and Kafka transports are **specified** in the adapter but deliberately left
unimplemented: writing them against a guessed endpoint would be fiction, and
since the features are weekly aggregates, a stream would be collapsed back into
the same four tables anyway. Streaming adds operational cost and no accuracy.

### Sizing

| Base size | Feature build | Scoring | Storage per week |
|---|---|---|---|
| 150,000 | ~1 min | < 1 s | ~25 MB |
| 1,000,000 | ~6 min | ~2 s | ~170 MB |

Single commodity VM. No GPU. No external API. No per-customer cost.

---

## 5. What we would need to agree before a pilot

1. **A pseudonymous subscriber key** that is stable across OSS, CDR and the
   warehouse. Nothing identifying is needed — StaySignal never sees a name or a
   phone number.
2. **Retention window.** 26 weeks of history is what the features assume; 17 is
   the minimum for a customer to be scorable at all.
3. **A holdout group.** The save rate (currently a stated assumption of 35%) can
   only become a measurement if some flagged customers are deliberately not
   contacted. This is the single most valuable thing a pilot can produce.
4. **Where the output goes.** A ranked queue into the existing campaign system,
   or the console in this repository, or both.
5. **Who owns the network cases.** Flagged network faults are work orders for
   the RF team, not discounts for marketing. That routing has to exist.

---

## 6. What we are not claiming

- We have not tested this on Hutch data, and nobody should act on the reported
  numbers until it has been.
- We cannot see another operator's traffic. The interference signal says *our
  own load does not explain this*, which is a strong hint and a work order — not
  proof that a named carrier is responsible.
- The market feed needs to be built. Without it, that feature is zero and the
  model degrades gracefully to its previous behaviour on competitor-driven churn.
