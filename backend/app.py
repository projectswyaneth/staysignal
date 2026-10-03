"""
StaySignal — scoring API.

The browser console scores customers client-side so the prototype can run as a
static page with no backend. In production the model belongs behind an API
inside the operator's network; this module is that service.

    uvicorn app:app --reload --port 8000      (from the backend/ directory)
    http://localhost:8000/docs                 interactive documentation

Endpoints
    GET  /health      is the service up, and which model is loaded
    GET  /model       the model card: features, weights, threshold, accuracy
    POST /score       score one customer and explain the score
    POST /score/batch score many at once — this is the realistic call

-----------------------------------------------------------------------------
HOW THIS SERVICE THINKS ABOUT ITS INPUTS
-----------------------------------------------------------------------------
Three of the model's feature families are not properties of a customer at all:

    the population baseline   is a property of the WHOLE BASE that week
    cell condition            is a property of the NETWORK
    market pressure           is a property of a DISTRICT

A request therefore cannot carry them, and should not try. They are reference
state, computed by the nightly job and loaded here at start-up — exactly as they
would be in production, where this service reads them from the same warehouse
the batch job writes to. A request carries only what is genuinely about the
customer: their static record and their weekly history.

That split is also what keeps the service honest. If the caller could supply the
population baseline, a caller could change it, and every score in the system
would become unreproducible.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ml"))

# the exact feature code the model was trained with — never a re-implementation
from features import (build_features, population_baseline,      # noqa: E402
                      suppression, READABLE)

MODEL_PATH = ROOT / "models" / "model.json"
DATA = ROOT / "data"


# ---------------------------------------------------------------- start-up
def _load_model() -> dict:
    if not MODEL_PATH.exists():
        raise RuntimeError(f"No model at {MODEL_PATH}. Run `python ml/train.py` first.")
    return json.loads(MODEL_PATH.read_text())


def _load_reference() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Network and market state, plus the population baseline.

    In production these come from the warehouse the nightly job writes. Here
    they come from the generated tables, which is the same contract.
    """
    cells = pd.read_csv(DATA / "cells_weekly.csv")
    market = pd.read_csv(DATA / "market_weekly.csv")
    model = MODEL
    pop = model.get("population_baseline")
    if not pop:
        pop = population_baseline(pd.read_csv(DATA / "customers_weekly.csv"))
    return cells, market, pop


MODEL = _load_model()
CELLS, MARKET, POP = _load_reference()
FEATURES: list[str] = MODEL["features"]


# ---------------------------------------------------------------- schemas
class WeeklyRow(BaseModel):
    week: int = Field(..., ge=1, le=520)
    data_gb: float = Field(..., ge=0)
    app_opens: int = Field(0, ge=0)
    recharges: float = Field(..., ge=0)
    voice_minutes: float = Field(0, ge=0)
    serving_cell: str
    home_cell_share: float = Field(..., ge=0, le=1)
    distinct_cells: int = Field(1, ge=1)
    distinct_regions: int = Field(1, ge=1)
    attached: int = Field(1, ge=0, le=1)


class Customer(BaseModel):
    customer_id: str
    region: str
    plan: str
    data_quota_gb: float = Field(..., gt=0)
    monthly_spend_lkr: float = Field(..., ge=0)
    months_with_hutch: int = Field(..., ge=0)
    overage_charges_lkr: float = 0
    complaints_last_month: int = 0
    language: str = "English"
    weekly: list[WeeklyRow] = Field(..., min_length=17,
                                    description="At least 17 weeks. A customer "
                                                "with less history has no baseline "
                                                "window of their own and is not "
                                                "scored.")


class Contribution(BaseModel):
    feature: str
    readable: str
    value: float
    contribution: float


class Score(BaseModel):
    customer_id: str
    risk: float
    score: int
    flagged: bool
    hold_reason: str | None
    action: str
    top_reasons: list[Contribution]
    model_version: str


