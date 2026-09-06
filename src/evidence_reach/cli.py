"""Command-line adapter for deterministic EvidenceReach assessments."""

import argparse
import csv
import io
import json
from pathlib import Path
import sys
from typing import Sequence

from .core import PlanValidationError, _summary_rows_for_assessed_plan, assess


CSV_FIELDS = (
    "scenario_id",
    "horizon_days",
    "horizon_date",
    "scenario_implied_matured_n",
    "required_n",
    "state",
    "earliest_target_date",
)


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="evidence-reach")
    commands = parser.add_subparsers(dest="command", required=True)
    assess_parser = commands.add_parser("assess")
    assess_parser.add_argument("--plan", required=True)
    assess_parser.add_argument("--out", required=True)
    return parser


def _render_csv(result: dict[str, object]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(CSV_FIELDS)
    for row in result["reachability"]:
        writer.writerow([row[field] for field in CSV_FIELDS])
    return output.getvalue().encode("utf-8")


def _display(value: object) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, float):
        return f"{value:.12g}"
    return str(value)


def _render_summary(
    result: dict[str, object], summary_rows: list[dict[str, object]]
) -> bytes:
    statistics = result["statistics"]
    lines = [
        "# EvidenceReach assessment",
        "",
        "## Decision summary",
        "",
    ]
    for row in summary_rows:
        earliest_target_date = row["earliest_target_date"]
        earliest_text = (
            "not reached within term"
            if earliest_target_date is None
            else _display(earliest_target_date)
        )
        lines.append(
            "- {scenario_id}: required N {required_n}; scenario-implied mature N "
            "at the end of the collection-and-maturity term ({term_end_date}) "
            "{mature_n_at_term_end}; gap {mature_n_gap}; earliest target date "
            "{earliest_target_date}.".format(
                **{
                    field: _display(value)
                    for field, value in {
                        **row,
                        "earliest_target_date": earliest_text,
                    }.items()
                }
            )
        )
    lines.extend([
        "",
        "## Statistics",
        "",
        f"- Current mature N: {_display(statistics['current_matured_n'])}",
        f"- Required N: {_display(statistics['required_n'])}",
        f"- Adjusted alpha: {_display(statistics['adjusted_alpha'])}",
        f"- Current power: {_display(statistics['current_power'])}",
        f"- Current MDE: {_display(statistics['current_mde'])}",
        f"- Power at required N: {_display(statistics['power_at_required_n'])}",
        "",
        "## Scenario-implied reachability",
        "",
    ])
    scenarios: dict[str, list[dict[str, object]]] = {}
    for row in result["reachability"]:
        scenarios.setdefault(str(row["scenario_id"]), []).append(row)
    for scenario_id, rows in scenarios.items():
        first = rows[0]
        earliest_target_date = (
            "not reached within term"
            if first["earliest_target_date"] is None
            else _display(first["earliest_target_date"])
        )
        horizons = "; ".join(
            "{horizon_days} days ({horizon_date}): N "
            "{scenario_implied_matured_n}".format(
                **{field: _display(row[field]) for field in CSV_FIELDS}
            )
            for row in rows
        )
        lines.append(
            f"- {scenario_id}: scenario-implied mature N by horizon: "
            f"{horizons}; {_display(first['state'])}; earliest target date "
            f"{earliest_target_date}."
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {limitation}" for limitation in result["limitations"])
    return ("\n".join(lines) + "\n").encode("utf-8")


def _render_outputs(
    result: dict[str, object], summary_rows: list[dict[str, object]]
) -> dict[str, bytes]:
    return {
        "assessment.json": (
            json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8"),
        "reachability.csv": _render_csv(result),
        "summary.md": _render_summary(result, summary_rows),
    }


def _write_outputs(output_directory: Path, outputs: dict[str, bytes]) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    for name in ("assessment.json", "reachability.csv", "summary.md"):
        (output_directory / name).write_bytes(outputs[name])


def _error(message: str) -> int:
    print(f"evidence-reach: {message}", file=sys.stderr)
    return 1


def _argument_error(message: str) -> int:
    required_prefix = "the following arguments are required: "
    if message.startswith(required_prefix):
        missing = message.removeprefix(required_prefix)
        label = "argument" if ", " not in missing else "arguments"
        return _error(f"missing required {label}: {missing}")
    return _error("invalid arguments")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the single EvidenceReach command and return 0 or 1."""
    try:
        arguments = _parser().parse_args(argv)
    except SystemExit as error:
        return 0 if error.code == 0 else _error("invalid arguments")
    except ValueError as error:
        return _argument_error(str(error))

    try:
        plan_bytes = Path(arguments.plan).read_bytes()
    except (OSError, ValueError):
        return _error("unable to read plan")

    try:
        result = assess(plan_bytes)
    except PlanValidationError as error:
        return _error(f"invalid plan: {error}")
    except Exception:
        return _error("calculation failed")

    try:
        summary_rows = _summary_rows_for_assessed_plan(
            plan_bytes,
            required_n=result["statistics"]["required_n"],
            reachability_rows=result["reachability"],
        )
        outputs = _render_outputs(result, summary_rows)
    except Exception:
        return _error("calculation failed")

    try:
        _write_outputs(Path(arguments.out), outputs)
    except (OSError, ValueError):
        return _error("unable to write results")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
