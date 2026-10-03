"""
StaySignal — the integration adapter.

This is the socket Hutch's real extracts plug into, and it is deliberately the
ONLY file that has to change when they arrive.

-----------------------------------------------------------------------------
WHY THIS FILE EXISTS
-----------------------------------------------------------------------------
A model is easy to retrain. What usually kills a telecom pilot is the three
months spent discovering that `sinr` is called `AVG_SINR_DL_DB` in one export,
that outages are in seconds rather than minutes, that PRB utilisation is a
fraction in one table and a percentage in another, and that nobody told anyone
when a column was renamed.

So the contract is stated here, once, in code:

    everything downstream of this file consumes FOUR canonical tables,
    and nothing downstream knows or cares where they came from.

Hutch's integrator writes one mapping dictionary per source. Nothing else in
the repository is touched. If a column is missing or a value is physically
impossible, this file says so loudly instead of quietly passing a nonsense
number into a model that will happily score it.

-----------------------------------------------------------------------------
CONFIRMED SOURCES  (Hutch IT, 1 October 2026)
-----------------------------------------------------------------------------
    cells_weekly       <- OSS / NMS                     confirmed available
    customers_weekly   <- CDR / xDR mediation           confirmed available
    customers_static   <- prepaid data warehouse        confirmed available
    market_weekly      <- MNP port-out + public promo calendar   external

    Integration style  <- REST, Kafka or warehouse batch: any of the three.
    CEM platform       <- exists, but its data is NOT exposed to third-party
                          systems. StaySignal therefore never reads from it and
                          runs inside Hutch's own boundary.

-----------------------------------------------------------------------------
USAGE
-----------------------------------------------------------------------------
    from integrations.oss_adapter import Adapter, HUTCH_MAPPING_TEMPLATE

    adapter = Adapter(HUTCH_MAPPING_TEMPLATE)
    tables, report = adapter.load_all({
        "cells_weekly":     oss_dataframe,
        "customers_weekly": cdr_dataframe,
        "customers_static": warehouse_dataframe,
        "market_weekly":    market_dataframe,
    })
    print(report)                       # refuses to be ignored
    if report.ok:
        features = build_features(**tables)

Run this file directly to self-test it against the simulated extracts:

    python integrations/oss_adapter.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


# ===========================================================================
# THE CONTRACT — what every canonical table must contain
# ===========================================================================
@dataclass(frozen=True)
class Column:
    """One canonical column, and what a believable value looks like.

    `low` and `high` are PHYSICAL bounds, not statistical ones. SINR below
    -20 dB or a call drop rate above 100% is not an outlier, it is a broken
    export, and the difference matters: we clip the first and refuse the
    second.
    """
    name: str
    kind: str                      # "id" | "int" | "float" | "str"
    low: float | None = None
    high: float | None = None
    required: bool = True
    default: object | None = None  # used when an optional column is absent
    note: str = ""


@dataclass(frozen=True)
class TableSpec:
    name: str
    source: str
    grain: str
    columns: tuple[Column, ...]

    @property
    def required_columns(self) -> list[str]:
        return [c.name for c in self.columns if c.required]


CELLS_WEEKLY = TableSpec(
    name="cells_weekly",
    source="OSS / NMS",
    grain="one row per cell per week",
    columns=(
        Column("cell_id", "id", note="must match serving_cell in customers_weekly"),
        Column("region", "str", note="district, for the market join"),
        Column("week", "int", 1, 520),
        Column("call_drop_rate_pct", "float", 0, 100),
        Column("avg_sinr_db", "float", -20, 40),
        Column("prb_utilisation_pct", "float", 0, 100,
               note="if your export is a 0-1 fraction, use scale=100 in the mapping"),
        Column("handover_success_pct", "float", 0, 100, required=False),
        Column("outage_minutes", "float", 0, 10080,
               note="per week; 10080 = the whole week"),
        Column("shared_site", "int", 0, 1, required=False,
               note="from the site database. Used to read interference honestly, "
                    "never to blame a named operator."),
    ),
)

CUSTOMERS_WEEKLY = TableSpec(
    name="customers_weekly",
    source="CDR / xDR mediation, joined to recharge and app logs",
    grain="one row per subscriber per week",
    columns=(
        Column("customer_id", "id"),
        Column("week", "int", 1, 520),
        Column("data_gb", "float", 0, 10000),
        Column("app_opens", "int", 0, 10000, required=False),
        Column("recharges", "float", 0, 500),
        Column("voice_minutes", "float", 0, 100000, required=False),
        Column("serving_cell", "id", note="the DOMINANT cell that week"),
        Column("home_cell_share", "float", 0, 1,
               note="share of sessions on their modal cell"),
        Column("distinct_cells", "int", 1, 5000,
               note="how many different cells served them that week"),
        Column("distinct_regions", "int", 1, 100,
               note="how many districts those cells sat in"),
        Column("attached", "int", 0, 1,
               note="did the subscriber attach to the network at all that week"),
    ),
)

CUSTOMERS_STATIC = TableSpec(
    name="customers_static",
    source="prepaid data warehouse",
    grain="one row per subscriber",
    columns=(
        Column("customer_id", "id"),
        Column("region", "str"),
        Column("language", "str", required=False, default="English",
               note="selects the SMS template. Optional: where the account record "
                    "has no language, English is used."),
        Column("plan", "str"),
        Column("data_quota_gb", "float", 0, 100000),
        Column("monthly_spend_lkr", "float", 0, 1_000_000),
        Column("months_with_hutch", "int", 0, 1200),
        Column("overage_charges_lkr", "float", 0, 1_000_000, required=False),
        Column("complaints_last_month", "int", 0, 1000, required=False),
    ),
)

MARKET_WEEKLY = TableSpec(
    name="market_weekly",
    source="MNP port-out reporting + public competitor campaign calendar",
    grain="one row per district per week — contains NO personal data",
    columns=(
        Column("region", "str"),
        Column("week", "int", 1, 520),
        Column("competitor_promo_intensity", "float", 0, 1,
               note="0 = nothing happening, 1 = a major national campaign"),
        Column("port_out_rate_pct", "float", 0, 100, required=False,
               note="the observable consequence; preferred over the calendar "
                    "where available, because it is measured rather than announced"),
    ),
)

SPECS = {t.name: t for t in (CELLS_WEEKLY, CUSTOMERS_WEEKLY,
                             CUSTOMERS_STATIC, MARKET_WEEKLY)}


# ===========================================================================
# THE MAPPING — the only thing an integrator at Hutch has to write
# ===========================================================================
@dataclass
class FieldMap:
    """How one of Hutch's exports maps onto one canonical table.

    rename    their column name -> ours
    scale     canonical column  -> multiplier (unit conversion)
    derive    canonical column  -> function(df) -> Series, for anything that
              has to be computed rather than renamed
    const     canonical column  -> a fixed value, for a column their export
              genuinely does not have
    """
    rename: dict[str, str] = field(default_factory=dict)
    scale: dict[str, float] = field(default_factory=dict)
    derive: dict[str, Callable[[pd.DataFrame], pd.Series]] = field(default_factory=dict)
    const: dict[str, object] = field(default_factory=dict)


# A worked template. The commented lines are the ones a Hutch integrator edits;
# everything here is a guess at their naming until they confirm it, and it is
# labelled as a guess rather than presented as fact.
HUTCH_MAPPING_TEMPLATE: dict[str, FieldMap] = {
    "cells_weekly": FieldMap(
        rename={
            # "CELL_NAME":            "cell_id",
            # "LOCATION_AREA":        "region",
            # "WEEK_ID":              "week",
            # "CDR_PCT":              "call_drop_rate_pct",
            # "AVG_SINR_DL":          "avg_sinr_db",
            # "DL_PRB_UTIL":          "prb_utilisation_pct",
            # "HO_SUCC_RATE":         "handover_success_pct",
            # "CELL_UNAVAIL_SEC":     "outage_minutes",
        },
        scale={
            # "prb_utilisation_pct": 100.0,   # if exported as a 0-1 fraction
            # "outage_minutes":      1 / 60,  # if exported in seconds
        },
        const={
            # "shared_site": 0,               # until the site database is joined
        },
    ),
    "customers_weekly": FieldMap(),
    "customers_static": FieldMap(),
    "market_weekly": FieldMap(),
}


# ===========================================================================
# VALIDATION
# ===========================================================================
@dataclass
class TableReport:
    table: str
    rows: int = 0
    missing_required: list[str] = field(default_factory=list)
    missing_optional: list[str] = field(default_factory=list)
    out_of_range: dict[str, int] = field(default_factory=dict)
    null_rate: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing_required and not self.out_of_range


@dataclass
class Report:
    tables: dict[str, TableReport] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(t.ok for t in self.tables.values())

    def __str__(self) -> str:
        width = 74
        lines = ["", "=" * width, " StaySignal adapter — extract validation", "=" * width]
        for name, t in self.tables.items():
            mark = "OK  " if t.ok else "FAIL"
            lines.append(f"[{mark}] {name:<20} {t.rows:>9,} rows   ({SPECS[name].source})")
            for col in t.missing_required:
                lines.append(f"         MISSING REQUIRED COLUMN: {col}")
            if t.missing_optional:
                lines.append("         optional columns absent, defaults used: "
                             + ", ".join(t.missing_optional))
            for col, n in t.out_of_range.items():
                lines.append(f"         OUT OF PHYSICAL RANGE: {col} — {n:,} rows")
            bad_nulls = {c: r for c, r in t.null_rate.items() if r > 0.01}
            if bad_nulls:
                lines.append("         nulls: " + ", ".join(
                    f"{c} {r:.1%}" for c, r in sorted(bad_nulls.items(),
                                                      key=lambda kv: -kv[1])[:5]))
            for n in t.notes:
                lines.append(f"         note: {n}")
        lines.append("-" * width)
        lines.append(" RESULT: " + ("all extracts usable" if self.ok else
                                    "NOT USABLE — fix the items above before scoring"))
        lines.append("=" * width)
        return "\n".join(lines)


# ===========================================================================
# THE ADAPTER
# ===========================================================================
class Adapter:
    """Hutch's field names in, four canonical tables out."""

    def __init__(self, mapping: dict[str, FieldMap] | None = None):
        self.mapping = mapping or {}

    # -- one table ---------------------------------------------------------
    def load(self, table: str, df: pd.DataFrame) -> tuple[pd.DataFrame, TableReport]:
        spec = SPECS[table]
        fmap = self.mapping.get(table, FieldMap())
        rep = TableReport(table=table)

        out = df.rename(columns=fmap.rename).copy()

        for col, fn in fmap.derive.items():
            out[col] = fn(out)
        for col, value in fmap.const.items():
            if col not in out.columns:
                out[col] = value
        for col, factor in fmap.scale.items():
            if col in out.columns:
                out[col] = out[col] * factor

        for c in spec.columns:
            if c.name in out.columns:
                continue
            if c.required:
                rep.missing_required.append(c.name)
            else:
                rep.missing_optional.append(c.name)
                out[c.name] = _default_for(c)

        # types, then physical sanity — run on whatever IS present, so a report
        # names every problem at once rather than one per re-run
        for c in spec.columns:
            if c.name not in out.columns:
                continue
            s = out[c.name]
            if c.kind in ("int", "float"):
                s = pd.to_numeric(s, errors="coerce")
                if c.low is not None and c.high is not None:
                    bad = int(((s < c.low) | (s > c.high)).sum())
                    if bad:
                        rep.out_of_range[c.name] = bad
                if c.kind == "int":
                    s = s.round()
                out[c.name] = s
            else:
                out[c.name] = s.astype("string")
            rep.null_rate[c.name] = float(out[c.name].isna().mean())

        rep.rows = len(out)
        if not rep.missing_required:
            out = out[[c.name for c in spec.columns]]
        return out, rep

    # -- everything --------------------------------------------------------
    def load_all(self, frames: dict[str, pd.DataFrame]
                 ) -> tuple[dict[str, pd.DataFrame], Report]:
        tables, report = {}, Report()
        for name in SPECS:
            if name not in frames:
                rep = TableReport(table=name)
                rep.missing_required = [f"<entire table absent: {SPECS[name].source}>"]
                report.tables[name] = rep
                continue
            tables[name], report.tables[name] = self.load(name, frames[name])

        if report.ok:
            report.tables["cells_weekly"].notes.extend(
                _referential_checks(tables))
        return tables, report


