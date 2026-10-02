"""
StaySignal — build the data file the console loads.

    python build_console_data.py        ->  ../frontend/data.js

WHY THE FEATURES ARE COMPUTED HERE AND NOT IN THE BROWSER
---------------------------------------------------------
The console still runs the MODEL live: data.js carries the 24 weights, and
app.js does the standardisation, the weighted sum, the sigmoid and the ranking
of contributions. What it does not do is rebuild the features, because that
would mean a second implementation of features.py written in JavaScript — and
two implementations of the same feature definition drift apart. That is
training/serving skew, which is one of the most common ways a working ML system
silently starts lying.

So this script calls the same `build_features()` that trained the model, and
bakes the resulting vector into the file. The browser receives numbers it could
not have computed differently, and the thing the audience watches happen live —
the score and the reasons behind it — is genuinely the model running.

It also carries, per customer: the suppression decision, the weekly series the
charts draw, and the condition of the specific cell that served them, so the
console can name the tower rather than assert a network problem.
"""
import json
from pathlib import Path

import pandas as pd

from features import (build_features, population_baseline, cell_baselines,
                      suppression, FEATURE_SETS, READABLE, WEEKS, RECENT,
                      HOLIDAY_WEEKS)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend" / "data.js"
V3 = FEATURE_SETS["v3"]

PLAN_PRICES = {"Lite 5GB": 490, "Value 15GB": 990, "Max 40GB": 1790, "Unlimited": 2990}
SMALLER = {"Unlimited": "Max 40GB", "Max 40GB": "Value 15GB",
           "Value 15GB": "Lite 5GB", "Lite 5GB": "Lite 5GB"}
BIGGER = {"Lite 5GB": "Value 15GB", "Value 15GB": "Max 40GB",
          "Max 40GB": "Unlimited", "Unlimited": "Unlimited"}

ACTIONS = {
    "Network problem": "Apologise for the fault, confirm the fix, raise an RF work order",
    "Bill shock": "Explain the extra charge and offer a bigger-value package",
    "Plan too big": "Offer a smaller package that costs less",
    "Plan too small": "Offer a larger package — they are paying for top-ups they don't need to",
    "Competitor offer": "Match the market with a loyalty bonus before they port out",
    "Losing interest": "Offer 5GB free night data with their next reload",
}

OWNERS = {
    "Network problem": "RF / network team",
    "Bill shock": "Retention",
    "Plan too big": "Retention",
    "Plan too small": "Retention",
    "Competitor offer": "Retention",
    "Losing interest": "Marketing",
}