# ---------------------------------------------------------------- scoring
def _score_frame(statics: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    X = build_features(weekly, statics, CELLS, MARKET, POP,
                       feature_set="v3")[FEATURES]
    import numpy as np
    z = (MODEL["intercept"]
         + ((X.values - MODEL["mean"]) / MODEL["scale"]) @ MODEL["coefficients"])
    X = X.copy()
    X["_risk"] = 1 / (1 + np.exp(-z))
    return X


def _unpack(customers: list[Customer]) -> tuple[pd.DataFrame, pd.DataFrame]:
    statics, weekly = [], []
    for c in customers:
        d = c.model_dump()
        rows = d.pop("weekly")
        statics.append(d)
        for r in rows:
            weekly.append({"customer_id": c.customer_id, **r})
    return pd.DataFrame(statics), pd.DataFrame(weekly)


def _explain(row: pd.Series, n: int = 4) -> list[Contribution]:
    out = []
    for i, name in enumerate(FEATURES):
        standardised = (row[name] - MODEL["mean"][i]) / MODEL["scale"][i]
        out.append(Contribution(
            feature=name, readable=READABLE.get(name, name),
            value=round(float(row[name]), 4),
            contribution=round(float(MODEL["coefficients"][i] * standardised), 4)))
    out.sort(key=lambda c: abs(c.contribution), reverse=True)
    return out[:n]


def _action(flagged: bool, hold: str | None) -> str:
    if not flagged:
        return "no action"
    if hold:
        return f"hold — {hold}"
    return "contact with the offer matching the top reason"


# ---------------------------------------------------------------- app
app = FastAPI(
    title="StaySignal scoring API",
    version=MODEL["model"],
    description="Customer Experience Management for prepaid. Runs inside the "
                "operator's network; no customer data leaves, and no LLM is "
                "called at any point.",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


@app.get("/health", tags=["service"])
def health():
    return {
        "status": "ok",
        "model": MODEL["model"],
        "features": len(FEATURES),
        "threshold": MODEL["threshold"],
        "reference_state": {
            "cells": int(CELLS.cell_id.nunique()),
            "districts": int(MARKET.region.nunique()),
            "population_baseline": POP,
        },
    }


@app.get("/model", tags=["service"])
def model_card():
    """Everything needed to audit a score, including every weight.

    The model is published in full on purpose: a system that claims to be
    explainable should not hide its coefficients.
    """
    return {
        "model": MODEL["model"],
        "trained_on": MODEL["trained_on"],
        "test_roc_auc": MODEL["test_roc_auc"],
        "threshold": MODEL["threshold"],
        "intercept": MODEL["intercept"],
        "weights": [
            {"feature": f, "readable": READABLE.get(f, f),
             "weight": round(w, 4)}
            for f, w in zip(FEATURES, MODEL["coefficients"])
        ],
        "notes": "Trained on simulated data. Retrain on Hutch extracts before use.",
    }


@app.post("/score", response_model=Score, tags=["scoring"])
def score_one(customer: Customer):
    return score_many([customer])[0]


@app.post("/score/batch", response_model=list[Score], tags=["scoring"])
def score_many(customers: list[Customer]):
    if not customers:
        raise HTTPException(400, "No customers supplied.")
    if len(customers) > 10_000:
        raise HTTPException(413, "Batch limit is 10,000 customers.")

    statics, weekly = _unpack(customers)
    unknown = set(weekly.serving_cell) - set(CELLS.cell_id)
    if unknown:
        raise HTTPException(
            422, f"{len(unknown)} serving cells are not in the OSS reference "
                 f"({sorted(unknown)[:5]}...). Scoring a customer with no network "
                 f"evidence would silently treat their towers as healthy.")

    X = _score_frame(statics, weekly)
    holds = suppression(X[FEATURES], POP, version="v3")

    out = []
    for (cid, row), hold in zip(X.iterrows(), holds):
        risk = float(row["_risk"])
        flagged = risk >= MODEL["threshold"]
        out.append(Score(
            customer_id=str(cid),
            risk=round(risk, 4),
            score=round(risk * 100),
            flagged=flagged,
            hold_reason=hold,
            action=_action(flagged, hold),
            top_reasons=_explain(row),
            model_version=MODEL["model"],
        ))
    return out