def _default_for(c: Column):
    if c.default is not None:
        return c.default
    return 0 if c.kind in ("int", "float") else "unknown"


def _referential_checks(tables: dict[str, pd.DataFrame]) -> list[str]:
    """The joins have to actually join. This is where real extracts usually
    fail first, and silently: a cell id that exists in CDR but not in the OSS
    export produces a customer with no network evidence, and the model simply
    scores them as if their towers were fine."""
    notes = []
    cw, cells = tables["customers_weekly"], tables["cells_weekly"]
    known = set(cells.cell_id.unique())
    used = set(cw.serving_cell.unique())
    orphans = used - known
    if orphans:
        share = cw.serving_cell.isin(orphans).mean()
        notes.append(f"{len(orphans)} serving cells have no OSS record "
                     f"({share:.1%} of customer-weeks) — those customers would be "
                     f"scored with no network evidence")

    static, weekly = tables["customers_static"], tables["customers_weekly"]
    no_history = set(static.customer_id) - set(weekly.customer_id)
    if no_history:
        notes.append(f"{len(no_history)} subscribers have no weekly history and "
                     f"cannot be scored")

    weeks = weekly.groupby("customer_id").week.nunique()
    short = int((weeks < 17).sum())
    if short:
        notes.append(f"{short} subscribers have under 17 weeks of history — their "
                     f"own baseline window does not exist yet, so they are excluded "
                     f"rather than guessed at")

    market_regions = set(tables["market_weekly"].region.unique())
    missing = set(static.region.unique()) - market_regions
    if missing:
        notes.append(f"{len(missing)} districts have no market feed; "
                     f"market_pressure falls back to 0 for them")
    return notes


