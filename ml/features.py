"""
Feature engineering for StaySignal — the single definition used everywhere.

train.py, the scoring API and the browser console all build features from this
module, so a customer is scored identically in training and in serving. A second
implementation would allow the two to drift apart, which is a common and silent
failure mode in deployed models.

Design principle: no quantity is used in absolute form.

    a customer is measured against their own history
    a cell       is measured against its own history
    a week       is measured against the whole base that week
    mobility     is measured against that customer's own usual mobility

Absolute levels are not comparable across subjects. 8 GB/month is heavy use for
one subscriber and light for another; 55% PRB utilisation is routine for a dense
urban cell and abnormal for a rural one; twelve distinct cells per week is
unusual for an office worker and normal for a field worker. Every feature is
therefore a ratio or a delta against the appropriate reference.

Feature families
----------------
  A  behaviour vs the customer's own history
  B  behaviour vs the whole base that week   (removes seasonality)
  C  presence and mobility
  D  network experience on the cells that served them
  E  commercial attributes
  F  market context

Three named feature sets are kept so the effect of each family can be measured
rather than assumed:

    v1  (4 features)   behaviour only
    v2  (18 features)  adds population baseline, presence, network
    v3  (24 features)  adds own-mobility baselines, interference, market  <- deployed
"""
import numpy as np
import pandas as pd

WEEKS = 26
RECENT = 4                       # weeks 23-26 are "now"
BASE_FROM, BASE_TO = 5, 17       # weeks 5-16 are the customer's own baseline
HOLIDAY_WEEKS = {23, 24}         # a national holiday INSIDE the recent window

# How much SINR loss a cell's OWN extra load can reasonably explain, per
# percentage point of PRB utilisation growth. Anything beyond this is not our
# congestion -- it is external. See cell_baselines().
SINR_DB_PER_PRB_POINT = 0.22


# --- A: behaviour vs the customer's own history -----------------------------
SET_A = ["data_ratio", "opens_ratio", "recharge_ratio", "quota_utilisation"]

# --- B: behaviour vs the whole base that week (removes seasonality) --------
SET_B = ["data_ratio_vs_base", "opens_ratio_vs_base"]

# --- C: presence and mobility ---------------------------------------------
SET_C = ["home_cell_share", "home_share_drop", "weeks_since_attach",
         "regions_seen"]
SET_C3 = ["home_share_ratio", "mobility_ratio", "regions_ratio"]   # v3

# --- D: network experience on their own cells -----------------------------
SET_D = ["cell_drop_delta", "cell_sinr_delta", "cell_congestion",
         "cell_outage_hours"]
SET_D3 = ["cell_congestion_delta", "cell_interference"]   # v3

# --- E: commercial --------------------------------------------------------
SET_E = ["has_overage", "complaints", "tenure_months", "monthly_spend"]

# --- F: market context ----------------------------------------------------
SET_F3 = ["market_pressure"]                           # v3

FEATURE_SETS = {
    "v1": SET_A,
    "v2": SET_A + SET_B + SET_C + SET_D + SET_E,
    "v3": SET_A + SET_B + SET_C + SET_C3 + SET_D + SET_D3 + SET_E + SET_F3,
}
FEATURE_NAMES = FEATURE_SETS["v3"]          # everything build_features returns

READABLE = {
    "data_ratio":            "Data use vs own past",
    "opens_ratio":           "App opens vs own past",
    "recharge_ratio":        "Reloads vs own past",
    "quota_utilisation":     "Share of package used",
    "data_ratio_vs_base":    "Data drop vs everyone else",
    "opens_ratio_vs_base":   "App drop vs everyone else",
    "home_cell_share":       "Time on home tower",
    "home_share_drop":       "Drop in time at home",
    "weeks_since_attach":    "Weeks since last seen on network",
    "regions_seen":          "Districts visited",
    "home_share_ratio":      "Time at home vs own normal",
    "mobility_ratio":        "Towers visited vs own normal",
    "regions_ratio":         "Districts visited vs own normal",
    "cell_drop_delta":       "Their tower's call drops vs its normal",
    "cell_sinr_delta":       "Their tower's signal quality loss",
    "cell_congestion":       "Their tower's congestion",
    "cell_congestion_delta": "Their tower's congestion growth",
    "cell_interference":     "Unexplained signal loss on their tower",
    "cell_outage_hours":     "Their tower's outage hours",
    "has_overage":           "Was charged extra",
    "complaints":            "Complaints last month",
    "tenure_months":         "Months with Hutch",
    "monthly_spend":         "Monthly spend",
    "market_pressure":       "Competitor pressure in their district",
}