MESSAGES = {
    "Network problem": {
        "English": "Dear Valued Customer,\nWe are currently experiencing an unexpected service disruption due to a technical error. We sincerely apologize for the inconvenience caused. Our technical team is actively working to resolve the issue, and services will be restored as quickly as possible. Thank you. - Hutch",
        "Sinhala": "හිතවත් පාරිභෝගිකය,\nතාක්ෂණික දෝෂයක් හේතුවෙන් දැනට අපගේ සන්නිවේදන සේවාවල බිඳවැටීමක් සිදුවී ඇත. මේ නිසා ඔබට සිදුවන අපහසුතාවයට අපගේ කණගාටුව ප්‍රකාශ කර සිටිමු. අපගේ තාක්ෂණික කණ්ඩායම මේ වන විටත් ගැටලුව නිරාකරණය කිරීමට කටයුතු කරමින් සිටී. ඉතා ඉක්මනින් සේවාව යථා තත්ත්වයට පත් කිරීමට පියවර ගන්නෙමු. ස්තූතියි. - Hutch",
        "Tamil": "அன்பான வாடிக்கையாளரே,\nதொழில்நுட்பக் கோளாறு காரணமாக எங்களது தகவல் தொடர்பு சேவைகளில் திடீர் செயலிழப்பு ஏற்பட்டுள்ளது. இதனால் உங்களுக்கு ஏற்பட்டுள்ள அசௌகரியத்திற்கு எங்களது வருத்தத்தைத் தெரிவித்துக்கொள்கிறோம். எங்களது தொழில்நுட்பக் குழுவினர் இப்பிரச்சினையைச் சரிசெய்ய தற்போது தீவிரமாக ஈடுபட்டுள்ளதோடு, மிக விரைவில் சேவைகள் வழமைக்குக் கொண்டுவரப்படும். நன்றி. - Hutch",
    },
    "Bill shock": {
        "English": "Dear Valued Customer,\nYou spent an extra Rs. {overage}/- on data last month due to exceeding your package limit. Switch to our \"{better_plan}\" package to enjoy more data for the same amount. Reply YES to switch. - Hutch",
        "Sinhala": "හිතවත් පාරිභෝගිකය,\nපසුගිය මාසයේ ඔබගේ ඩේටා සීමාව ඉක්මවීම නිසා අමතරව රු. {overage}/-ක මුදලක් වැයවී ඇත. අපගේ \"{better_plan}\" පැකේජය වෙත මාරු වීමෙන් එම මුදලටම වැඩි ඩේටා ප්‍රමාණයක් ලබාගත හැක. මාරු වීම සඳහා YES ලෙස reply කරන්න. - Hutch",
        "Tamil": "அன்பான வாடிக்கையாளரே,\nகடந்த மாதம் உங்கள் டேட்டா பேக்கேஜ் எல்லை முடிந்ததால், மேலதிகமாக ரூ. {overage}/- வசூலிக்கப்பட்டுள்ளது. எங்களின் \"{better_plan}\" பேக்கேஜிற்கு மாறுவதன் மூலம் அதே தொகைக்கு அதிக டேட்டாவைப் பெற்றுக்கொள்ளலாம். மாற விரும்பினால் YES என reply செய்யவும். - Hutch",
    },
    "Plan too big": {
        "English": "Dear Valued Customer,\nYou utilized only {data_now}GB out of your {quota}GB package last month. Switch to our \"{better_plan}\" package and save Rs. {saving}/- monthly. Reply YES to switch. - Hutch",
        "Sinhala": "හිතවත් පාරිභෝගිකය,\nපසුගිය මාසයේ ඔබගේ {quota}GB පැකේජයෙන් භාවිත කර ඇත්තේ {data_now}GB පමණි. අපගේ \"{better_plan}\" පැකේජය වෙත මාරු වීමෙන් ඔබට මසකට රු. {saving}/-ක මුදලක් ඉතිරි කරගත හැක. මාරු වීම සඳහා YES ලෙස reply කරන්න. - Hutch",
        "Tamil": "அன்பான வாடிக்கையாளரே,\nகடந்த மாதம் உங்கள் {quota}GB பேக்கேஜில் {data_now}GB மட்டுமே பயன்படுத்தப்பட்டுள்ளது. எங்களின் \"{better_plan}\" பேக்கேஜிற்கு மாறி, மாதத்திற்கு ரூ. {saving}/- வரை சேமித்திடுங்கள். மாற விரும்பினால் YES என reply செய்யவும். - Hutch",
    },
    "Plan too small": {
        "English": "Dear Valued Customer,\nYou used {data_now}GB of your {quota}GB package last month and reloaded more than usual. Our \"{better_plan}\" package gives you more data for better value. Reply YES to switch. - Hutch",
        "Sinhala": "හිතවත් පාරිභෝගිකය,\nපසුගිය මාසයේ ඔබගේ {quota}GB පැකේජයෙන් {data_now}GB ක් භාවිත කර, සුපුරුදුට වඩා වැඩියෙන් රීලෝඩ් කර ඇත. අපගේ \"{better_plan}\" පැකේජය මඟින් වඩා වාසිදායක මිලකට වැඩි ඩේටා ප්‍රමාණයක් ලබාගත හැක. මාරු වීම සඳහා YES ලෙස reply කරන්න. - Hutch",
        "Tamil": "அன்பான வாடிக்கையாளரே,\nகடந்த மாதம் உங்கள் {quota}GB பேக்கேஜில் {data_now}GB பயன்படுத்தி, வழக்கத்தை விட அதிகமாக ரீலோட் செய்துள்ளீர்கள். எங்களின் \"{better_plan}\" பேக்கேஜ் மூலம் சிறந்த மதிப்பில் அதிக டேட்டாவைப் பெறலாம். மாற விரும்பினால் YES என reply செய்யவும். - Hutch",
    },
    "Competitor offer": {
        "English": "Dear Valued Customer,\nThank you for staying with Hutch. As a valued customer, enjoy {bonus}GB extra data absolutely free on your next reload. Reply YES to claim. - Hutch",
        "Sinhala": "හිතවත් පාරිභෝගිකය,\nHutch සමඟ රැඳී සිටීම ගැන ඔබට ස්තූතියි. අපගේ විශේෂ පාරිභෝගිකයෙකු ලෙස, ඔබගේ මීළඟ රීලෝඩ් එක සමඟ අමතර {bonus}GB ඩේටා සම්පූර්ණයෙන්ම නොමිලේ ලබාගන්න. ලබාගැනීමට YES ලෙස reply කරන්න. - Hutch",
        "Tamil": "அன்பான வாடிக்கையாளரே,\nHutch உடன் தொடர்ந்து இருப்பதற்கு நன்றி. எங்களின் சிறப்பு வாடிக்கையாளராக, உங்கள் அடுத்த ரீலோடுடன் மேலதிக {bonus}GB டேட்டாவை முற்றிலும் இலவசமாகப் பெற்றுக்கொள்ளுங்கள். பெற YES என reply செய்யவும். - Hutch",
    },
    "Losing interest": {
        "English": "Dear Valued Customer,\nA special offer just to welcome you back! Enjoy an extra 5GB of Night Data completely free with your next reload. Reply YES to activate. - Hutch",
        "Sinhala": "හිතවත් පාරිභෝගිකය,\nඔබව නැවත අප සමඟ සම්බන්ධ කරගැනීම වෙනුවෙන් විශේෂ දීමනාවක්! ඔබගේ මීළඟ රීලෝඩ් එක සමඟ රාත්‍රී කාලය සඳහා අමතර 5GB ඩේටා සම්පූර්ණයෙන්ම නොමිලේ ලබාගන්න. දීමනාව සක්‍රීය කරගැනීමට YES ලෙස reply කරන්න. - Hutch",
        "Tamil": "அன்பான வாடிக்கையாளரே,\nஉங்களை மீண்டும் வரவேற்பதற்கான விசேட சலுகை! உங்களின் அடுத்த ரீலோடுடன் இரவு நேரத்திற்கான மேலதிக 5GB டேட்டாவை முற்றிலும் இலவசமாகப் பெற்றுக்கொள்ளுங்கள். ஆக்டிவேட் செய்ய YES என reply செய்யவும். - Hutch",
    },
}

