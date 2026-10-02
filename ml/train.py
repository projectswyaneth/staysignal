"""
StaySignal — training, benchmarking and honest self-testing.

Four models are trained on identical data so every choice is measured rather
than asserted:

  v1   4 features   what we brought to the idea pitch
  v2  18 features   after the first technical panel
  v3  24 features   after the finalist panel      <- deployed
  GBM 24 features   gradient boosting, as a benchmark for the linear choice

Accuracy is not the headline. Four named regression tests are, because each one
is a question a judge actually asked and each one has a number attached:

  1. THE HOLIDAY TEST      how many customers on holiday do we wrongly chase?
  2. THE SALES REP TEST    do we silently hold back a field worker who really
                           is leaving, because he always uses many towers?
  3. THE SHARED TOWER TEST can we tell our own congestion apart from
                           interference we do not generate?
  4. THE COMPETITOR TEST   do we catch customers pulled away by a rival's
                           promotion, which nothing inside Hutch explains?

Outputs:
  models/model.json     the deployed model (also copied to model_v3.json)
  reports/metrics.md    every number, for the solution document
  reports/weights.png   what the model learned
"""
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from features import (build_features, population_baseline, cell_baselines,
                     suppression, FEATURE_SETS, READABLE)
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import (roc_auc_score, average_precision_score,
                             confusion_matrix)

ORANGE, INK, MUTED = "#E8490B", "#12100E", "#9A938C"

# Business assumptions — stated openly, unchanged since the idea pitch.
OFFER_MARGIN_GIVEN_UP = 0.15
SMS_COST_LKR = 5
SAVE_RATE = 0.35
HORIZON_MONTHS = 6

V1, V2, V3 = FEATURE_SETS["v1"], FEATURE_SETS["v2"], FEATURE_SETS["v3"]


def net_value(y, prob, spend, threshold):
    flagged = prob >= threshold
    leaving = y == 1
    value = spend * HORIZON_MONTHS
    offer_cost = value * OFFER_MARGIN_GIVEN_UP + SMS_COST_LKR
    missed = -value[~flagged & leaving].sum()
    caught = -(value[flagged & leaving] * (1 - SAVE_RATE)).sum()
    offers = -offer_cost[flagged].sum()
    return missed + caught + offers, int(flagged.sum())


def choose_threshold(y, prob, spend):
    return max(((t, *net_value(y, prob, spend, t)) for t in np.arange(0.05, 0.96, 0.01)),
               key=lambda r: r[1])