# ==========================================================================
# CELL BASELINES — each cell measured against its own healthy level
# ==========================================================================
def cell_baselines(cells_df):
    """Per-cell condition, each cell measured against its own history.

    Dense urban cells are permanently busier than rural ones, so only the change
    relative to a cell's own healthy level is informative.

    The function also separates two causes of signal degradation that are
    indistinguishable in SINR alone and require different remedies:

        PRB up   + SINR down  ->  congestion from our own traffic. Add capacity.
        PRB flat + SINR down  ->  degradation our own load does not account for.
                                  Typical of external interference, including a
                                  neighbouring operator's carrier on a shared or
                                  co-located site, or a new obstruction.
                                  Requires RF planning, not capacity.

    `interference` is the SINR loss not explained by the cell's own increase in
    load. Another operator's traffic is not observable to us; degradation our own
    traffic does not explain is.
    """
    base = cells_df[cells_df.week < BASE_TO].groupby("cell_id").agg(
        base_drop=("call_drop_rate_pct", "median"),
        base_sinr=("avg_sinr_db", "median"),
        base_prb=("prb_utilisation_pct", "median"),
    )
    recent = cells_df[cells_df.week > WEEKS - RECENT].groupby("cell_id").agg(
        now_drop=("call_drop_rate_pct", "mean"),
        now_sinr=("avg_sinr_db", "mean"),
        now_prb=("prb_utilisation_pct", "mean"),
        outage_min=("outage_minutes", "sum"),
    )
    c = base.join(recent)
    c["drop_delta"] = c.now_drop - c.base_drop            # percentage points worse
    c["sinr_delta"] = c.base_sinr - c.now_sinr            # dB of quality lost
    c["congestion"] = c.now_prb                           # absolute busy-ness
    c["congestion_delta"] = c.now_prb - c.base_prb        # how much busier it got
    c["outage_hours"] = c.outage_min / 60.0

    explained = SINR_DB_PER_PRB_POINT * c.congestion_delta.clip(lower=0)
    c["interference"] = (c.sinr_delta - explained).clip(lower=0)

    return c[["drop_delta", "sinr_delta", "congestion", "congestion_delta",
              "interference", "outage_hours"]]


# ==========================================================================
# POPULATION BASELINE — what the whole base did each week
# ==========================================================================
def population_baseline(weekly_df):
    """Median behaviour of the whole base, per week.

    Removes seasonality. If every subscriber's usage falls 30% during a public
    holiday, a 30% fall carries no information; only a fall beyond the population
    median does.

    Scope: this is a NATIONAL median. It cancels national events but not a
    regional one — a district-level competitor campaign moves one region and
    barely moves the national median. Family F covers that case.

    In production this is computed once per nightly run and stored, so a single
    customer can still be scored on demand through the API.
    """
    per_week = weekly_df.groupby("week").agg(
        pop_data=("data_gb", "median"),
        pop_opens=("app_opens", "median"),
    )
    base = per_week[(per_week.index >= BASE_FROM) & (per_week.index < BASE_TO)]
    recent = per_week[per_week.index > WEEKS - RECENT]
    return {
        "data": float(recent.pop_data.mean() / max(base.pop_data.mean(), 1e-6)),
        "opens": float(recent.pop_opens.mean() / max(base.pop_opens.mean(), 1e-6)),
    }


