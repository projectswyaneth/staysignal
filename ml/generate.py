"""
StaySignal — data generator.

Builds FOUR tables that mirror what a real operator already holds. The field
names and value ranges follow standard telecom KPI definitions, so the schema
matches what Hutch would export rather than something invented for a demo:

  1. data/cells_weekly.csv       per-cell network KPIs, one row per cell per week
                                 -> an OSS / NMS export
  2. data/customers_weekly.csv   per-customer behaviour + serving-cell footprint
                                 -> CDR / xDR joined to recharge and app logs
  3. data/customers_static.csv   plan, tenure, region, spend, labels
                                 -> prepaid data warehouse
  4. data/market_weekly.csv      competitor campaign pressure by district
                                 -> MNP port-out reports + public promo calendar

Everything here is SIMULATED, and that is stated wherever a number appears.
The point of the simulator is not to pretend to be Hutch's data. It is to
contain, deliberately, every trap the judges asked about, so the fixes can be
MEASURED rather than claimed:

    a national holiday inside the scoring window     weeks 24-25
    customers who travel and are not leaving         ~12% of the base
    cells that genuinely degrade, with three causes  ~16% of cells
    high-mobility customers (sales reps, drivers)    ~9% of the base
    a competitor promotion in four districts         weeks 24-26

Usage:
    python generate.py          -> 4000 customers, seed 42  (training)
    python generate.py demo     -> 150 customers,  seed 7   (console)
"""
import sys
import numpy as np
import pandas as pd

DEMO = len(sys.argv) > 1 and sys.argv[1] == "demo"
RNG = np.random.default_rng(7 if DEMO else 42)

WEEKS = 26                       # six months of history
N_CUSTOMERS = 150 if DEMO else 4000
SUFFIX = "demo_" if DEMO else ""

RECENT = 4                       # weeks 23-26 are "now"
BASE_FROM, BASE_TO = 5, 17       # weeks 5..16 are the customer's own baseline

# A national holiday INSIDE the recent window. Every customer's usage falls.
# This is the trap the idea-pitch model fell straight into.
HOLIDAY_WEEKS = {23, 24}
HOLIDAY_FACTOR = 0.62

# A competitor (think Dialog or Mobitel) runs a hard data promotion in four
# districts. Price-sensitive customers there become more likely to leave for
# reasons that have nothing to do with Hutch's network or their own habits.
PROMO_WEEKS = {24, 25, 26}
PROMO_REGIONS = ["Gampaha", "Kandy", "Negombo", "Kurunegala"]
PROMO_INTENSITY = 0.72

REGIONS = ["Colombo", "Gampaha", "Kandy", "Galle", "Matara", "Jaffna",
           "Kurunegala", "Anuradhapura", "Batticaloa", "Negombo",
           "Ratnapura", "Trincomalee"]
CELLS_PER_REGION = 12            # 144 cells, which is a plausible small region set

LANGUAGE_BY_REGION = {
    "Jaffna": ["Tamil", "Tamil", "English"],
    "Batticaloa": ["Tamil", "Tamil", "English"],
    "Trincomalee": ["Tamil", "Sinhala", "English"],
    "Colombo": ["Sinhala", "English", "Tamil"],
}
DEFAULT_LANGUAGES = ["Sinhala", "Sinhala", "English"]

PLANS = {
    "Lite 5GB":   {"quota": 5,   "price": 490},
    "Value 15GB": {"quota": 15,  "price": 990},
    "Max 40GB":   {"quota": 40,  "price": 1790},
    "Unlimited":  {"quota": 100, "price": 2990},
}
PLAN_NAMES = list(PLANS)

# Hidden behaviours. The model never sees this column.
# "traveller" exists because travellers look exactly like leavers on the
# original features and must NOT be flagged.
#
# "plan_too_small" is the mirror image of plan_too_big and it is not primarily a
# churn case at all: these customers are heavy users capped by a package that is
# too small for them, so they reload more often than they should have to. Left
# alone they drift, but the right action is an UPSELL rather than a discount —
# the same detection machinery finding revenue instead of protecting it.
PROFILES = ["healthy", "network", "bill_shock", "plan_too_big", "bored",
            "traveller", "plan_too_small"]