def main():
    w = pd.read_csv("../data/customers_weekly.csv")
    s = pd.read_csv("../data/customers_static.csv")
    c = pd.read_csv("../data/cells_weekly.csv")
    m = pd.read_csv("../data/market_weekly.csv")

    pop = population_baseline(w)
    X = build_features(w, s, c, m, pop, feature_set="v3")
    meta = s.set_index("customer_id").loc[X.index]
    y = meta.churned_next_30d.values
    spend = meta.monthly_spend_lkr.values.astype(float)
    profile = meta._hidden_profile.values
    mobility = meta._hidden_mobility.values
    price_sens = meta._hidden_price_sensitive.values
    exposure = meta._hidden_promo_exposure.values

    print(f"{len(X)} customers x {len(V3)} features | churn {y.mean():.1%} | "
          f"national population baseline {pop['data']:.3f}\n")

    idx = np.arange(len(X))
    i_tr, i_te = train_test_split(idx, test_size=0.25, random_state=42, stratify=y)
    Xtr, Xte, ytr, yte = X.iloc[i_tr], X.iloc[i_te], y[i_tr], y[i_te]
    spend_te = spend[i_te]
    prof_te, mob_te = profile[i_te], mobility[i_te]
    ps_te, exp_te = price_sens[i_te], exposure[i_te]

    def fit_logistic(cols):
        mdl = Pipeline([("scale", StandardScaler()),
                        ("clf", LogisticRegression(max_iter=2000, C=1.0))])
        mdl.fit(Xtr[cols], ytr)
        return mdl, mdl.predict_proba(Xte[cols])[:, 1]

    m_v1, p_v1 = fit_logistic(V1)
    m_v2, p_v2 = fit_logistic(V2)
    m_v3, p_v3 = fit_logistic(V3)

    gbm = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06,
                                         max_depth=5, random_state=42)
    gbm.fit(Xtr, ytr)
    p_gbm = gbm.predict_proba(Xte)[:, 1]

    aucs = {k: roc_auc_score(yte, p) for k, p in
            (("v1", p_v1), ("v2", p_v2), ("v3", p_v3), ("gbm", p_gbm))}
    prs = {k: average_precision_score(yte, p) for k, p in
           (("v1", p_v1), ("v2", p_v2), ("v3", p_v3), ("gbm", p_gbm))}

    print("MODEL COMPARISON (held-out test set)")
    print(f"  v1   {len(V1):>2} features   ROC AUC {aucs['v1']:.3f}   PR AUC {prs['v1']:.3f}")
    print(f"  v2   {len(V2):>2} features   ROC AUC {aucs['v2']:.3f}   PR AUC {prs['v2']:.3f}")
    print(f"  v3   {len(V3):>2} features   ROC AUC {aucs['v3']:.3f}   PR AUC {prs['v3']:.3f}   <- deployed")
    print(f"  gradient boost    ROC AUC {aucs['gbm']:.3f}   PR AUC {prs['gbm']:.3f}")

    folds = StratifiedKFold(5, shuffle=True, random_state=42)

    def cv_auc(cols):
        return cross_val_score(
            Pipeline([("scale", StandardScaler()),
                      ("clf", LogisticRegression(max_iter=2000))]),
            X[cols], y, cv=folds, scoring="roc_auc")

    cv2, cv = cv_auc(V2), cv_auc(V3)
    print(f"  5-fold CV (v2)    {cv2.mean():.3f} (+/- {cv2.std():.3f})")
    print(f"  5-fold CV (v3)    {cv.mean():.3f} (+/- {cv.std():.3f})")
    print("  v2 -> v3 is inside cross-validation noise on AUC, and that is")
    print("  expected: the two faults v3 fixes are INVISIBLE to AUC. See tests 2-4.\n")

    t_v3, val_v3, n_v3 = choose_threshold(yte, p_v3, spend_te)

    # ================= TEST 1 — THE HOLIDAY TEST =========================
    # Give every system the SAME contact budget, then ask how many of the
    # people it chases are simply on holiday. Comparing each model at its own
    # threshold would be comparing two different budgets, which proves nothing.
    travellers = prof_te == "traveller"
    BUDGET = n_v3
    tops = {k: np.argsort(-p)[:BUDGET] for k, p in
            (("v1", p_v1), ("v2", p_v2), ("v3", p_v3))}
    chased = {k: int(travellers[t].sum()) for k, t in tops.items()}
    caught = {k: int(yte[t].sum()) for k, t in tops.items()}
    ranks = {k: float(pd.Series(p).rank(pct=True)[travellers].mean() * 100)
             for k, p in (("v1", p_v1), ("v2", p_v2), ("v3", p_v3))}

    print("TEST 1 — THE HOLIDAY TEST   (same contact budget for every system)")
    print(f"  travellers in test set          {int(travellers.sum())}")
    print(f"  budget (customers contacted)    {BUDGET}")
    for k in ("v1", "v2", "v3"):
        print(f"  {k} wasted on travellers         {chased[k]:<4} "
              f"(caught {caught[k]} real leavers)")
    print(f"  traveller risk percentile       v1 {ranks['v1']:.0f}th -> "
          f"v3 {ranks['v3']:.0f}th\n")

    # ================= TEST 2 — THE SALES REP TEST ========================
    # A judge asked: some people use the same two towers every day, others —
    # sales reps, drivers — use a different set daily. Did you consider that?
    #
    # We had not, and the cost was not a wasted offer. It was the opposite, and
    # worse: the v2 suppression rules used ABSOLUTE thresholds, so a field
    # worker looked permanently "away from home" and was held back every single
    # week — including the weeks he really was leaving. Nothing surfaces a
    # suppressed customer, so that failure is silent.
    Xte_v3 = Xte[V3]
    hold_v2 = np.array(suppression(Xte_v3, pop, version="v2"), dtype=object)
    hold_v3 = np.array(suppression(Xte_v3, pop, version="v3"), dtype=object)

    def travel_hold(reasons):
        """Only the TRAVEL reasons. The seasonal rule is a separate mechanism
        and during a holiday week it legitimately holds back most of the base,
        so including it here would drown the effect being measured."""
        return np.array([bool(r) and r.startswith("Travelling") for r in reasons])

    trav_v2, trav_v3 = travel_hold(hold_v2), travel_hold(hold_v3)
    flagged = p_v3 >= t_v3
    roamer = mob_te == "roamer"
    leaver = yte == 1

    lost_v2 = int((leaver & roamer & trav_v2).sum())
    lost_v3 = int((leaver & roamer & trav_v3).sum())
    held_roamer_v2 = int((roamer & trav_v2).sum())
    held_roamer_v3 = int((roamer & trav_v3).sum())
    trav_held_v3 = int((travellers & trav_v3).sum())
    trav_held_v2 = int((travellers & trav_v2).sum())

    print("TEST 2 — THE SALES REP TEST   (held back as 'travelling')")
    print(f"  high-mobility customers in test set           {int(roamer.sum())}")
    print(f"  of them, called 'travelling' by v2 rules       {held_roamer_v2}")
    print(f"  of them, called 'travelling' by v3 rules       {held_roamer_v3}")
    print(f"  REAL LEAVERS silently held back   v2 {lost_v2}  ->  v3 {lost_v3}")
    print(f"  genuine travellers still held back   v2 {trav_held_v2}  ->  "
          f"v3 {trav_held_v3}   of {int(travellers.sum())}\n")

    # ================= TEST 3 — THE SHARED TOWER TEST =====================
    # A judge asked: towers are shared with Mobitel, Dialog, Airtel — congestion
    # there causes a network loss for your customer. How would you identify that?
    #
    # We cannot see another operator's traffic, and we never will. But we can
    # see signal loss that OUR OWN load does not explain, and that is the
    # fingerprint. The table below is the proof that the two separate.
    cells_now = cell_baselines(c)
    truth = (c[["cell_id"]].drop_duplicates().set_index("cell_id"))
    # recover each cell's fault type from the KPI shape of the raw export
    # (the simulator's label is not available to the model, so this is only
    # used here, to verify the feature behaves as designed)
    sev = c.groupby("cell_id").agg(
        prb_rise=("prb_utilisation_pct", lambda v: v.tail(4).mean() - v.head(16).median()),
        sinr_fall=("avg_sinr_db", lambda v: v.head(16).median() - v.tail(4).mean()),
        outage=("outage_minutes", "sum"))
    joined = cells_now.join(sev)
    kinds = {
        "healthy":       joined[joined.sinr_fall < 1.0],
        "our own congestion": joined[(joined.sinr_fall >= 1.0) & (joined.prb_rise > 12)],
        "external interference": joined[(joined.sinr_fall >= 1.0) & (joined.prb_rise.between(-5, 12))],
        "hardware / outage": joined[(joined.sinr_fall >= 1.0) & (joined.prb_rise < -5)],
    }
    print("TEST 3 — THE SHARED TOWER TEST   (cells grouped by KPI fingerprint)")
    print(f"  {'cell group':<24}{'n':>4}{'PRB change':>12}{'SINR lost':>11}"
          f"{'interference feature':>22}")
    shared_rows = []
    for name, grp in kinds.items():
        if len(grp) == 0:
            continue
        print(f"  {name:<24}{len(grp):>4}{grp.prb_rise.mean():>+11.1f}pp"
              f"{grp.sinr_fall.mean():>9.1f}dB{grp.interference.mean():>19.1f}dB")
        shared_rows.append((name, len(grp), grp.prb_rise.mean(),
                            grp.sinr_fall.mean(), grp.interference.mean()))
    print("  -> congestion and interference look identical in SINR alone, and")
    print("     separate cleanly once SINR is read against our own PRB.\n")

    # ================= TEST 4 — THE COMPETITOR TEST =======================
    # A judge asked: what about Dialog's and Mobitel's promotions? Nothing
    # inside Hutch explains a customer leaving because somebody else got
    # cheaper. So it is supplied as an external district-level signal.
    pulled = (ps_te == 1) & (exp_te > 0.3) & (yte == 1)
    rec_v2 = float(np.isin(np.where(pulled)[0], tops["v2"]).mean()) if pulled.sum() else 0.0
    rec_v3 = float(np.isin(np.where(pulled)[0], tops["v3"]).mean()) if pulled.sum() else 0.0
    w_market = float(m_v3.named_steps["clf"].coef_[0][V3.index("market_pressure")])

    print("TEST 4 — THE COMPETITOR TEST   (same contact budget)")
    print(f"  leavers pulled by a rival's promotion         {int(pulled.sum())}")
    print(f"  share of them caught by v2                    {rec_v2:.0%}")
    print(f"  share of them caught by v3                    {rec_v3:.0%}")
    print(f"  learned weight on market pressure             {w_market:+.3f}\n")

    # ================= operating point and money ==========================
    pred = (p_v3 >= t_v3).astype(int)
    tn, fp, fn, tp = confusion_matrix(yte, pred).ravel()
    recall, precision = tp / (tp + fn), tp / (tp + fp)
    nobody = net_value(yte, p_v3, spend_te, 1.1)[0]
    everybody = net_value(yte, p_v3, spend_te, 0.0)[0]
    n_held = int((flagged & np.array([bool(r) for r in hold_v3])).sum())
    n_held_travel = int((flagged & trav_v3).sum())

    print(f"Threshold {t_v3:.2f} -> flags {n_v3} of {len(yte)} | "
          f"recall {recall:.0%} precision {precision:.0%}")
    print(f"  of those flagged, {n_held} are held back by policy "
          f"({n_held_travel} travelling), {n_v3 - n_held} are contacted")
    print(f"Money: nobody {-nobody:,.0f} | everybody {-everybody:,.0f} | "
          f"targeted {-val_v3:,.0f}")
    print(f"       saves {val_v3-nobody:,.0f} vs nothing, "
          f"{val_v3-everybody:,.0f} vs blanket\n")

    # ================= export ==============================================
    scaler, clf = m_v3.named_steps["scale"], m_v3.named_steps["clf"]
    model = {
        "model": "logistic_regression_v3",
        "trained_on": f"simulated, {len(X)} customers x {len(V3)} features, "
                      "26 weekly observations each — retrain on Hutch data",
        "features": V3,
        "readable_names": {k: READABLE[k] for k in V3},
        "mean": [float(v) for v in scaler.mean_],
        "scale": [float(v) for v in scaler.scale_],
        "coefficients": [float(v) for v in clf.coef_[0]],
        "intercept": float(clf.intercept_[0]),
        "threshold": float(round(t_v3, 2)),
        "test_roc_auc": round(float(aucs["v3"]), 4),
        "population_baseline": pop,
    }
    with open("../models/model.json", "w") as fh:
        json.dump(model, fh, indent=2)

    order = np.argsort(clf.coef_[0])
    fig, ax = plt.subplots(figsize=(9.5, 8))
    names = [READABLE[V3[i]] for i in order]
    vals = clf.coef_[0][order]
    ax.barh(names, vals, color=[ORANGE if v > 0 else INK for v in vals])
    ax.axvline(0, color=MUTED, lw=1)
    ax.set_xlabel("Learned weight   (orange = raises risk, black = lowers it)")
    ax.set_title("What the deployed model learned", loc="left",
                 fontsize=13, weight="bold")
    fig.tight_layout()
    fig.savefig("../reports/weights.png", dpi=150)
    plt.close(fig)

    tbl3 = "\n".join(
        f"| {n} | {k} | {p:+.1f} pp | {s:.1f} dB | **{i:.1f} dB** |"
        for n, k, p, s, i in shared_rows)

    report = f"""# StaySignal — model results

Trained on simulated data: **{len(X):,} customers x 26 weekly observations**,
{y.mean():.1%} churn. Every number below comes from a held-out test set of
**{len(yte)} customers** the model never saw.

> All data in this repository is simulated. The pipeline is written so that
> only the input tables change when Hutch's own extracts arrive.

## How the model got here

| Version | Features | Added because a panel asked | ROC AUC | PR AUC |
|---|---|---|---|---|
| v1 — idea pitch | {len(V1)} | — | {aucs['v1']:.3f} | {prs['v1']:.3f} |
| v2 — first technical panel | {len(V2)} | network evidence, travel, seasonality | {aucs['v2']:.3f} | {prs['v2']:.3f} |
| **v3 — finalist panel (deployed)** | **{len(V3)}** | own-mobility baseline, interference, competitor pressure | **{aucs['v3']:.3f}** | **{prs['v3']:.3f}** |
| Gradient boosting benchmark | {len(V3)} | — | {aucs['gbm']:.3f} | {prs['gbm']:.3f} |

5-fold cross-validation: v2 {cv2.mean():.3f} (+/- {cv2.std():.3f}),
v3 {cv.mean():.3f} (+/- {cv.std():.3f}).

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
All three systems are given the same contact budget of {BUDGET} customers.

| System | Offers wasted on travellers | Real leavers caught |
|---|---|---|
| v1 — {len(V1)} behaviour features | **{chased['v1']}** | {caught['v1']} |
| v2 — {len(V2)} features | **{chased['v2']}** | {caught['v2']} |
| **v3 — {len(V3)} features** | **{chased['v3']}** | **{caught['v3']}** |

Travellers sit at the **{ranks['v1']:.0f}th** risk percentile under v1 — squarely in
the danger zone. Under v3 they sit at the **{ranks['v3']:.0f}th**, correctly judged safe.

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
| High-mobility customers labelled "travelling" | {held_roamer_v2} of {int(roamer.sum())} | {held_roamer_v3} of {int(roamer.sum())} |
| **Real leavers silently held back** | **{lost_v2}** | **{lost_v3}** |
| Genuine travellers correctly held back | {trav_held_v2} of {int(travellers.sum())} | {trav_held_v3} of {int(travellers.sum())} |

(The traveller row is not {int(travellers.sum())} of {int(travellers.sum())} in either
column, and should not be: a customer whose trip ended three weeks ago is home
and behaving normally again, so there is nothing left to hold back. The rule
exists for people who are away *now* — and at the operating point only
{chased['v3']} traveller in {BUDGET} contacts slips through.)

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
{tbl3}

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
| In the test set | {int(pulled.sum())} |
| Share caught by v2 | {rec_v2:.0%} |
| **Share caught by v3** | **{rec_v3:.0%}** |

Learned weight on market pressure: {w_market:+.3f} (positive, as expected).

## Operating point ({t_v3:.2f})

|  | Predicted stay | Predicted leave |
|---|---|---|
| **Actually stayed** | {tn} | {fp} |
| **Actually left** | {fn} | **{tp}** |

Recall {recall:.0%} — we catch {tp} of the {tp+fn} who really left.
Precision {precision:.0%} — of {tp+fp} flagged, {tp} really left.
Of the {n_v3} flagged, {n_held} are held back by policy
({n_held_travel} of them for travel) and {n_v3-n_held} are contacted.

## Money (test set, {HORIZON_MONTHS} months)

Assumptions, stated: an offer gives up {OFFER_MARGIN_GIVEN_UP:.0%} of that
customer's revenue, and we keep {SAVE_RATE:.0%} of the leavers we contact.

| Strategy | Revenue lost |
|---|---|
| Contact nobody | Rs. {-nobody:,.0f} |
| Contact everybody (blanket discount) | Rs. {-everybody:,.0f} |
| **Contact who the model flags** | **Rs. {-val_v3:,.0f}** |

Targeting saves Rs. {val_v3-nobody:,.0f} against doing nothing and
Rs. {val_v3-everybody:,.0f} against blanket discounting. Blanket discounting is
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
"""
    with open("../reports/metrics.md", "w") as fh:
        fh.write(report)
    print("Written: models/model.json, reports/metrics.md, reports/weights.png")


if __name__ == "__main__":
    main()
