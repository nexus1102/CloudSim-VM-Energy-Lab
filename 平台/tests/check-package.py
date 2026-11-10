"""Real relocation, copy-integrity and refusal-path checks; retains temp evidence."""
import csv
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("package_current", ROOT / "tools/package_ga_fix_v10.py")
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


def rejected(action, expected):
    try:
        action()
    except expected:
        return
    raise AssertionError("Unsafe package operation was accepted")


def run(platform, *arguments):
    environment = dict(os.environ, RESEARCH_PYTHON=sys.executable)
    subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File",
                    str(platform / "run_research_platform.ps1"), *arguments],
                   cwd=platform, env=environment, check=True)


def main():
    temporary = Path(tempfile.mkdtemp(prefix="V1-maintenance-package-"))
    target = temporary / "V1 改名与空格验证"
    rejected(lambda: packager.package(ROOT.parent / "nested-output"), ValueError)
    rejected(lambda: packager.package(ROOT.parent.parent), FileExistsError)
    rejected(lambda: packager.package(temporary), FileExistsError)
    missing = temporary / "missing-report-output"
    rejected(lambda: packager.package(missing, temporary / "missing-matrix"), ValueError)
    assert not missing.exists(), "Invalid source created a partial output"
    packager.package(target)
    with (target / "文件校验清单.csv").open(encoding="utf-8-sig", newline="") as stream:
        records = list(csv.DictReader(stream))
    assert len(records) > 100
    for record in records:
        assert packager.sha(target / record["path"]) == record["sha256"], record["path"]
    assert json.loads((target / "封存核验.json").read_text(encoding="utf-8"))["simulation_rerun"] is False
    rejected(lambda: packager.package(target), FileExistsError)
    platform = target / "平台"
    run(platform, "-Mode", "Test")
    run(platform, "-Mode", "Single", "-Method", "GA", "-Output", "research_platform/runs/maintenance_package_ga")
    run(platform, "-Mode", "Verify", "-Output", "research_platform/runs/maintenance_package_ga")
    assert json.loads((platform / "research_platform/runs/maintenance_package_ga/report/independent_checks.json")
                      .read_text(encoding="utf-8"))["status"] == "PASS"
    # Every sealed member remains unchanged after compiling/running the relocated package.
    for record in records:
        assert packager.sha(target / record["path"]) == record["sha256"], record["path"]
    print("PASS package hashes, refusal boundaries, relocated Test/Single/Verify; evidence:", temporary, flush=True)


if __name__ == "__main__":
    main()