PROFILE_WEIGHTS = [0.39, 0.13, 0.10, 0.10, 0.09, 0.12, 0.07]

# How a customer moves around, independent of why they might leave. A sales
# rep can be healthy or can be leaving; mobility is not a churn profile, which
# is exactly why a model must not treat it as one.
#   static   — one tower, mostly at home
#   commuter — home and work, two or three towers, same district
#   roamer   — sales reps, drivers, field staff: many towers, several districts
MOBILITY = ["static", "commuter", "roamer"]
MOBILITY_WEIGHTS = [0.34, 0.57, 0.09]


# ===========================================================================
# 1. THE NETWORK — per-cell weekly KPIs (what an OSS export looks like)
# ===========================================================================
# Three physically different ways a cell goes bad. They need different fixes,
# and - crucially - they leave different fingerprints across PRB and SINR:
#
#   congestion    our own traffic outgrew the cell. PRB up a lot, SINR down a
#                 little, drops up. Fix: add capacity / carrier.
#   interference   something outside our own traffic is degrading the signal.
#                 SINR down hard while PRB barely moves. On a shared or
#                 co-located site this is the signature of a neighbouring
#                 operator's carrier, or a new physical obstruction.
#                 Fix: RF re-planning and inter-operator coordination.
#   hardware       a faulty or partly failed cell. It carries LESS traffic than
#                 normal while quality collapses, with real outage minutes.
#                 Fix: a truck roll.
FAULT_TYPES = ["congestion", "interference", "hardware"]
FAULT_WEIGHTS = [0.45, 0.35, 0.20]


def build_cells():
    rows, meta = [], {}
    for region in REGIONS:
        for n in range(CELLS_PER_REGION):
            cell_id = f"{region[:3].upper()}_{n+1:02d}"

            # each cell's own healthy baseline
            base_drop = float(np.clip(RNG.normal(0.45, 0.14), 0.12, 1.0))   # %
            base_sinr = float(np.clip(RNG.normal(14.5, 2.6), 7, 22))        # dB
            base_prb = float(np.clip(RNG.normal(44, 13), 12, 78))           # %
            base_ho = float(np.clip(RNG.normal(98.6, 0.7), 95, 99.8))       # %

            # ~16% of cells develop a real fault partway through the window
            faulty = RNG.random() < 0.16
            fault_type = str(RNG.choice(FAULT_TYPES, p=FAULT_WEIGHTS)) if faulty else "none"
            fault_week = int(RNG.integers(16, 23)) if faulty else 99
            severity = float(RNG.uniform(3.0, 7.0)) if faulty else 0.0

            # Tower sharing is normal in Sri Lanka. A cell on a shared or
            # co-located site is physically more exposed to another operator's
            # carrier, so interference faults concentrate there. We record the
            # flag because Hutch's own site database has it -- we are not
            # guessing which towers are shared.
            shared_site = bool(RNG.random() < 0.38 or fault_type == "interference")

            meta[cell_id] = {"region": region, "faulty": faulty,
                             "fault_type": fault_type, "fault_week": fault_week,
                             "severity": severity, "shared_site": shared_site}

            for w in range(1, WEEKS + 1):
                degraded = w >= fault_week
                ramp = min((w - fault_week + 1) / 3.0, 1.0) if degraded else 0.0
                sev = severity * ramp

                drop = base_drop
                sinr = base_sinr
                prb = base_prb
                ho = base_ho
                outage = 0.0

                if fault_type == "congestion":
                    prb += 26 * ramp
                    sinr -= 0.62 * sev          # a busy cell is a bit noisier
                    drop += 0.55 * sev
                    ho -= 0.40 * sev
                elif fault_type == "interference":
                    prb += 2.0 * ramp           # our own load barely changes
                    sinr -= 1.05 * sev          # but the signal gets much worse
                    drop += 0.80 * sev
                    ho -= 0.70 * sev
                elif fault_type == "hardware":
                    prb -= 11 * ramp            # it is carrying LESS, not more
                    sinr -= 0.55 * sev
                    drop += 1.05 * sev
                    ho -= 0.95 * sev
                    if degraded and RNG.random() < 0.55:
                        outage = float(RNG.uniform(60, 420))

                rows.append({
                    "cell_id": cell_id,
                    "region": region,
                    "week": w,
                    "shared_site": int(shared_site),
                    "call_drop_rate_pct": round(float(np.clip(drop + RNG.normal(0, 0.06), 0.05, 12)), 3),
                    "avg_sinr_db": round(float(np.clip(sinr + RNG.normal(0, 0.6), -2, 25)), 2),
                    "prb_utilisation_pct": round(float(np.clip(prb + RNG.normal(0, 4), 5, 99)), 1),
                    "handover_success_pct": round(float(np.clip(ho + RNG.normal(0, 0.25), 80, 99.9)), 2),
                    "outage_minutes": round(outage, 0),
                })
    return pd.DataFrame(rows), meta


