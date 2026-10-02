"""
StaySignal — feature engineering. The single source of truth.

train.py, the scoring API and the browser console all build features from this
one file, so a customer is scored identically everywhere. (Training/serving
skew is one of the most common ways a working ML system silently breaks.
Sharing one definition makes it structurally impossible.)

-----------------------------------------------------------------------------
ONE IDEA, APPLIED EVERYWHERE
-----------------------------------------------------------------------------
Nothing is ever judged in absolute terms.

    a customer is compared to their own past
    a cell       is compared to its own past
    a week       is compared to what the whole base did that week
    a traveller  is compared to their own normal travel

8 GB is a lot for one person and nothing for another. 55% congestion is
normal for a Colombo cell and alarming for a rural one. Eight districts in a
week is alarming for an office worker and Tuesday for a sales rep. So every
feature is a ratio or a delta against the right reference, never a raw level.

-----------------------------------------------------------------------------
FEATURE FAMILIES — and the judge question each one exists to answer
-----------------------------------------------------------------------------
  A. Behaviour vs the customer's OWN past        the original idea
  B. Behaviour vs THE WHOLE BASE that week       "what about a holiday dip?"
  C. Presence and mobility                       "what if they are travelling?"
                                                 "what about a sales rep who
                                                  uses different towers daily?"
  D. Network experience on THEIR OWN cells        "how do you KNOW it is the
                                                  network?"
                                                 "what if another operator on a
                                                  shared tower causes this?"
  E. Commercial                                  bill shock, tenure, value
  F. Market context                              "what about Dialog's and
                                                  Mobitel's promotions?"

Three named feature sets are kept so the repository can prove the progression
rather than assert it:

    v1  (4 features)   what we brought to the idea pitch
    v2  (18 features)  after the first technical panel
    v3  (23 features)  after the finalist panel  <- deployed
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


# --- A: vs their own past ---------------------------------------------------
SET_A = ["data_ratio", "opens_ratio", "recharge_ratio", "quota_utilisation"]

# --- B: vs the whole base that week (seasonality cancels out) --------------
SET_B = ["data_ratio_vs_base", "opens_ratio_vs_base"]

# --- C: presence and mobility ---------------------------------------------
SET_C = ["home_cell_share", "home_share_drop", "weeks_since_attach",
         "regions_seen"]
SET_C3 = ["home_share_ratio", "mobility_ratio", "regions_ratio"]   # new in v3

# --- D: network experience on their own cells -----------------------------
SET_D = ["cell_drop_delta", "cell_sinr_delta", "cell_congestion",
         "cell_outage_hours"]
SET_D3 = ["cell_congestion_delta", "cell_interference"]   # new in v3

# --- E: commercial --------------------------------------------------------
SET_E = ["has_overage", "complaints", "tenure_months", "monthly_spend"]

# --- F: market context ----------------------------------------------------
SET_F3 = ["market_pressure"]                           # new in v3

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
    "cell_drop_delta":       "Their tower's call drops (vs its own normal)",
    "cell_sinr_delta":       "Their tower's signal quality loss",
    "cell_congestion":       "Their tower's congestion",
    "cell_congestion_delta": "Their tower's congestion growth",
    "cell_interference":     "Signal loss their tower's own load cannot explain",
    "cell_outage_hours":     "Their tower's outage hours",
    "has_overage":           "Was charged extra",
    "complaints":            "Complaints last month",
    "tenure_months":         "Months with Hutch",
    "monthly_spend":         "Monthly spend",
    "market_pressure":       "Competitor campaign pressure in their district",
}


# ==========================================================================
# CELL BASELINES — every cell judged against its own healthy level
# ==========================================================================
def cell_baselines(cells_df):
    """Per-cell condition, each cell compared to ITS OWN past.

    A cell in a dense city is permanently busier than a rural one. What
    matters is whether a cell got worse than it normally is.

    This function also separates two causes of bad signal that look identical
    in a single SINR number, and which need completely different fixes:

        PRB up   + SINR down  ->  OUR OWN congestion. Add capacity.
        PRB flat + SINR down  ->  interference from OUTSIDE our own traffic.
                                  Towers in Sri Lanka are commonly shared
                                  between operators, so a neighbouring
                                  carrier, or a new obstruction, can degrade
                                  our signal while our own load is unchanged.
                                  Capacity will not fix it; RF planning and
                                  inter-operator coordination will.

    `interference` is the SINR loss that the cell's own extra load cannot
    account for. It is the honest answer to "what if another operator on the
    same tower is causing this?" -- we cannot see their traffic, but we can
    see degradation our traffic does not explain.
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
    """The seasonality fix.

    If everybody's data fell 30% during Avurudu, a customer who fell 30% has
    told us nothing. Only a fall BEYOND the crowd is a signal.

    Note what this does NOT fix: it is a NATIONAL median, so it cancels
    national events (holidays, exam season) but not a regional one -- a
    competitor running a district-level promotion moves one region and barely
    moves the national median. That is exactly why family F exists.

    In production this is computed nightly and stored, so a single customer
    can still be scored on demand through the API.
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

    A judge asked: Dialog or Mobitel runs an aggressive promotion, Hutch
    customers leave, and nothing about our own network or the customer's own
    behaviour explains it. Correct -- and no amount of internal data can see
    it, because the cause is outside Hutch.

    So it is supplied as an EXTERNAL input, one row per district per week.
    In production it is built from two things Hutch already has or can get:

      * MNP port-out requests by district and week. This is the ground truth
        for competitive loss -- Hutch knows exactly who ported out and to whom.
      * Competitor campaign calendar. Promotions are publicly announced, so
        start and end dates are known, not guessed.

    It is deliberately NOT learned from our own churn labels. Using outcomes
    to predict outcomes is leakage; a lagged, externally sourced market index
    is not.
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
    """Weekly rows -> one row of features per customer.

    Always computes every v3 feature, then returns the requested named subset,
    so v1 / v2 / v3 are guaranteed to be built from identical inputs. That is
    what makes the comparison in train.py honest.
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

    # the last week we saw them on the network at all
    seen = w[w.attached == 1].groupby("customer_id").week.max()

    # their own towers' condition, averaged over the cells that actually
    # served them -- not over the whole network
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

    # ---- B: vs the whole base that week  (THE SEASONALITY FIX) -----------
    f["data_ratio_vs_base"] = f["data_ratio"] / max(pop["data"], 1e-6)
    f["opens_ratio_vs_base"] = f["opens_ratio"] / max(pop["opens"], 1e-6)

    # ---- C: presence and mobility  (THE TRAVELLER FIX) -------------------
    f["home_cell_share"] = r.r_home
    f["home_share_drop"] = (b.b_home - r.r_home).clip(lower=0)
    f["weeks_since_attach"] = (WEEKS - seen).reindex(f.index).fillna(WEEKS).clip(upper=12)
    f["regions_seen"] = r.r_regions.reindex(f.index).fillna(1).clip(upper=6)

    # ...and the same signals measured against THEIR OWN normal.
    # A sales rep who always touches ten towers in three districts, and whose
    # busiest single tower only ever holds a quarter of his sessions, is not
    # travelling - that is his Tuesday. An office worker who always touches two
    # towers and suddenly touches ten IS travelling. The absolute counts cannot
    # tell those two apart; the ratios can, because each person is measured
    # against themselves.
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
# SUPPRESSION — flagged is not the same as contacted
# ==========================================================================
# A high score says "this customer's experience is degrading". It does NOT
# automatically mean "spend money on them today".
#
# These rules are deliberately rules rather than learned weights: they are
# business policy, and Hutch must be able to change them without retraining
# anything. A model that cannot be overruled by the business does not get
# deployed by the business.
#
# v2 wrote them against absolute thresholds, and the finalist panel found the
# flaw: a sales representative legitimately uses many towers in many districts
# every week, so the v2 rules classified him as permanently "travelling" and
# held him back forever -- including when he really was leaving. That is a
# silent false negative, which is worse than a wasted offer because nothing
# ever surfaces it.
#
# v3 rewrites every rule against the customer's OWN mobility baseline.
# ==========================================================================
def suppression(features, pop=None, version="v3"):
    """Returns a reason to HOLD, or None to contact."""
    pop_dip = (pop or {}).get("data", 1.0) < 0.85
    out = []

    for _, x in features.iterrows():
        reason = None

        if version == "v2":
            # kept so the regression test in train.py can measure the damage
            if x.home_cell_share < 0.35 and x.weeks_since_attach <= 1:
                reason = "Travelling - still active elsewhere"
            elif x.regions_seen >= 2 and x.home_share_drop > 0.3:
                reason = "Travelling - seen in another district"
            elif pop_dip and x.data_ratio_vs_base > 0.9:
                reason = "Seasonal - whole base is down this week"
        else:
            # 1. Away from THEIR OWN usual footprint, and still attaching.
            #    A ratio, not a level: a rep who normally sits at 0.25 is
            #    untouched, while an office worker falling from 0.95 to 0.30
            #    is caught. Both are judged against themselves.
            if x.home_share_ratio < 0.5 and x.weeks_since_attach <= 1:
                reason = "Travelling - away from usual towers, still active"
            # 2. Covering more districts than they normally do.
            elif x.regions_ratio > 1.5 and x.home_share_ratio < 0.8:
                reason = "Travelling - more districts than their own normal"
            # 3. A national dip the whole base shares.
            elif pop_dip and x.data_ratio_vs_base > 0.9:
                reason = "Seasonal - whole base is down this week"

        out.append(reason)
    return out