# Approximate positions on the map, as a fraction of the island's bounding box.
TOWN_XY = {
    "Colombo": [0.24, 0.72], "Gampaha": [0.29, 0.66], "Negombo": [0.22, 0.63],
    "Kandy": [0.47, 0.55], "Kurunegala": [0.37, 0.48], "Galle": [0.36, 0.92],
    "Matara": [0.47, 0.94], "Jaffna": [0.34, 0.03], "Anuradhapura": [0.40, 0.28],
    "Batticaloa": [0.78, 0.50], "Trincomalee": [0.70, 0.31], "Ratnapura": [0.42, 0.78],
}


# --------------------------------------------------------------------------
def diagnose(x, quota_fit):
    """Name the most likely cause from the same features that produced the score.

    Order matters, and it encodes a priority rather than a probability: an
    internal, fixable cause outranks an external one. "Competitor offer" sits
    near the bottom deliberately — it is the residual explanation, used when
    nothing inside Hutch accounts for the drift. Blaming the market first would
    be the comfortable answer and usually the wrong one.

    `quota_fit` is package use measured over the customer's BASELINE window, not
    the recent one. Whether a package is the right size is a structural question
    about the customer, and judging it from a window that contains a national
    holiday would downgrade half the base to a smaller plan every April.
    """
    if x.cell_drop_delta >= 1.0 or x.cell_outage_hours >= 0.5 or x.cell_interference >= 2.0:
        return "Network problem"
    if x.has_overage:
        return "Bill shock"
    if quota_fit >= 0.70:
        return "Plan too small"
    if quota_fit <= 0.22:
        return "Plan too big"
    if x.market_pressure >= 0.30:
        return "Competitor offer"
    return "Losing interest"


