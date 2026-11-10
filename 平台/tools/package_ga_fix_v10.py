"""Package the current working platform with explicitly identified historical reports.

The historical filename is kept for command compatibility. No implicit output,
no rewriting sealed production metadata, and no assertion of a new simulation.
"""
import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TREES = ["src", "lib", "tools", "build", "tests", "config", "correction/inputs",
         "correction/comparison", "paper_alignment/config", "paper_alignment/inputs",
         "evidence", "research_platform/config", "research_platform/audit"]
FILES = ["build.ps1", "run_research_platform.ps1", "runtime.ps1", "requirements.txt",
         "requirements-lock.txt", "使用这套平台.md", "research_platform/README.md",
         "research_platform/物理假设与论文依据.md"]
BASELINE = ["summary.csv", "report/ga_ablation.csv", "report/ga_static_before_after.csv"]


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def package(output, run=None):
    project = ROOT.parent
    target = Path(output).resolve()
    if target.exists():
        raise FileExistsError(f"Output already exists; choose a new directory: {target}")
    if target.is_relative_to(project) or project.is_relative_to(target):
        raise ValueError("Package output and source project must not overlap")
    report = Path(run).resolve() / "report" if run else project / "结果"
    if target.is_relative_to(report) or report.is_relative_to(target):
        raise ValueError("Package output and report source must not overlap")
    if run and not (Path(run) / "completed.txt").is_file():
        raise ValueError("Historical matrix requires completed.txt")
    for name in ["independent_checks.json", "figure_checks.json", "final_fix_checks.json"]:
        if json.loads((report / name).read_text(encoding="utf-8-sig"))["status"] != "PASS":
            raise ValueError(f"Historical report lacks PASS: {name}")
    sources = [(ROOT / part, Path("平台") / part) for part in TREES + FILES]
    sources += [(report, Path("结果"))]
    sources += [(project / part, Path(part)) for part in
                ["README.md", "在此目录运行.md", "历史数据索引.json", "维护记录"]]
    baseline = ROOT / "research_platform/runs/ga_fix_v09_20261013"
    sources += [(baseline / part, Path("平台/research_platform/runs/ga_fix_v09_20261013") / part)
                for part in BASELINE]
    # Validate every source before creating an output directory.
    records = []
    for source, relative in sources:
        if not source.exists():
            raise FileNotFoundError(f"Required package source is missing: {source}")
        candidates = sorted(source.rglob("*")) if source.is_dir() else [source]
        if source.is_symlink() or any(p.is_symlink() for p in candidates):
            raise ValueError(f"Symbolic links are unsupported in package sources: {source}")
        for item in candidates:
            if item.is_file() and "__pycache__" not in item.parts and item.suffix not in {".pyc", ".log"}:
                dest = relative / item.relative_to(source) if source.is_dir() else relative
                records.append((item, dest, sha(item)))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir()  # Race-safe: never merge into an existing archive.
    for source, relative, expected in records:
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        if sha(dest) != expected:
            raise AssertionError(f"Copy hash mismatch: {relative}; incomplete output retained")
    metadata = dict(project_name=target.name, source_project=str(project),
                    report_source=str(report), historical_algorithm_version="v10",
                    raw_matrix_cases_copied=False, simulation_rerun=False,
                    status="COPIED_HASH_VERIFIED",
                    scope="Copy integrity only. Included reports remain historical evidence; run Test and a new Single to validate the current package.")
    (target / "封存核验.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    # The manifest excludes itself; all other copied/generated files are covered.
    with (target / "文件校验清单.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["path", "sha256"])
        writer.writeheader()
        for item in sorted(target.rglob("*")):
            if item.is_file() and item != target / "文件校验清单.csv":
                writer.writerow(dict(path=item.relative_to(target).as_posix(), sha256=sha(item)))
    print(f"COPIED_HASH_VERIFIED: {target}; historical reports, no new simulation claim")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New package directory outside source project")
    parser.add_argument("--run", help="Optional completed historical matrix; default: project/结果")
    arguments = parser.parse_args()
    package(arguments.output, arguments.run)
