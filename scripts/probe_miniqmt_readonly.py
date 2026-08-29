"""Command-line entry point for the TASK-055 Mini QMT read-only probe."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from quantiqmt.live.qmt.readonly_probe import (
    ProbeConfigError,
    ReadonlyProbeConfig,
    default_exit_code,
    failure_report,
    load_probe_environment,
    run_probe_isolated,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the fail-closed Mini QMT read-only probe")
    parser.add_argument(
        "--env-file",
        type=Path,
        required=True,
        help="Explicit local environment file; secrets are forbidden",
    )
    arguments = parser.parse_args()

    try:
        environment = load_probe_environment(arguments.env_file, os.environ)
        config = ReadonlyProbeConfig.from_environment(environment)
        report = run_probe_isolated(config)
    except ProbeConfigError as exc:
        report = failure_report(exc.reason_code)

    print(json.dumps(report.to_public_dict(), sort_keys=True))
    return default_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