# ==========================================================================
# MARKET PRESSURE — competitor activity, by district and week
# ==========================================================================
def market_pressure(market_df):
    """Competitive pressure per district over the recent window.

    Churn caused by a rival's promotion has no internal explanation: the cause is
    outside the operator. It therefore enters as an external input, one row per
    district per week, built in production from:

      * MNP port-out requests by district and week — measured ground truth for
        competitive loss, including the receiving operator.
      * The competitor campaign calendar, which is publicly announced, so start
        and end dates are known rather than estimated.

    It is deliberately not derived from our own churn labels; using outcomes to
    predict outcomes is leakage. A lagged, externally sourced index is not.
    """
    if market_df is None or len(market_df) == 0:
        return None
    recent = market_df[market_df.week > WEEKS - RECENT]
    return recent.groupby("region").competitor_promo_intensity.mean()


# ==========================================================================
# BUILD
# ==========================================================================
def build_features(weekly_df, static_df, cells_df, market_df=None,
                   pop=None, feature_set="v3"):
    """Weekly rows -> one feature row per customer.

    Always computes the full v3 set, then returns the requested named subset, so
    v1 / v2 / v3 are guaranteed to be built from identical inputs.
    """
    cells = cell_baselines(cells_df)
    if pop is None:
        pop = population_baseline(weekly_df)
    market = market_pressure(market_df)

    w = weekly_df
    recent = w[w.week > WEEKS - RECENT]
    base = w[(w.week >= BASE_FROM) & (w.week < BASE_TO)
             & (~w.week.isin(HOLIDAY_WEEKS))]

    r = recent.groupby("customer_id").agg(
        r_data=("data_gb", "mean"), r_opens=("app_opens", "mean"),
        r_rec=("recharges", "mean"), r_home=("home_cell_share", "mean"),
        r_cells=("distinct_cells", "mean"), r_regions=("distinct_regions", "mean"),
    )
    b = base.groupby("customer_id").agg(
        b_data=("data_gb", "mean"), b_opens=("app_opens", "mean"),
        b_rec=("recharges", "mean"), b_home=("home_cell_share", "mean"),
        b_cells=("distinct_cells", "mean"), b_regions=("distinct_regions", "mean"),
    )

    # last week the subscriber attached to the network at all
    seen = w[w.attached == 1].groupby("customer_id").week.max()

    # condition of the cells that actually served this subscriber, averaged
    # over the recent window -- not a network-wide average
    rc = recent.join(cells, on="serving_cell")
    net = rc.groupby("customer_id").agg(
        drop_delta=("drop_delta", "mean"), sinr_delta=("sinr_delta", "mean"),
        congestion=("congestion", "mean"),
        congestion_delta=("congestion_delta", "mean"),
        interference=("interference", "mean"),
        outage_hours=("outage_hours", "mean"),
    )

    s = static_df.set_index("customer_id")
    f = pd.DataFrame(index=s.index)

    # ---- A: vs their own past --------------------------------------------
    f["data_ratio"] = r.r_data / b.b_data.clip(lower=0.05)
    f["opens_ratio"] = r.r_opens / b.b_opens.clip(lower=0.5)
    f["recharge_ratio"] = r.r_rec / b.b_rec.clip(lower=0.05)
    f["quota_utilisation"] = (r.r_data * 4.33) / s.data_quota_gb.clip(lower=1)

    # ---- B: vs the whole base that week ----------------------------------
    f["data_ratio_vs_base"] = f["data_ratio"] / max(pop["data"], 1e-6)
    f["opens_ratio_vs_base"] = f["opens_ratio"] / max(pop["opens"], 1e-6)

    # ---- C: presence and mobility ----------------------------------------
    f["home_cell_share"] = r.r_home
    f["home_share_drop"] = (b.b_home - r.r_home).clip(lower=0)
    f["weeks_since_attach"] = (WEEKS - seen).reindex(f.index).fillna(WEEKS).clip(upper=12)
    f["regions_seen"] = r.r_regions.reindex(f.index).fillna(1).clip(upper=6)

    # The same signals measured against each customer's own usual mobility.
    # Absolute counts cannot distinguish a habitually high-mobility subscriber
    # (field staff, drivers) from one who has temporarily left their usual
    # footprint; ratios against the subscriber's own baseline can.
    f["home_share_ratio"] = (r.r_home / b.b_home.clip(lower=0.02)).clip(upper=3)
    f["mobility_ratio"] = (r.r_cells / b.b_cells.clip(lower=0.5)).clip(upper=6)
    f["regions_ratio"] = (r.r_regions / b.b_regions.clip(lower=0.5)).clip(upper=6)

    # ---- D: network experience on their own cells ------------------------
    f["cell_drop_delta"] = net.drop_delta.reindex(f.index).fillna(0).clip(0, 8)
    f["cell_sinr_delta"] = net.sinr_delta.reindex(f.index).fillna(0).clip(0, 12)
    f["cell_congestion"] = net.congestion.reindex(f.index).fillna(45).clip(0, 100)
    f["cell_congestion_delta"] = net.congestion_delta.reindex(f.index).fillna(0).clip(-20, 40)
    f["cell_interference"] = net.interference.reindex(f.index).fillna(0).clip(0, 12)
    f["cell_outage_hours"] = net.outage_hours.reindex(f.index).fillna(0).clip(0, 24)

    # ---- E: commercial ---------------------------------------------------
    f["has_overage"] = (s.overage_charges_lkr > 0).astype(int)
    f["complaints"] = s.complaints_last_month.clip(upper=4)
    f["tenure_months"] = s.months_with_hutch.clip(upper=72)
    f["monthly_spend"] = s.monthly_spend_lkr

    # ---- F: market context ----------------------------------------------
    if market is not None:
        f["market_pressure"] = s.region.map(market).fillna(0.0)
    else:
        f["market_pressure"] = 0.0

    return f[FEATURE_SETS[feature_set]].fillna(0)