def cell_diagnosis(row):
    """Which of the three physically different faults this cell has.

    Congestion and interference are indistinguishable in SINR alone; they
    separate once SINR is read against the cell's OWN load.
    """
    if row.sinr_delta < 1.0 and row.drop_delta < 0.5 and row.outage_hours < 0.5:
        return "healthy", "Operating within its own normal range"
    if row.outage_hours >= 0.5 and row.congestion_delta < -4:
        return "hardware", ("Carrying less traffic than normal with real outage "
                            "minutes — this looks like failing hardware")
    if row.congestion_delta > 12:
        return "congestion", ("Our own traffic outgrew the cell — PRB up "
                              f"{row.congestion_delta:.0f}pp. Capacity, not interference")
    if row.interference >= 2.0:
        return "interference", ("Signal loss our own load does not explain "
                                f"({row.interference:.1f} dB). On a shared site this is "
                                "the external-interference signature — RF planning, "
                                "not capacity")
    return "degraded", "Degraded against its own baseline"


def main():
    w = pd.read_csv(ROOT / "data" / "demo_customers_weekly.csv")
    s = pd.read_csv(ROOT / "data" / "demo_customers_static.csv")
    c = pd.read_csv(ROOT / "data" / "demo_cells_weekly.csv")
    mk = pd.read_csv(ROOT / "data" / "demo_market_weekly.csv")
    model = json.loads((ROOT / "models" / "model.json").read_text())

    # The console's world is the demo base, so its own population baseline is
    # the right reference for "what did everyone else do this week".
    pop = population_baseline(w)
    X = build_features(w, s, c, mk, pop, feature_set="v3")
    holds = suppression(X, pop, version="v3")
    cells = cell_baselines(c)

    static = s.set_index("customer_id")
    recent = w[w.week > WEEKS - RECENT]
    base = w[(w.week >= 5) & (w.week < 17) & (~w.week.isin(HOLIDAY_WEEKS))]
    r = recent.groupby("customer_id").agg(
        data=("data_gb", "mean"), opens=("app_opens", "mean"),
        rec=("recharges", "mean"), cell=("serving_cell", lambda v: v.mode().iat[0]))
    b = base.groupby("customer_id").agg(
        data=("data_gb", "mean"), opens=("app_opens", "mean"),
        rec=("recharges", "mean"))
    series = {cid: g.sort_values("week").data_gb.round(2).tolist()
              for cid, g in w.groupby("customer_id")}

    customers = []
    for cid, x in X.iterrows():
        st = static.loc[cid]
        quota_fit = float(b.loc[cid, "data"]) * 4.33 / max(float(st.data_quota_gb), 1)
        cause = diagnose(x, quota_fit)

        if cause == "Plan too big":
            better = SMALLER[st.plan]
            saving = max(PLAN_PRICES[st.plan] - PLAN_PRICES[better], 0)
        elif cause in ("Bill shock", "Plan too small"):
            better, saving = BIGGER[st.plan], 0
        else:
            better, saving = st.plan, 0

        data_now = float(r.loc[cid, "data"]) * 4.33       # weekly mean -> monthly
        fill = {"overage": int(st.overage_charges_lkr), "better_plan": better,
                "quota": int(st.data_quota_gb), "data_now": round(data_now, 1),
                "saving": saving, "bonus": 5}

        cell_id = r.loc[cid, "cell"]
        crow = cells.loc[cell_id]
        kind, explanation = cell_diagnosis(crow)

        customers.append({
            "id": cid,
            "region": st.region,
            "language": st.language,
            "plan": st.plan,
            "quota": float(st.data_quota_gb),
            "spend": int(st.monthly_spend_lkr),
            "quotaFit": round(quota_fit, 3),
            "months": int(st.months_with_hutch),
            "complaints": int(st.complaints_last_month),
            "overage": int(st.overage_charges_lkr),

            # headline display numbers, monthly so a human can read them
            "dataBefore": round(float(b.loc[cid, "data"]) * 4.33, 1),
            "dataNow": round(data_now, 1),
            "opensBefore": int(round(float(b.loc[cid, "opens"]) * 4.33)),
            "opensNow": int(round(float(r.loc[cid, "opens"]) * 4.33)),
            "gapBefore": round(7 / max(float(b.loc[cid, "rec"]), 0.05), 1),
            "gapNow": round(7 / max(float(r.loc[cid, "rec"]), 0.05), 1),

            # the 24-value feature vector the browser scores — built by the SAME
            # code that trained the model, never re-implemented in JavaScript
            "f": [round(float(x[name]), 6) for name in V3],

            # policy
            "hold": holds[len(customers)],

            # network evidence, so the console can name the tower
            "cell": cell_id,
            "cellKind": kind,
            "cellWhy": explanation,
            "cellDrop": round(float(crow.drop_delta), 2),
            "cellSinr": round(float(crow.sinr_delta), 2),
            "cellPrb": round(float(crow.congestion), 1),
            "cellPrbDelta": round(float(crow.congestion_delta), 1),
            "cellInterference": round(float(crow.interference), 2),
            "cellOutage": round(float(crow.outage_hours), 1),
            # kept for the console's existing label; now derived from real cell
            # KPIs rather than an invented "network dips" column
            "dips": int(round(float(x.cell_drop_delta))),

            # the weekly series the charts draw
            "weekly": series[cid],

            "cause": cause,
            "owner": OWNERS[cause],
            "action": ACTIONS[cause],
            "betterPlan": better,
            "saving": saving,
            "messages": {lang: text.format(**fill)
                         for lang, text in MESSAGES[cause].items()},
        })

    payload = {
        "customers": customers,
        "model": model,
        "townXY": TOWN_XY,
        "meta": {
            "weeks": WEEKS,
            "recent": RECENT,
            "holidayWeeks": sorted(HOLIDAY_WEEKS),
            "populationBaseline": pop,
            "readable": {k: READABLE[k] for k in V3},
            "note": "Simulated data. Scores are computed in the browser from the "
                    "exported weights; features come from ml/features.py.",
        },
    }

    OUT.write_text("// Generated by ml/build_console_data.py - do not edit by hand.\n"
                   "window.STAYSIGNAL = "
                   + json.dumps(payload, ensure_ascii=False) + ";\n",
                   encoding="utf-8")

    print(f"Wrote {len(customers)} customers to {OUT.relative_to(ROOT)}")
    print(f"  population baseline  data {pop['data']:.3f}  opens {pop['opens']:.3f}")
    counts = pd.Series([c["cause"] for c in customers]).value_counts()
    print("  causes:")
    for cause, n in counts.items():
        print(f"    {cause:<18} {n}")
    held = [c for c in customers if c["hold"]]
    print(f"  held back by policy: {len(held)}")
    kinds = pd.Series([c["cellKind"] for c in customers]).value_counts()
    print("  serving-cell condition: " +
          "  ".join(f"{k}={v}" for k, v in kinds.items()))


if __name__ == "__main__":
    main()