# ===========================================================================
# 2. THE MARKET — competitor pressure by district and week
# ===========================================================================
def build_market():
    """One row per district per week.

    In production this table is built from MNP port-out reports (Hutch knows
    exactly how many numbers left each district, and to which operator) plus
    the competitor campaign calendar, which is public. Here it is simulated.
    """
    rows = []
    for region in REGIONS:
        for w in range(1, WEEKS + 1):
            promo = (region in PROMO_REGIONS and w in PROMO_WEEKS)
            intensity = (PROMO_INTENSITY * RNG.uniform(0.85, 1.12)) if promo \
                else float(abs(RNG.normal(0.05, 0.03)))
            intensity = float(np.clip(intensity, 0.0, 1.0))
            # port-out rate is the observable consequence of that pressure
            port_out = 0.28 + 2.4 * intensity + float(RNG.normal(0, 0.08))
            rows.append({
                "region": region,
                "week": w,
                "competitor_promo_intensity": round(intensity, 3),
                "port_out_rate_pct": round(max(port_out, 0.0), 3),
            })
    return pd.DataFrame(rows)


def promo_exposure(region):
    """Mean competitor pressure this district felt during the recent window."""
    if region not in PROMO_REGIONS:
        return 0.05
    overlap = len([w for w in PROMO_WEEKS if w > WEEKS - RECENT])
    return (PROMO_INTENSITY * overlap + 0.05 * (RECENT - overlap)) / RECENT