# ==========================================================================
# SUPPRESSION — a high score is not by itself an instruction to spend
# ==========================================================================
# A high score indicates a degrading customer experience. Whether to act on it
# is a commercial decision, so these are rules rather than learned weights: the
# operator must be able to change retention policy without retraining a model,
# and must be able to explain why a given customer was or was not contacted.
#
# All thresholds are relative. Absolute thresholds misclassify subscribers whose
# normal footprint is wide — a field worker's share of sessions on his modal cell
# is permanently low, so an absolute rule marks him as travelling in every week,
# including weeks in which he is genuinely churning. Suppression produces no
# alert, so that error is not visible in any accuracy metric; the v2 ruleset is
# retained below only so the regression test in train.py can quantify it.
# ==========================================================================
def suppression(features, pop=None, version="v3", last_contact_days=None,
                fatigue_days=30):
    """Returns a reason to HOLD, or None to contact.

    `last_contact_days` maps customer_id -> days since that customer was last
    contacted, read from the contact ledger. Where it is absent the fatigue rule
    cannot fire, which is the case for the simulated data: it contains no
    campaign history, because no campaign has been run against it.
    """
    pop_dip = (pop or {}).get("data", 1.0) < 0.85
    recent = last_contact_days or {}
    out = []

    for cid, x in features.iterrows():
        reason = None

        # Contact fatigue outranks every other rule: whatever else is true about
        # this customer, sending a second message inside the window makes the
        # first one less likely to be read, not more.
        since = recent.get(cid)
        if since is not None and since < fatigue_days:
            out.append(f"Contacted {int(since)} days ago - inside the "
                       f"{fatigue_days}-day window")
            continue

        if version == "v2":
            # retained for the regression test in train.py
            if x.home_cell_share < 0.35 and x.weeks_since_attach <= 1:
                reason = "Travelling - still active elsewhere"
            elif x.regions_seen >= 2 and x.home_share_drop > 0.3:
                reason = "Travelling - seen in another district"
            elif pop_dip and x.data_ratio_vs_base > 0.9:
                reason = "Seasonal - whole base is down this week"
        else:
            # 1. Away from their own usual footprint, and still attaching.
            #    A ratio, not a level, so a subscriber whose normal share is
            #    0.25 is unaffected while one falling from 0.95 to 0.30 is not.
            if x.home_share_ratio < 0.5 and x.weeks_since_attach <= 1:
                reason = "Travelling - away from usual towers, still active"
            # 2. Covering more districts than their own usual range.
            elif x.regions_ratio > 1.5 and x.home_share_ratio < 0.8:
                reason = "Travelling - more districts than their own normal"
            # 3. A base-wide dip.
            elif pop_dip and x.data_ratio_vs_base > 0.9:
                reason = "Seasonal - whole base is down this week"

        out.append(reason)
    return out
