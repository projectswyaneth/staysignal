"""Renders docs/gantt.png — the StaySignal implementation plan.

    python docs/make_gantt.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.lines import Line2D

OUT = Path(__file__).resolve().parent / "gantt.png"

SURFACE = "#FCFCFB"
INK = "#12100E"
BODY = "#453F3A"
MUTED = "#8A827B"
GRID = "#E8E3DE"

# Four workstreams. Palette validated with the dataviz validator:
# lightness band, chroma floor, CVD separation, normal-vision floor and
# contrast against this surface all pass. Identity is never colour-alone —
# every bar is directly labelled on the y axis as well.
STREAMS = {
    "Data & integration":  "#E8490B",
    "Modelling":           "#1569A8",
    "Product & interface": "#2E7D52",
    "Pilot & rollout":     "#7A4FA3",
}

# (phase, workstream, start week, end week)
PHASES = [
    ("1 · Access, NDA and pseudonymous key agreement", "Data & integration", 1, 3),
    ("2 · Adapter build and data-quality audit",       "Data & integration", 2, 7),
    ("3 · Retrain and validate on Hutch data",         "Modelling",          6, 10),
    ("4 · Threshold and policy calibration",           "Modelling",          9, 12),
    ("5 · Console and campaign-system integration",    "Product & interface", 10, 16),
    ("6 · Fairness and conduct audit",                 "Product & interface", 14, 17),
    ("7 · Controlled pilot, one region, with holdout", "Pilot & rollout",    17, 25),
    ("8 · Measure save rate, retrain from outcomes",   "Pilot & rollout",    23, 28),
    ("9 · National rollout and handover",              "Pilot & rollout",    27, 32),
]

MILESTONES = [
    (7,  "Extracts validated"),
    (12, "Model signed off"),
    (17, "Pilot live"),
    (25, "Save rate measured"),
    (32, "Handover"),
]

MAX_WEEK = 33

fig, ax = plt.subplots(figsize=(13.2, 6.4))
fig.patch.set_facecolor(SURFACE)
ax.set_facecolor(SURFACE)

bar_h = 0.52
for i, (label, stream, start, end) in enumerate(PHASES):
    y = len(PHASES) - i - 1
    # 2px surface gap between adjacent fills is achieved by the bar height
    # leaving space in the row; rounded data-ends anchored to the real extent.
    ax.add_patch(FancyBboxPatch(
        (start, y - bar_h / 2), end - start, bar_h,
        boxstyle="round,pad=0,rounding_size=0.22",
        linewidth=0, facecolor=STREAMS[stream], mutation_aspect=0.42, zorder=3))
    ax.text(end + 0.35, y, f"w{start}–{end}", va="center", ha="left",
            fontsize=8.5, color=MUTED, zorder=4)

for week, name in MILESTONES:
    ax.plot([week], [-1.0], marker="D", markersize=6.5, color=INK,
            clip_on=False, zorder=5)
    ax.text(week, -1.3, name, ha="center", va="top", fontsize=8.2,
            color=BODY, clip_on=False)

for x in range(0, MAX_WEEK + 1, 4):
    ax.axvline(x, color=GRID, lw=1, zorder=1)

ax.set_yticks(range(len(PHASES)))
ax.set_yticklabels([p[0] for p in reversed(PHASES)], fontsize=9.6, color=INK)
ax.set_xticks(range(0, MAX_WEEK + 1, 4))
ax.set_xticklabels([f"week {x}" if x else "start" for x in range(0, MAX_WEEK + 1, 4)],
                   fontsize=8.8, color=MUTED)
ax.set_xlim(0, MAX_WEEK + 3.2)
ax.set_ylim(-1.9, len(PHASES) - 0.3)
# week scale on top, so the milestone row below has the space to itself
ax.xaxis.set_ticks_position("top")
ax.xaxis.set_label_position("top")
ax.tick_params(length=0, pad=6)
for side in ("top", "right", "left", "bottom"):
    ax.spines[side].set_visible(False)

ax.set_title("StaySignal — implementation plan from hackathon to national rollout",
             loc="left", fontsize=13.5, color=INK, fontweight="bold", pad=44)
ax.text(0, 1.085, "Eight months. The pilot carries a holdout group, because that is "
                  "the only way the save rate stops being an assumption.",
        transform=ax.transAxes, fontsize=9.6, color=MUTED)

ax.legend(handles=[Line2D([], [], marker="s", linestyle="", markersize=9,
                          markerfacecolor=c, markeredgecolor="none", label=n)
                   for n, c in STREAMS.items()],
          loc="lower right", bbox_to_anchor=(1.0, -0.30), ncol=4,
          frameon=False, fontsize=9, labelcolor=BODY, handletextpad=0.5,
          columnspacing=1.8)

fig.tight_layout()
fig.subplots_adjust(bottom=0.20)
fig.savefig(OUT, dpi=200, facecolor=SURFACE)
print(f"Written: {OUT}")