# ===========================================================================
# 3. THE CUSTOMERS — weekly behaviour, mobility footprint, serving cell
# ===========================================================================
def build_customer(i, cells_meta, cell_ids_by_region):
    profile = str(RNG.choice(PROFILES, p=PROFILE_WEIGHTS))
    if profile == "network":
        # a network-caused churner must actually be served by a degrading cell,
        # otherwise the label has no cause behind it
        faulty_cells = [c for c, m in cells_meta.items() if m["faulty"]]
        home_cell = str(RNG.choice(faulty_cells))
        region = cells_meta[home_cell]["region"]
    else:
        region = str(RNG.choice(REGIONS))
        home_cell = str(RNG.choice(cell_ids_by_region[region]))

    plan = str(RNG.choice(PLAN_NAMES, p=[0.30, 0.34, 0.24, 0.12]))
    quota = PLANS[plan]["quota"]
    price = PLANS[plan]["price"]
    languages = LANGUAGE_BY_REGION.get(region, DEFAULT_LANGUAGES)
    tenure = int(RNG.integers(2, 73))

    # --- how this person moves around, independent of why they may leave ---
    mobility = str(RNG.choice(MOBILITY, p=MOBILITY_WEIGHTS))
    if mobility == "static":
        usual_cells, usual_regions = RNG.uniform(1.0, 1.6), 1.0
        home_share_norm = float(RNG.uniform(0.88, 0.97))
    elif mobility == "commuter":
        usual_cells, usual_regions = RNG.uniform(2.0, 3.4), float(RNG.choice([1.0, 1.0, 1.4]))
        home_share_norm = float(RNG.uniform(0.55, 0.78))
    else:                                   # roamer: sales rep, driver, field staff
        usual_cells, usual_regions = RNG.uniform(6.0, 13.0), float(RNG.uniform(2.1, 3.4))
        home_share_norm = float(RNG.uniform(0.18, 0.34))

    # price sensitivity decides who a competitor promotion can actually pull
    price_sensitive = bool(RNG.random() < 0.35)
    exposure = promo_exposure(region)

    # Healthy WEEKLY level for this person. The quota is a MONTHLY allowance,
    # so the weekly figure is scaled by 4.33 weeks per month — without that, a
    # "share of package used" feature reads about 1.8 for everybody, which is
    # both wrong and quietly misleading, since it implies the entire base is
    # permanently over its quota.
    base_gb = float(np.clip(RNG.normal(quota * 0.42, quota * 0.16) / 4.33,
                            0.05, quota * 1.15 / 4.33))
    base_opens = float(np.clip(RNG.normal(9, 3.4), 1, 26))
    base_recharges = float(np.clip(RNG.normal(1.25, 0.4), 0.3, 3.2))
    base_voice = float(np.clip(RNG.normal(42, 18), 3, 130))

    # a traveller is away for a block of recent weeks
    away_from = int(RNG.integers(21, 24)) if profile == "traveller" else 99
    away_to = away_from + int(RNG.integers(2, 4))
    away_region = str(RNG.choice([r for r in REGIONS if r != region]))
    away_cell = str(RNG.choice(cell_ids_by_region[away_region]))

    fault_week = cells_meta[home_cell]["fault_week"]

    weekly = []
    overage_total = 0.0
    complaints_total = 0

    for w in range(1, WEEKS + 1):
        gb_mult, open_mult, rec_mult = 1.0, 1.0, 1.0
        serving_cell = home_cell
        home_share = home_share_norm * RNG.uniform(0.94, 1.06)
        cells_touched = usual_cells * RNG.uniform(0.82, 1.18)
        regions_touched = usual_regions * RNG.uniform(0.85, 1.15)
        away_flag = 0

        # --- national holiday: affects EVERYBODY --------------------------
        if w in HOLIDAY_WEEKS:
            gb_mult *= HOLIDAY_FACTOR
            open_mult *= HOLIDAY_FACTOR + 0.08
            rec_mult *= 0.80

        # --- competitor promotion in their district -----------------------
        # Price-sensitive customers try the rival SIM, so Hutch recharges dip
        # in those districts only. A NATIONAL population baseline cannot see
        # this, which is why market pressure is its own feature.
        if price_sensitive and w in PROMO_WEEKS and region in PROMO_REGIONS:
            rec_mult *= 0.80
            gb_mult *= 0.86

        # --- travelling: away, but STILL ACTIVE on other cells ------------
        if away_from <= w <= away_to:
            serving_cell, away_flag = away_cell, 1
            home_share = float(RNG.uniform(0.02, 0.12))
            cells_touched = max(cells_touched * RNG.uniform(0.9, 1.6), 2.0)
            regions_touched = max(regions_touched + RNG.uniform(0.8, 1.8), 2.0)
            gb_mult *= RNG.uniform(0.42, 0.68)      # less data on holiday
            open_mult *= RNG.uniform(0.45, 0.75)
            rec_mult *= RNG.uniform(0.45, 0.80)

        # --- the real churn drivers, in the recent window ------------------
        recent = w > WEEKS - 8
        if profile == "network" and w >= fault_week:
            hit = min((w - fault_week + 1) / 3.0, 1.0)
            gb_mult *= 1 - 0.55 * hit
            open_mult *= 1 - 0.45 * hit
            rec_mult *= 1 - 0.35 * hit
            if RNG.random() < 0.10:
                complaints_total += 1
        elif profile == "bill_shock" and recent:
            gb_mult *= 0.55
            rec_mult *= 0.70
            if w == WEEKS - 7:
                overage_total = float(RNG.uniform(180, 900))
            if RNG.random() < 0.07:
                complaints_total += 1
        elif profile == "plan_too_big":
            gb_mult *= 0.22
        elif profile == "plan_too_small":
            # heavy user on a package that caps them: they use their whole
            # allowance and top up more often to keep going
            gb_mult *= 1.85
            rec_mult *= 1.35
        elif profile == "bored" and recent:
            fade = (w - (WEEKS - 8)) / 8.0
            gb_mult *= 1 - 0.42 * fade
            open_mult *= 1 - 0.50 * fade
            rec_mult *= 1 - 0.40 * fade

        data_gb = max(float(RNG.normal(base_gb * gb_mult, base_gb * 0.12)), 0.0)
        opens = max(int(round(RNG.normal(base_opens * open_mult, 1.6))), 0)
        recharges = max(float(RNG.normal(base_recharges * rec_mult, 0.22)), 0.0)
        voice = max(float(RNG.normal(base_voice * gb_mult, base_voice * 0.18)), 0.0)

        # someone who is leaving stops attaching at all; a traveller does not
        attached = 1 if (data_gb > 0.02 or recharges > 0.05 or voice > 0.5) else 0

        weekly.append({
            "customer_id": f"HUT{100000 + i}",
            "week": w,
            "data_gb": round(data_gb, 3),
            "app_opens": opens,
            "recharges": round(recharges, 2),
            "voice_minutes": round(voice, 1),
            "serving_cell": serving_cell,
            "home_cell_share": round(float(np.clip(home_share, 0.01, 1.0)), 3),
            "distinct_cells": int(max(round(cells_touched), 1)),
            "distinct_regions": int(max(round(regions_touched), 1)),
            "away_from_home_region": away_flag,
            "attached": attached,
        })

    static = {
        "customer_id": f"HUT{100000 + i}",
        "region": region,
        "home_cell": home_cell,
        "language": str(RNG.choice(languages)),
        "plan": plan,
        "data_quota_gb": quota,
        "monthly_spend_lkr": int(price * RNG.uniform(0.92, 1.30)),
        "months_with_hutch": tenure,
        "overage_charges_lkr": round(overage_total, 0),
        "complaints_last_month": complaints_total,
        "_hidden_profile": profile,
        "_hidden_mobility": mobility,
        "_hidden_price_sensitive": int(price_sensitive),
        "_hidden_promo_exposure": round(exposure, 3),
    }
    return static, weekly


