"""Render the Precision64 figures from preserved evidence.

From the repository root, with Matplotlib already available:
    python qualification/precision64/plot_results.py

Inputs default to evidence/precision64/{physics,performance}.json. Outputs are
docs/figures/precision64-{convergence,timing}.{svg,png} and
docs/figures/precision64-plot-data.json. The latter records the exact plotted
values, input and output SHA-256 hashes, and rendering versions. Rendering is
deterministic within the same Python, Matplotlib, FreeType and font environment.
No simulation, timing measurement, package installation or network access occurs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform


CASES = (
    ("earth-orbit", "Earth", "#0072B2", "o"),
    ("moon-orbit", "Moon", "#D55E00", "s"),
    ("earth-eccentric-inclined", "Earth, inclined holdout", "#009E73", "^"),
)
PLATFORMS = (
    ("windows-x64", "Windows x64", "#0072B2"),
    ("macos-arm64", "macOS arm64", "#D55E00"),
)
WORKLOADS = (
    ("coast", "Coast"),
    ("coupled-controls", "Coupled controls"),
    ("high-spin", "High spin"),
)
FACTORS = (("legacy", 1), ("coarser", 4), ("selected", 8))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    def reject_constant(value):
        raise ValueError(f"Nonfinite JSON constant: {value}")

    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def finite_number(value, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"{label} must be finite and {'positive' if positive else 'nonnegative'}")
    return float(value)


def convergence_data(physics: dict) -> list[dict]:
    if physics["outer_steps_per_second"] != 64 or physics["selected_factor"] != 8:
        raise ValueError("Convergence figure requires the selected N=8, 64 Hz evidence")
    rows = []
    for case, label, _, _ in CASES:
        matches = [result for result in physics["results"] if result["case"] == case]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one result for {case}")
        result = matches[0]
        coverage = None
        for role, factor in FACTORS:
            if result["factors"][role] != factor:
                raise ValueError(f"Unexpected {role} factor for {case}")
            oracle = result["oracle_receipts"][role]
            if oracle["case"] != case or oracle["steps_per_second"] != 64:
                raise ValueError(f"Mismatched oracle receipt for {case}/{role}")
            if oracle["complete_declared_sample_coverage"] is not True:
                raise ValueError(f"Incomplete sample coverage for {case}/{role}")
            current_coverage = (oracle["duration_seconds"], oracle["sample_count"],
                                oracle["sample_interval_seconds"])
            if coverage is not None and coverage != current_coverage:
                raise ValueError(f"Unequal comparison coverage for {case}")
            coverage = current_coverage
            error_m = finite_number(oracle["metrics"]["max_position_error_m"],
                                    f"{case}/{role} position error", positive=True)
            rows.append({"case": case, "label": label, "role": role,
                         "substeps": factor, "max_sampled_position_error_m": error_m,
                         "max_sampled_position_error_mm": error_m * 1000,
                         "duration_seconds": current_coverage[0],
                         "sample_count": current_coverage[1],
                         "sample_interval_seconds": current_coverage[2],
                         "reference": oracle["reference"],
                         "oracle_identities": oracle["identities"]})
    return rows


def timing_data(performance: dict) -> list[dict]:
    rows = []
    for platform_id, label, _ in PLATFORMS:
        for workload, _ in WORKLOADS:
            matches = [run for run in performance["runs"]
                       if run["platform"] == platform_id and run["substeps"] == 8
                       and run["workload"] == workload]
            if len(matches) != 1:
                raise ValueError(f"Expected one N=8 run for {platform_id}/{workload}")
            run = matches[0]
            rows.append({"platform": platform_id, "label": label, "substeps": 8,
                         "workload": workload,
                         "mean_ms": finite_number(run["mean_ms"], "mean_ms"),
                         "p99_ms": finite_number(run["p99_ms"], "p99_ms")})
    return rows


def save_figure(figure, output: Path, stem: str) -> list[Path]:
    files = []
    for extension in ("svg", "png"):
        path = output / f"{stem}.{extension}"
        metadata = {"Date": None, "Creator": "Precision64 plotting script"} if extension == "svg" else {
            "Software": "Precision64 plotting script"}
        figure.savefig(path, dpi=180, facecolor="white", metadata=metadata,
                       bbox_inches="tight", pad_inches=0.16)
        if extension == "svg":
            lines = path.read_text(encoding="utf-8").splitlines()
            path.write_text("\n".join(line.rstrip(" \t") for line in lines) + "\n",
                            encoding="utf-8", newline="\n")
        files.append(path)
    return files


def draw_convergence(plt, rows: list[dict], output: Path) -> list[Path]:
    figure, axis = plt.subplots(figsize=(8.0, 5.6))
    figure.subplots_adjust(left=0.13, right=0.97, bottom=0.27, top=0.88)
    for case, label, color, marker in CASES:
        series = [row for row in rows if row["case"] == case]
        axis.plot([row["substeps"] for row in series],
                  [row["max_sampled_position_error_mm"] for row in series],
                  color=color, marker=marker, markersize=6, linewidth=1.7, label=label)
    axis.set_xscale("log", base=2)
    axis.set_yscale("log")
    axis.set_xticks([1, 4, 8], labels=["1", "4", "8"])
    axis.set_xlim(0.86, 9.2)
    errors = [row["max_sampled_position_error_mm"] for row in rows]
    axis.set_ylim(min(errors) / 1.7, max(errors) * 1.8)
    axis.set_xlabel("Integration substeps per 64 Hz tick")
    axis.set_ylabel("Maximum sampled position error (mm)")
    axis.set_title("Orbital position error under refinement", loc="left", pad=14)
    axis.grid(which="major", color="#D9D9D9", linewidth=0.65)
    axis.set_axisbelow(True)
    axis.legend(loc="upper right", frameon=True, facecolor="white", edgecolor="white")
    durations = [next(row for row in rows if row["case"] == case)["duration_seconds"]
                 for case, _, _, _ in CASES]
    intervals = {row["sample_interval_seconds"] for row in rows}
    if intervals != {1}:
        raise ValueError("Caption requires one-second orbital samples")
    caption = (f"Analytic two-body reference; samples every 1 s. Earth: {durations[0]:g} s; "
               f"Moon: {durations[1]:g} s; holdout: {durations[2]:g} s.\n"
               "Errors describe exported samples; extrema between samples were not measured.")
    figure.text(0.13, 0.055, caption, fontsize=9, color="#404040", linespacing=1.5)
    files = save_figure(figure, output, "precision64-convergence")
    plt.close(figure)
    return files


def draw_timing(plt, rows: list[dict], output: Path) -> list[Path]:
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    figure, axis = plt.subplots(figsize=(8.0, 5.6))
    figure.subplots_adjust(left=0.11, right=0.97, bottom=0.24, top=0.77)
    width = 0.30
    for index, (platform_id, _, color) in enumerate(PLATFORMS):
        series = [next(row for row in rows if row["platform"] == platform_id
                       and row["workload"] == workload) for workload, _ in WORKLOADS]
        positions = [x + (index - 0.5) * 0.36 for x in range(len(WORKLOADS))]
        axis.bar(positions, [row["mean_ms"] for row in series], width=width,
                 color=color, alpha=0.82, edgecolor=color, linewidth=0.8)
        axis.scatter(positions, [row["p99_ms"] for row in series], marker="D", s=39,
                     facecolor="white", edgecolor=color, linewidth=1.7, zorder=4)
    axis.axhline(12.5, color="#666666", linestyle="--", linewidth=1.2)
    axis.axhline(15.625, color="#222222", linestyle=":", linewidth=1.4)
    for y, label in ((12.5, "12.5 ms headroom gate"), (15.625, "15.625 ms tick budget")):
        axis.text(0.99, y + 0.24, label, transform=axis.get_yaxis_transform(),
                  ha="right", va="bottom", color="#333333", fontsize=9,
                  bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.4})
    maximum = max(row[key] for row in rows for key in ("mean_ms", "p99_ms"))
    axis.set_ylim(0, max(18.5, maximum * 1.25))
    axis.set_xlim(-0.6, len(WORKLOADS)-0.4)
    axis.set_xticks(range(len(WORKLOADS)), labels=[label for _, label in WORKLOADS])
    axis.set_ylabel("Time per outer tick (ms)")
    axis.grid(axis="y", color="#D9D9D9", linewidth=0.65)
    axis.set_axisbelow(True)
    figure.suptitle("Tick timing with 8 integration substeps", x=0.11, y=0.95,
                   ha="left", fontsize=13)
    handles = [Patch(facecolor=color, label=label) for _, label, color in PLATFORMS]
    handles += [Patch(facecolor="#777777", label="Mean (bar)"),
                Line2D([], [], marker="D", linestyle="none", markerfacecolor="white",
                       markeredgecolor="#333333", label="99th percentile (point)")]
    figure.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.10, 0.905),
                  ncol=2, frameon=False, columnspacing=2.0, fontsize=9)
    figure.text(0.11, 0.06,
                "Measured workloads on two machines; 64 Hz outer tick.\n"
                "Points show the 99th percentile, not a confidence interval or worst-case bound.",
                fontsize=9, color="#404040", linespacing=1.5)
    files = save_figure(figure, output, "precision64-timing")
    plt.close(figure)
    return files


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics", type=Path, default=root/"evidence/precision64/physics.json")
    parser.add_argument("--performance", type=Path, default=root/"evidence/precision64/performance.json")
    parser.add_argument("--output", type=Path, default=root/"docs/figures")
    args = parser.parse_args()
    convergence = convergence_data(load_json(args.physics))
    timing = timing_data(load_json(args.performance))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.ft2font
    import matplotlib.pyplot as plt

    matplotlib.rcParams.update({
        "svg.hashsalt": "precision64-figures-v1", "svg.fonttype": "path",
        "font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 13,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.facecolor": "white", "figure.facecolor": "white",
        "savefig.facecolor": "white", "text.color": "#222222",
        "axes.labelcolor": "#222222", "xtick.color": "#333333", "ytick.color": "#333333",
    })
    args.output.mkdir(parents=True, exist_ok=True)
    files = draw_convergence(plt, convergence, args.output) + draw_timing(plt, timing, args.output)
    receipt = {
        "schema": "precision64-plot-data-v1",
        "inputs": {"physics_sha256": sha256(args.physics), "performance_sha256": sha256(args.performance)},
        "plot_script_sha256": sha256(Path(__file__)),
        "rendering": {"python": platform.python_version(), "matplotlib": matplotlib.__version__,
                      "freetype": matplotlib.ft2font.__freetype_version__, "backend": "Agg",
                      "svg_hashsalt": "precision64-figures-v1", "date_metadata": None},
        "convergence": convergence, "timing": timing,
        "timing_reference_lines_ms": {"headroom_gate": 12.5, "outer_tick_budget": 15.625},
        "outputs_sha256": {path.name: sha256(path) for path in files},
    }
    receipt_path = args.output/"precision64-plot-data.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"receipt": str(receipt_path), "outputs_sha256": receipt["outputs_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
