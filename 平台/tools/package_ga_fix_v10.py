"""Add a runnable v10 and reviewable reports without modifying sealed historical versions."""
import argparse,csv,json,shutil
from pathlib import Path
from research_platform_audit import sha

ROOT=Path(__file__).resolve().parents[1]

def package():
    dest=ROOT/'版本迭代/v10_GA与规模实验口径修正';platform=dest/'平台'
    if dest.exists():raise FileExistsError('v10 version exists; never overwrite sealed versions')
    run=ROOT/'research_platform/runs/ga_fix_v10_20261013'
    for f in ['independent_checks.json','figure_checks.json','final_fix_checks.json']:
        if json.loads((run/'report'/f).read_text(encoding='utf-8'))['status']!='PASS':raise AssertionError(f)
    platform.mkdir(parents=True)
    for relative in ['src','lib','tools','config','correction/inputs','correction/comparison','paper_alignment/config','paper_alignment/inputs','evidence','research_platform/config','research_platform/audit']:
        shutil.copytree(ROOT/relative,platform/relative,ignore=shutil.ignore_patterns('__pycache__','*.log'),dirs_exist_ok=False)
    for relative in ['build.ps1','run_research_platform.ps1','research_platform/物理假设与论文依据.md']:
        (platform/relative).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/relative,platform/relative)
    shutil.copy2(ROOT/'research_platform/config/default.properties',platform/'research_platform/config/legacy_v08.properties')
    shutil.copy2(ROOT/'research_platform/ga_fix_v10/config.properties',platform/'research_platform/config/default.properties')
    # Small immutable baseline tables support the final before/after explanation, not replay/Verify of old raw runs.
    baseline=platform/'research_platform/runs/ga_fix_v09_20261013';(baseline/'report').mkdir(parents=True)
    for relative in ['summary.csv','report/ga_ablation.csv','report/ga_static_before_after.csv']:
        shutil.copy2(ROOT/'research_platform/runs/ga_fix_v09_20261013'/relative,baseline/relative)
    shutil.copytree(run/'report',dest/'结果')
    (dest/'审计与生产依据').mkdir()
    for name in ['run_config.properties','benchmark_config.properties','summary.csv','provenance.csv','completed.txt']:
        shutil.copy2(run/name,dest/'审计与生产依据'/name)
    for name in ['tests.log','audit_fixed.log']:
        shutil.copy2(ROOT/'research_platform/ga_fix_v10'/name,dest/'审计与生产依据'/name)
    shutil.copy2(ROOT/'research_platform/GA与规模实验_v10_计划.md',dest/'审计与生产依据/计划.md')
    guide=fr'''# v10 使用与升级

本版本默认配置已启用GA可行打包与Host标签对齐、BFD-GA机架标签对齐及逐机架基因变异。传统GA/GGA目标仍为server_only，BFD-GA目标为total。对比报告包含全部限制，原作者完整排名和图2-26逐点形状尚未恢复。

在PowerShell运行，每次指定新的输出目录：

```powershell
Set-Location -LiteralPath '{platform}'
.\run_research_platform.ps1 -Mode Test
.\run_research_platform.ps1 -Mode Single -Output research_platform/runs/my_ga_001 -Method GA
# 1096个CloudSim案例和27条主求解轨迹
.\run_research_platform.ps1 -Mode Matrix -Output research_platform/runs/my_matrix_001
# 1296次原生目标规模求解（两个资源假设）
& 'H:/Company_project_study_PHD/SOFTWARE/01_JDK/jdk8u504-b01/bin/java.exe' -Xmx2g -cp 'bin;lib/*' repro.ResearchFigureBenchmarkV10 research_platform/runs/my_matrix_001 research_platform/runs/my_matrix_001/report/figure_benchmark
& 'C:/Users/袁鼎善/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' tools/research_figure_report_v10.py --run research_platform/runs/my_matrix_001
& 'C:/Users/袁鼎善/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' tools/research_ga_final_v10.py --run research_platform/runs/my_matrix_001
# 仅核验已完成的新Single/Matrix，不能核验下述摘要基线目录
.\run_research_platform.ps1 -Mode Verify -Output research_platform/runs/my_ga_001
```

Single支持FFD/BFD/GA/GGA/BFD-GA。图报告只能用于完整Matrix及其规模试验。默认配置见research_platform/config/default.properties，旧配置另存legacy_v08.properties。当前代码保留旧算子：research.genetic.operators=legacy、research.rack.operators=legacy。仅切换这些字段不能等同全部旧版本，复查历史使用封存来源。

创新入口：src/repro/ResearchPlacement.java（放置）、ResearchPolicy.Controller与ResearchExampleController（在线选择/目的节点）、ResearchDatacenter（事件和能耗）、ResearchConfig（物理参数）。研究者先复制平台为新工作版本，改一个算法类别，再Test、Single、Matrix。输入同一CSV、种子、交付工作量与物理模型共同控制；不要以曲线外观替代验收。

research_ga_final_v10.py用于本固定版本对照，包含“非BFD-GA结果应与旧基线不变”的断言。创新改动后不要机械执行该历史等同断言，应另写与创新范围对应的核验；research_figure_report_v10.py仍负责当前声明模型的真实数据与图表。

规模基准刻意使用random_hosts、无BFD种子及原生目标，测试搜索能力；能耗矩阵使用feasible_packing。这两种初始化用途和所有覆盖参数都存档，不能混称同一作者实现。机架标签对齐适用当前同构UPS；扩展异构供电时需关闭或按同型设备限制置换。两资源情景都显示，4VM是论文示例而非已确认实验参数。

结果在[十二图页](../结果/逐图对照.html)和[最终修正说明](../结果/GA与图2-26最终修正说明.md)。大矩阵的全部原始事件/CSV保留在 `{run}`；本版本复制可查看报告、规模全方案、配置/来源与可运行程序，没有重复复制上千案例原始CSV。不要对摘要基线ga_fix_v09_20261013执行Verify：它只提供最终解释所需旧表。实际原件仍在结果根目录对应运行下。

依赖为Java8和含numpy/matplotlib/Pillow的Python。换电脑需配置PATH或替换显示的既有Java/Python路径。遗传算子、成功判据、原始日期缺失及迁移控制仍有声明的重建假设；报告同时保留正文和图像偏差。
'''
    (platform/'使用这套平台.md').write_text(guide,encoding='utf-8')
    (platform/'research_platform/README.md').write_text('# 当前v10平台\n\n[运行与升级](../使用这套平台.md)。默认已启用本轮修正。原始1096例事件文件位于结果根目录ga_fix_v10_20261013，版本目录的“结果”为报告与规模试验副本。\n',encoding='utf-8')
    (dest/'README.md').write_text('# v10 GA与规模实验口径修正\n\n[十二图对照](结果/逐图对照.html) · [根因与结果](结果/GA与图2-26最终修正说明.md) · [平台使用](平台/使用这套平台.md)\n\n全部原始主矩阵位于 '+str(run)+'，此版为可运行程序、可查看报告和完整规模方案的增量封存。\n',encoding='utf-8')
    index=ROOT/'版本迭代/版本索引_v10.md'
    if index.exists():raise FileExistsError(index)
    index.write_text('# 版本索引（v10新增）\n\n[旧v00–v08分类](版本索引.md)\n\n- v09诊断与初步修正：结果根目录research_platform/runs/ga_fix_v09_20261013；未宣称原图恢复。\n- [v10修正和平台](v10_GA与规模实验口径修正/README.md)：新1096案例、1296次规模求解，原生目标及两种精度/资源假设；原图形状仍明确未恢复。\n',encoding='utf-8')
    records=[dict(path=str(p.relative_to(dest)),sha256=sha(p)) for p in sorted(dest.rglob('*')) if p.is_file()]
    with (dest/'文件校验清单.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['path','sha256']);w.writeheader();w.writerows(records)
    if any(sha(dest/r['path'])!=r['sha256'] for r in records):raise AssertionError('Copy hash mismatch')
    (dest/'封存核验.json').write_text(json.dumps(dict(status='PASS',files=len(records),original_run=str(run),raw_matrix_cases_copied=False),ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS version package',len(records),'files')

if __name__=='__main__':package()