# ===========================================================================
# 4. THE LABEL — who actually goes silent in the next 30 days
# ===========================================================================
def true_churn_probability(static, weekly, cells_meta):
    """Hidden and non-linear. The model never sees this function.

    Two design choices matter more than any coefficient here:

      TRAVELLING AND THE HOLIDAY DO NOT CAUSE CHURN. Usage falls, but nobody
      is leaving. A model that only watches "did usage fall" will flag them,
      waste money, and deserve to.

      MOBILITY DOES NOT CAUSE CHURN EITHER. A sales rep is no more and no less
      likely to leave than anyone else. So any system that treats "many towers"
      as evidence - in either direction - is reading noise.
    """
    df = pd.DataFrame(weekly)
    # Whether someone is really leaving must not depend on a public holiday,
    # so holiday weeks are excluded from BOTH windows here. The MODEL does not
    # get that luxury: it has to work the holiday out for itself from the
    # population baseline, which is precisely what we are testing.
    recent = df[(df.week > WEEKS - RECENT) & (~df.week.isin(HOLIDAY_WEEKS))]
    base = df[(df.week >= BASE_FROM) & (df.week < BASE_TO)]
    base_clean = base[~base.week.isin(HOLIDAY_WEEKS)]
    data_ratio = recent.data_gb.mean() / max(base_clean.data_gb.mean(), 0.05)
    opens_ratio = recent.app_opens.mean() / max(base_clean.app_opens.mean(), 0.5)
    rec_ratio = recent.recharges.mean() / max(base_clean.recharges.mean(), 0.05)

    # how bad did their own cells get?
    cells = recent.serving_cell.unique()
    fault = np.mean([cells_meta[c]["severity"] for c in cells]) if len(cells) else 0.0

    logit = -3.18
    logit += 1.30 * np.tanh((1.0 - data_ratio) * 2.0)
    logit += 1.00 * np.tanh((1.0 - opens_ratio) * 2.0)
    logit += 1.15 * np.tanh((1.0 - rec_ratio) * 2.2)
    logit += 0.15 * min(fault, 7.0)
    logit += 0.36 * min(static["complaints_last_month"], 3)
    logit += 0.55 * (static["overage_charges_lkr"] > 0)
    logit -= 0.012 * min(static["months_with_hutch"], 72)

    # bad signal AND falling usage is much worse than either alone
    if fault >= 2.5 and data_ratio < 0.75:
        logit += 0.80

    # a rival's promotion in their district pulls the price-sensitive
    logit += 1.45 * static["_hidden_promo_exposure"] * static["_hidden_price_sensitive"]

    # Being capped by too small a package is deliberately given NO churn effect.
    # It is an upsell opportunity, not a churn risk, and pretending otherwise
    # would inflate our own numbers by relabelling revenue as rescue. The same
    # detection machinery surfaces both; only the action differs.

    # A TRAVELLER IS NOT LEAVING. Their numbers fell because they were away.
    if static["_hidden_profile"] == "traveller":
        logit -= 2.35

    logit += RNG.normal(0, 0.55)
    return 1.0 / (1.0 + np.exp(-logit))


