# Integrating StaySignal with Hutch

> **Status:** designed against sources Hutch IT confirmed on 1 October 2026.
> Hutch has since told us that its data warehouse runs on **Snowflake**, and
> this document is updated to match. No Hutch API, credential, production
> system or data was used during the hackathon, in line with the guidelines,
> and we have not connected to Hutch's Snowflake account. Every field name
> below is either confirmed by Hutch or clearly labelled as our assumption.

---

## 1. What we asked, and what Hutch answered

| # | Question put to Hutch IT | Answer |
|---|---|---|
| 1 | Does Hutch use a CEM platform? | **Yes — but its data is not exposed to third-party systems.** |
| 2 | Which system holds per-cell KPIs (drop rate, SINR, PRB)? | **OSS / NMS — available.** |
| 3 | Is subscriber-to-serving-cell history available from CDR / xDR? | **Yes.** |
| 4 | Which system holds prepaid recharge and usage history? | **The data warehouse, which runs on Snowflake.** |
| 5 | Preferred integration style — REST, Kafka or warehouse batch? | **Any of the three.** |

Four of the five answers confirm that every input StaySignal needs already
exists. The fifth is a constraint, and it is the one that shaped the
architecture.

### What answer 1 means for the design

A CEM platform that does not expose data to third-party systems rules out one
architecture completely: StaySignal as an external service that consumes CEM
output. We think that is the right call by Hutch, and the design follows it:

- StaySignal **runs inside Hutch's boundary** — their VM or their container
  platform, on a network that can already reach their Snowflake account. It is
  not a SaaS product and there is no vendor endpoint.
- It **never reads from the CEM.** Its inputs are OSS, CDR and the Snowflake
  warehouse.
- **No subscriber record is sent anywhere new to be scored.** StaySignal reads
  only from Hutch's own systems: OSS, CDR and their Snowflake account. There is
  no LLM call, no external API, no vendor telemetry. The model is 24 numbers in
  a JSON file; scoring is arithmetic.
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

### 2.3 `customers_static` — from the prepaid data warehouse (Snowflake) ✅ confirmed

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

### Reading from Snowflake rather than from files

The CSV loader exists because a laptop has no warehouse attached to it. The
production path is `from_sql_warehouse()`, pointed at Hutch's Snowflake account:

```python
import snowflake.connector
conn = snowflake.connector.connect(
    account="<hutch_account>",               # placeholder
    user="STAYSIGNAL_READER",                # placeholder
    role="STAYSIGNAL_READ_ONLY",             # placeholder
    password=os.environ["SF_PASSWORD"],      # never in the code
    warehouse="ANALYTICS_WH",                # placeholder
    database="PREPAID")                      # placeholder

frames = from_sql_warehouse(conn, schema="PUBLIC", since_week=1)
```

**What is confirmed and what is assumed.** Hutch has confirmed that the
warehouse is Snowflake. The account, role, virtual warehouse, database and
schema names above are **placeholders**: we have not been given the real ones.
For a service account, Hutch's security team would choose the authentication
method (key-pair authentication is the usual choice over a password).

**Access needed is read-only.** One role with `SELECT` on the tables or views
that back the four contracts in section 2. StaySignal does not need to create,
change or delete anything in the warehouse.

**Which tables are in Snowflake.** Hutch confirmed that recharge and usage
history live in the warehouse. We have **not** confirmed whether the OSS cell
KPIs and the CDR serving-cell aggregates are also landed in Snowflake:

- If they are, all four tables arrive through this one connection.
- If they are not, those two arrive as extracts through the file loader, and
  the adapter validates and joins them exactly the same way.

**Not locked to one vendor.** `from_sql_warehouse()` takes any DB-API
connection or SQLAlchemy engine, so the same function would work against
Oracle, Teradata, BigQuery or Postgres. Only the connection object is specific
to Snowflake.

No file is created anywhere on this path.