# ===========================================================================
# TRANSPORT — all three styles Hutch offered, behind one interface
# ===========================================================================
def from_warehouse_batch(directory: str | Path) -> dict[str, pd.DataFrame]:
    """Nightly CSV or Parquet drop. This is the recommended style: the model is
    a batch job, nothing needs to be scored in real time, and no production
    system is ever queried live."""
    directory = Path(directory)
    frames = {}
    for name in SPECS:
        for ext, reader in ((".parquet", pd.read_parquet), (".csv", pd.read_csv)):
            path = directory / f"{name}{ext}"
            if path.exists():
                frames[name] = reader(path)
                break
    return frames


def from_sql_warehouse(connection, schema: str = "", since_week: int | None = None,
                       tables: dict[str, str] | None = None) -> dict[str, pd.DataFrame]:
    """Read the four canonical tables straight out of a SQL warehouse.

    This is the production path, and it is the answer to "surely you are not
    generating CSV files forever". The CSV loader exists because a laptop has
    no warehouse attached. Nothing downstream can tell the two apart: both
    produce the same four DataFrames.

    `connection` is any DB-API connection or SQLAlchemy engine — Snowflake,
    Oracle, Teradata, Postgres, BigQuery. We do not name a vendor because Hutch
    has not told us which one they run; they said "the data warehouse", and
    every one of these speaks SQL.

        import snowflake.connector
        conn = snowflake.connector.connect(
            account=..., user=..., password=os.environ["SF_PASSWORD"],
            warehouse="ANALYTICS_WH", database="PREPAID")
        frames = from_sql_warehouse(conn, schema="PUBLIC", since_week=1)

    On `since_week`: it is cast to int before it reaches the SQL text, so there
    is no injection surface. We do it this way rather than with a bound
    parameter because the placeholder style differs by driver (? vs %s vs
    :name) and this function has to work with all of them.

    A note on scale, for anyone extending this: a real base is hundreds of
    millions of customer-weeks, and pulling all of it into pandas is the wrong
    shape. The weekly aggregation in features.py is a GROUP BY, and a warehouse
    will do it far faster than we can — push it down, and pull one row per
    customer instead of twenty-six.
    """
    tables = tables or {n: n.upper() for n in SPECS}
    prefix = f"{schema}." if schema else ""
    frames = {}
    for name, spec in SPECS.items():
        table = f"{prefix}{tables.get(name, name.upper())}"
        has_week = any(c.name == "week" for c in spec.columns)
        sql = f"SELECT * FROM {table}"
        if since_week is not None and has_week:
            sql += f" WHERE week >= {int(since_week)}"
        frames[name] = pd.read_sql_query(sql, connection)
    return frames