# ===========================================================================
def main():
    print(f"Generating {'DEMO' if DEMO else 'TRAINING'} data - "
          f"{N_CUSTOMERS} customers x {WEEKS} weeks\n")

    cells_df, cells_meta = build_cells()
    market_df = build_market()
    cell_ids_by_region = {r: [c for c, m in cells_meta.items() if m["region"] == r]
                          for r in REGIONS}

    faulty = [m for m in cells_meta.values() if m["faulty"]]
    by_type = pd.Series([m["fault_type"] for m in faulty]).value_counts()
    print(f"Cells: {len(cells_meta)}   rows: {len(cells_df):,}")
    print(f"  degrading cells: {len(faulty)}  " +
          "  ".join(f"{k}={v}" for k, v in by_type.items()))
    print(f"  on shared / co-located sites: "
          f"{sum(1 for m in cells_meta.values() if m['shared_site'])}")
    print(f"Market table: {len(market_df)} rows  "
          f"(competitor promo in {', '.join(PROMO_REGIONS)}, weeks "
          f"{min(PROMO_WEEKS)}-{max(PROMO_WEEKS)})")

    statics, weeklies = [], []
    for i in range(N_CUSTOMERS):
        s, w = build_customer(i, cells_meta, cell_ids_by_region)
        p = true_churn_probability(s, w, cells_meta)
        s["churned_next_30d"] = int(RNG.random() < p)
        statics.append(s)
        weeklies.extend(w)

    static_df = pd.DataFrame(statics)
    weekly_df = pd.DataFrame(weeklies)

    cells_df.to_csv(f"../data/{SUFFIX}cells_weekly.csv", index=False)
    market_df.to_csv(f"../data/{SUFFIX}market_weekly.csv", index=False)
    static_df.to_csv(f"../data/{SUFFIX}customers_static.csv", index=False)
    weekly_df.to_csv(f"../data/{SUFFIX}customers_weekly.csv", index=False)

    rate = static_df.churned_next_30d.mean()
    print(f"\nCustomer rows: {len(weekly_df):,}")
    print(f"Churn rate: {rate:.1%}  ({static_df.churned_next_30d.sum()} left)\n")

    print("Churn rate by hidden profile (the model never sees this):")
    g = static_df.groupby("_hidden_profile")["churned_next_30d"].agg(["mean", "size"])
    for prof, r in g.sort_values("mean", ascending=False).iterrows():
        flag = "   <-- looks like churn but is NOT" if prof == "traveller" else ""
        print(f"  {prof:<14} {r['mean']:>6.1%}   n={int(r['size']):<5}{flag}")

    print("\nChurn rate by mobility class (should be roughly FLAT - how far "
          "someone travels\nfor work is not a reason to leave):")
    g = static_df.groupby("_hidden_mobility")["churned_next_30d"].agg(["mean", "size"])
    for mob, r in g.iterrows():
        print(f"  {mob:<14} {r['mean']:>6.1%}   n={int(r['size']):<5}")

    print("\nCompetitor promotion effect (price-sensitive customers only):")
    ps = static_df[static_df._hidden_price_sensitive == 1]
    inside = ps[ps.region.isin(PROMO_REGIONS)].churned_next_30d.mean()
    outside = ps[~ps.region.isin(PROMO_REGIONS)].churned_next_30d.mean()
    print(f"  in promo districts      {inside:>6.1%}")
    print(f"  elsewhere               {outside:>6.1%}")

    print(f"\nWritten to data/{SUFFIX}*.csv")


if __name__ == "__main__":
    main()