**It is tested, not asserted.** `python integrations/oss_adapter.py` builds a
SQLite database from the extracts, reads it back through `from_sql_warehouse()`,
and checks the resulting tables are identical to the file path. SQLite is the
one SQL engine available to us without an account — but the code under test is
the code a Snowflake connection would run. Only the connection object differs.
We have **not** run it against Snowflake itself, so Snowflake-specific details
(upper-case column names, data types) still need a first test run in Hutch's
environment.

**At real scale, push the aggregation down.** The weekly feature build is a
`GROUP BY`, and Snowflake does that far faster than pandas can. Against a base
of millions, the right shape is to compute the recent-window and baseline-window
aggregates in SQL and pull **one row per customer** rather than twenty-six:

```sql
SELECT customer_id,
       AVG(CASE WHEN week > 22              THEN data_gb END) AS recent_data,
       AVG(CASE WHEN week BETWEEN 5 AND 16  THEN data_gb END) AS base_data
FROM   CUSTOMERS_WEEKLY
GROUP  BY customer_id
```

That moves megabytes instead of gigabytes, and the feature definitions do not
change — only where the arithmetic happens.

### A precise note on "data never leaves"

Worth stating carefully, because the loose version of this claim is wrong.

Hutch's warehouse is Snowflake, which is a cloud data platform. Their data is
already in that cloud — that was Hutch's decision, made before StaySignal
existed. So we do not claim that data "never leaves the building". What we can
honestly claim is narrower and still strong:

> **StaySignal adds no new destination for customer data.** It reads from where
> Hutch already keeps it, and sends nothing anywhere else. No external API, no
> LLM, no vendor endpoint, no telemetry. The only outbound thing in the whole
> system is an SMS, sent by Hutch's own platform.

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

### Recommended: nightly Snowflake batch

```
02:00  Snowflake query (read-only) ->  aggregated rows, pulled over the connection
02:20  adapter + validation        ->  four canonical tables (or a rejection report)
02:30  feature build               ->  one row per subscriber
02:35  score + suppress            ->  ranked queue + held-back queue
02:40  publish                     ->  CEM console / campaign system
```

No export file is written: the job queries Snowflake directly. If Hutch
prefers, the ranked queue can also be written back to a single results table in
Snowflake, which would need `INSERT` on that one table only.

The heavy step is a `group by` per table, which runs inside Snowflake on
Hutch's own virtual warehouse — not the model, which is 24 multiplications per
subscriber. The scoring side is minutes of CPU on one machine.

REST and Kafka transports are **specified** in the adapter but deliberately left
unimplemented: writing them against a guessed endpoint would be fiction, and
since the features are weekly aggregates, a stream would be collapsed back into
the same four tables anyway. Streaming adds operational cost and no accuracy.

### Sizing

| Base size | Feature build | Scoring | Storage per week |
|---|---|---|---|
| 150,000 | ~1 min | < 1 s | ~25 MB |
| 1,000,000 | ~6 min | ~2 s | ~170 MB |

These timings are for the feature build running in pandas. With the
aggregation pushed down to Snowflake we expect it to be faster, but we have not
measured that.

Single commodity VM. No GPU. No external API. No per-customer cost. The nightly
query does use Hutch's Snowflake compute, so the size of the virtual warehouse
it runs on is Hutch's choice.

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
6. **Snowflake access.** A read-only role for StaySignal, the virtual warehouse
   the nightly query runs on, and the database, schema and view names that back
   the four tables. Also whether OSS and CDR data are landed in Snowflake or
   arrive as separate extracts.

---

## 6. What we are not claiming

- We have not tested this on Hutch data, and nobody should act on the reported
  numbers until it has been.
- We have not connected to Hutch's Snowflake account. The warehouse path is
  tested against SQLite only, and the connection details shown are placeholders.
- We cannot see another operator's traffic. The interference signal says *our
  own load does not explain this*, which is a strong hint and a work order — not
  proof that a named carrier is responsible.
- The market feed needs to be built. Without it, that feature is zero and the
  model degrades gracefully to its previous behaviour on competitor-driven churn.