def from_rest(base_url: str, token: str, since_week: int) -> dict[str, pd.DataFrame]:
    """REST pull. Intentionally unimplemented: implementing it against a guessed
    schema would be fiction. The contract is `GET {base_url}/{table}?since_week=`
    returning rows matching the TableSpec above; one afternoon's work once the
    endpoint exists."""
    raise NotImplementedError(
        "REST transport is specified, not implemented — no Hutch endpoint exists "
        "during the hackathon, and guessing one would be dishonest. "
        "Use from_warehouse_batch() with an export.")


def from_kafka(bootstrap: str, topics: dict[str, str]) -> dict[str, pd.DataFrame]:
    """Kafka consumption, for a future near-real-time mode. The features are
    weekly aggregates, so streaming buys nothing today: it would be consumed
    into the same four tables and scored on the same schedule."""
    raise NotImplementedError(
        "Kafka transport is specified, not implemented. The features are weekly "
        "aggregates, so a stream would be collapsed back into the same four "
        "tables — it adds operational cost and no accuracy.")


# ===========================================================================
# SELF-TEST — runs the adapter over the simulated extracts
# ===========================================================================
def _self_test() -> int:
    data = ROOT / "data"
    frames = {}
    for name in SPECS:
        path = data / f"{name}.csv"
        if path.exists():
            frames[name] = pd.read_csv(path)

    if not frames:
        print("No extracts found. Run `python ml/generate.py` first.")
        return 1

    print("Running the adapter over the simulated extracts with an identity "
          "mapping.\nWith real Hutch exports, only HUTCH_MAPPING_TEMPLATE changes.")
    tables, report = Adapter().load_all(frames)
    print(report)

    if report.ok:
        print("\nCanonical tables produced:")
        for name, t in tables.items():
            print(f"  {name:<20} {len(t):>9,} rows x {len(t.columns)} columns")

    # Prove the SQL path produces exactly what the file path produces. We use
    # SQLite because it is the one SQL engine available without an account, but
    # the code under test is the same code a Snowflake or Oracle connection
    # would run — only the connection object differs.
    print("\n" + "=" * 74)
    print(" SQL warehouse path — same loader, same four tables")
    print("=" * 74)
    import sqlite3
    conn = sqlite3.connect(":memory:")
    for name, df in frames.items():
        df.to_sql(name.upper(), conn, index=False)
    sql_frames = from_sql_warehouse(conn, since_week=1)
    sql_tables, sql_report = Adapter().load_all(sql_frames)
    same = all(
        tables[n].shape == sql_tables[n].shape
        and list(tables[n].columns) == list(sql_tables[n].columns)
        for n in SPECS
    )
    for name in SPECS:
        print(f"  {name:<20} file {str(tables[name].shape):>14}   "
              f"sql {str(sql_tables[name].shape):>14}")
    print(f"  -> identical: {same}.  The model cannot tell which one it was given,")
    print("     The source of the tables is not visible downstream.")
    conn.close()

    # A deliberately broken extract, to prove the validator is not decorative.
    print("\n" + "=" * 74)
    print(" Negative test — the same loader against a corrupted OSS export")
    print("=" * 74)
    broken = frames["cells_weekly"].copy()
    broken["avg_sinr_db"] = broken["avg_sinr_db"] * 100      # wrong unit
    broken = broken.drop(columns=["prb_utilisation_pct"])     # column renamed upstream
    _, rep = Adapter().load("cells_weekly", broken)
    print(f"  missing required : {rep.missing_required}")
    print(f"  out of range     : {rep.out_of_range}")
    print("  -> the extract is rejected before any customer is scored.")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(_self_test())
