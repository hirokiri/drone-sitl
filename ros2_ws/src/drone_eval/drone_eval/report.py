"""Turn a recorded flight into accuracy metrics and a plot (FR7, FR8).

Usage:
    ros2 run drone_eval report runs/<run>

Reads `<run>/flight.csv` (written by flight_recorder) and writes next to it:
`report.json` with the horizontal error of PX4's estimate against ground
truth (overall, and before / during / after the GNSS loss), and `report.png`
with the flown track and the error over time.
"""

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no display needed
import matplotlib.pyplot as plt

from drone_eval import metrics
from drone_eval.flight_log import Sample, read_log

LOSS_COLOUR = "#d9534f"


def build_report(samples: list[Sample]) -> dict:
    """Everything the JSON report holds, as plain data."""
    flying = [s for s in samples if not math.isnan(s.flight_time_s)]
    nav_states = []
    for sample in flying:
        if not nav_states or nav_states[-1]["nav_state"] != sample.nav_state:
            nav_states.append(
                {"flight_time_s": sample.flight_time_s, "nav_state": sample.nav_state}
            )
    return {
        "samples": len(samples),
        "flight_duration_s": flying[-1].flight_time_s if flying else 0.0,
        "gnss_loss": [asdict(w) for w in metrics.loss_windows(samples)],
        "horizontal_error_m": {
            phase: None if errors is None else asdict(errors)
            for phase, errors in metrics.phase_errors(samples).items()
        },
        "estimate_invalid_at_s": metrics.first_flight_time(
            samples, lambda s: not s.est_xy_valid
        ),
        "nav_states": nav_states,
    }


def plot(samples: list[Sample], path: Path, title: str) -> None:
    north, east, _ = metrics.frame_offset(samples)
    errors = metrics.horizontal_errors(samples)
    flying = [
        (s, e)
        for s, e in zip(samples, errors, strict=True)
        if not math.isnan(s.flight_time_s)
    ]
    windows = metrics.loss_windows(samples)

    fig, (track, error) = plt.subplots(1, 2, figsize=(12, 5.2))
    fig.suptitle(title)

    track.plot(
        [s.truth_e for s, _ in flying],
        [s.truth_n for s, _ in flying],
        color="black",
        label="ground truth",
    )
    track.plot(
        [s.est_e + east for s, _ in flying],
        [s.est_n + north for s, _ in flying],
        color="#1f77b4",
        linestyle="--",
        label="PX4 estimate (EKF2)",
    )
    lost = [s for s, _ in flying if s.gnss_mode != "healthy"]
    if lost:
        track.scatter(
            [s.truth_e for s in lost],
            [s.truth_n for s in lost],
            color=LOSS_COLOUR,
            s=6,
            zorder=3,
            label="ground truth, GNSS lost",
        )
    track.set_xlabel("east [m]")
    track.set_ylabel("north [m]")
    track.set_aspect("equal", adjustable="datalim")
    track.grid(True, alpha=0.3)
    track.legend(loc="best")
    track.set_title("Track (top view)")

    times = [s.flight_time_s for s, _ in flying]
    error.plot(times, [e for _, e in flying], color="#1f77b4", label="estimate error")
    error.plot(
        times,
        [s.est_eph for s, _ in flying],
        color="gray",
        linestyle=":",
        label="PX4's own accuracy estimate (eph)",
    )
    for index, window in enumerate(windows):
        error.axvspan(
            window.start_s,
            window.end_s,
            color=LOSS_COLOUR,
            alpha=0.15,
            label=f"GNSS {window.mode}" if index == 0 else None,
        )
    invalid_at = metrics.first_flight_time(samples, lambda s: not s.est_xy_valid)
    if invalid_at is not None:
        error.axvline(
            invalid_at,
            color=LOSS_COLOUR,
            linestyle="--",
            label="PX4 declares its position invalid",
        )
    error.set_xlabel("time since takeoff [s]")
    error.set_ylabel("horizontal error [m]")
    error.set_ylim(bottom=0.0)
    error.grid(True, alpha=0.3)
    error.legend(loc="best")
    error.set_title("Horizontal position error")

    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def describe(report: dict) -> str:
    lines = [f"flight: {report['flight_duration_s']:.0f} s"]
    for window in report["gnss_loss"]:
        lines.append(
            f"GNSS {window['mode']}: {window['start_s']:.1f} s to "
            f"{window['end_s']:.1f} s after takeoff"
        )
    for phase, errors in report["horizontal_error_m"].items():
        if errors is not None:
            lines.append(
                f"horizontal error, {phase.replace('_', ' ')}: "
                f"RMSE {errors['rmse_m']:.2f} m, max {errors['max_m']:.2f} m, "
                f"final {errors['final_m']:.2f} m"
            )
    if report["estimate_invalid_at_s"] is not None:
        lines.append(
            "PX4 declared its position invalid "
            f"{report['estimate_invalid_at_s']:.1f} s after takeoff"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("run_dir", type=Path, help="directory holding flight.csv")
    args = parser.parse_args()

    samples = read_log(args.run_dir)
    report = build_report(samples)
    (args.run_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    plot(samples, args.run_dir / "report.png", title=args.run_dir.resolve().name)
    print(describe(report))
    print(f"wrote {args.run_dir / 'report.json'} and {args.run_dir / 'report.png'}")


if __name__ == "__main__":
    main()
