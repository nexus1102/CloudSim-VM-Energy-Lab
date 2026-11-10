"""Check original archive bytes, complete source classification and V1 doc links."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess

PROJECT = Path(__file__).resolve().parents[2]
BASELINE = "6259eb6"
# Only these original baseline files are intentionally maintained.
ALLOWED = {
    "README.md", "在此目录运行.md", "平台/使用这套平台.md",
    "平台/research_platform/README.md", "平台/build.ps1",
    "平台/run_research_platform.ps1", "平台/src/repro/ResearchPlacement.java",
    "平台/src/repro/ResearchExperiments.java", "平台/tools/package_ga_fix_v10.py",
    "平台/research_platform/config/default.properties",
    "平台/tools/research_platform_audit.py",
    "平台/src/repro/ResearchFigureBenchmarkV10.java",
    "平台/src/repro/ResearchDatacenter.java",
}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--local-history",action="store_true",help="Also check external original data and local maintenance runs")
    args=parser.parse_args()
    tree = subprocess.check_output(["git", "ls-tree", "-rz", BASELINE], cwd=PROJECT)
    protected = 0
    for record in tree.split(b"\0"):
        if not record:
            continue
        metadata, name = record.split(b"\t", 1)
        path = name.decode("utf-8")
        if path in ALLOWED:
            continue
        data = (PROJECT / path).read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        assert actual == metadata.split()[2].decode(), "Historical file changed: " + path
        protected += 1
    platform = PROJECT / "平台"
    classified = []
    for manifest in (platform / "build").glob("*.txt"):
        classified.extend(line.strip() for line in manifest.read_text(encoding="utf-8-sig").splitlines()
                          if line.strip() and not line.startswith("#"))
    assert len(classified) == len(set(classified)), "Source appears in multiple groups"
    assert set(classified) == {p.relative_to(platform).as_posix() for p in (platform / "src/repro").glob("*.java")}
    default = (platform / "research_platform/config/default.properties").read_text(encoding="utf-8-sig")
    keys = [line.split("=", 1)[0] for line in default.splitlines() if line and not line.startswith("#")]
    assert len(keys) == len(set(keys)), "Duplicate default key"
    docs = [PROJECT / "README.md", PROJECT / "在此目录运行.md", platform / "使用这套平台.md",
            platform / "research_platform/README.md"]
    for doc in docs:
        text = doc.read_text(encoding="utf-8-sig")
        assert "v10_GA与规模实验口径修正\\平台" not in text, "Stale command path"
        for link in re.findall(r"\]\(([^)]+)\)", text):
            assert (doc.parent / link).exists(), f"Broken documentation link: {doc}: {link}"
    if args.local_history:
        index = json.loads((PROJECT / "历史数据索引.json").read_text(encoding="utf-8"))
        original = Path(index["original_matrix"]["path"])
        for name, item in index["original_matrix"]["key_files"].items():
            assert hashlib.sha256((original / name).read_bytes()).hexdigest() == item["sha256"]
        metrics = ["host_model_kwh", "hardware_kwh", "server_kwh", "ups_kwh", "total_kwh", "started",
                   "finished", "blocked", "requested_mi", "delivered_mi", "migration_seconds", "cpu_error", "vm_count", "native_calls"]
        for current, old in [("maintenance_v1_ga_001", "smoke_ga_v10"),
                             ("maintenance_v1_bfdga_001", "learning_20261015_110124_887")]:
            def summary(name):
                with (platform / "research_platform/runs" / name / "summary.csv").open(encoding="utf-8-sig", newline="") as stream:
                    return list(csv.DictReader(stream))[0]
            now, before = summary(current), summary(old)
            assert all(now[k] == before[k] for k in metrics), "Simulation metrics changed: " + current
    print(f"PASS {protected} original files byte-identical; all {len(classified)} sources classified; docs and defaults verified; local history checked only with --local-history")


if __name__ == "__main__":
    main()
