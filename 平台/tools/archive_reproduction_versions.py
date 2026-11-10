"""Non-destructive, hash-verified iteration folders and a runnable current release."""
import argparse,csv,json,shutil,sys
from pathlib import Path
from research_platform_audit import sha

ROOT=Path(__file__).resolve().parents[1]
VERSIONS=[('v00_初始复现','初始版','首次仿真与图；当前源树不能冒充首次生产源码'),
 ('v01_供电模型与数据修正','供电修正版','公开完整数据、模型修正与旧版源码备份'),
 ('v02_论文思路对齐','论文对齐版','静态/动态/求解实验和逐图报告'),
 ('v03_公开在线迁移目的节点','公开迁移版','原生公开目的节点接入及核验'),
 ('v04_重建假设与参数对照','假设对照版','动态假设及求解轨迹对照'),
 ('v05_第二章逐页核查','论文核查版','第二章逐页证据、矛盾与加权口径'),
 ('v06_研究平台诊断与早期接口','诊断版','浮点超分配、编码及早期接口运行；不混入有效重复'),
 ('v07_研究平台核验基线','核验基线版','1096案例/27轨迹及两个接口验证，保留生产源码快照'),
 ('v08_十二图当前版本重跑','最新重跑版','当前源码重跑、十二图、567固定预算求解；另附可运行平台副本')]

def archive(run,archive_name='版本迭代'):
    if not archive_name.startswith('版本迭代') or Path(archive_name).name!=archive_name or any(x in archive_name for x in ['/', '\\', ':']):
        raise ValueError('Archive name must be one directory name beginning with 版本迭代')
    run=Path(run).resolve();target=ROOT/archive_name
    if run.parent!=ROOT/'research_platform/runs':raise ValueError('Run must be a direct child of research_platform/runs')
    checks=json.loads((run/'report/figure_checks.json').read_text(encoding='utf-8'))
    if checks['status']!='PASS':raise ValueError('Audited twelve figures required')
    if target.exists():raise FileExistsError('Archive already exists; retain it and use --archive-name 版本迭代_NEW_REVISION')
    entries={};runtime=[]
    def tree(version,relative):
        source=ROOT/relative
        if not source.exists():raise FileNotFoundError(source)
        files=[source] if source.is_file() else sorted(p for p in source.rglob('*') if p.is_file())
        for p in files:
            if p.is_symlink():raise ValueError('Symlink source not supported: '+str(p))
            if p in entries:raise ValueError('Duplicate historical classification: '+str(p))
            entries[p]=Path(version)/p.relative_to(ROOT)
    for item in ['results','figures','comparison','audit','config','说明','README.md','run.ps1']:
        tree(VERSIONS[0][0],item)
    tree(VERSIONS[1][0],'correction')
    for child in sorted((ROOT/'paper_alignment').iterdir()):
        if child.name not in ['public_migration','inference','chapter2_review']:tree(VERSIONS[2][0],str(child.relative_to(ROOT)))
    for index,part in [(3,'public_migration'),(4,'inference'),(5,'chapter2_review')]:tree(VERSIONS[index][0],'paper_alignment/'+part)
    diagnostic={'verified_20261013','mapping_smoke_20261013','mapping_smoke_v2_20261013','plugin_smoke_20261013'}
    validated={'verified_v2_20261013','mapping_verified_20261013','plugin_verified_20261013'}
    for child in sorted((ROOT/'research_platform/runs').iterdir()):
        if not child.is_dir():raise ValueError('Unexpected run file: '+str(child))
        if child.name in diagnostic:index=6
        elif child.name in validated:index=7
        elif child==run:index=8
        else:raise ValueError('Unclassified run; assign a version before archive: '+str(child))
        tree(VERSIONS[index][0],str(child.relative_to(ROOT)))
    for child in sorted((ROOT/'research_platform').iterdir()):
        if child.name=='runs':continue
        if child.name=='audit':
            for item in sorted(child.iterdir()):
                # A currently written archive log is not a stable historical input.
                # Save its completed snapshot separately after this process returns.
                if item.name.endswith('archive.log'):continue
                index=8 if item.name.startswith('rerun_v3') else 7
                tree(VERSIONS[index][0],str(item.relative_to(ROOT)))
        else:
            index=8 if child.name in ['README.md','图2-15至2-26重跑与版本归档计划.md'] else 7
            tree(VERSIONS[index][0],str(child.relative_to(ROOT)))
    for item in ['data','evidence']:tree('共享证据与数据',item)
    for p in ROOT.iterdir():
        if p.is_file() and p not in entries:tree('共享证据与数据',p.name)
    # A complete current execution tree: preserve each original relative path.
    for relative in ['src','lib','tools','config','research_platform/config','correction/inputs','paper_alignment/config','paper_alignment/inputs']:
        source=ROOT/relative
        for p in sorted(source.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:runtime.append((p,Path(VERSIONS[8][0])/'平台'/p.relative_to(ROOT)))
    for relative in ['build.ps1','run_research_platform.ps1','research_platform/README.md','research_platform/物理假设与论文依据.md',
            'correction/comparison/summary.json','research_platform/audit/custom_mapping.csv','research_platform/audit/plugin_smoke.properties']:
        runtime.append((ROOT/relative,Path(VERSIONS[8][0])/'平台'/relative))
    for n in range(15,27):runtime.append((ROOT/f'evidence/original_2-{n}.png',Path(VERSIONS[8][0])/'平台'/f'evidence/original_2-{n}.png'))
    required=sum(p.stat().st_size for p in entries)+sum(p.stat().st_size for p,_ in runtime)
    if shutil.disk_usage(ROOT).free<required*1.1:raise OSError('Insufficient archive disk space')
    if target.resolve().parent!=ROOT:raise ValueError('Archive target escaped intended workspace')
    target.mkdir();manifest=[]
    def copy(source,destination,category):
        dest=target/destination;dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():raise FileExistsError(dest)
        shutil.copy2(source,dest);expected=sha(source)
        if sha(dest)!=expected:raise OSError('Archive hash mismatch: '+str(dest))
        manifest.append(dict(category=category,source=str(source),archive_path=str(destination),bytes=source.stat().st_size,sha256=expected))
    for i,(source,dest) in enumerate(entries.items()):
        copy(source,dest,'historical_or_shared')
        if i%2000==0:print(f'archive historical {i+1}/{len(entries)}',flush=True)
    for source,dest in runtime:copy(source,dest,'current_runnable_copy')
    with (target/'文件校验清单.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(manifest[0]));w.writeheader();w.writerows(manifest)
    index=['# 版本迭代索引','', '本目录为经过SHA256校验的分类副本；原文件保留，未移动、删除或改写。日期是本次归档日期，不是所有历史版本的实际生产日期。',
        '', '| 版本目录 | 内容 | 查看与使用 |','|---|---|---|']
    for version,title,description in VERSIONS:
        (target/version).mkdir(exist_ok=True)
        index.append(f'| [{title}]({version}/版本说明.md) | {description} | 先看版本说明 |')
        note=[f'# {title}','',description,'', '归档保留原相对目录结构。源码真实性以对应运行的source_snapshot、provenance或既有manifest为准；没有生产源码快照的旧结果不赋予当前源码版本。历史报告保留其当时结论，诊断版不能作为有效重复。',
            '', '旧CSV中的绝对输入路径没有改写，因此直接审计历史副本仍可能引用原目录。原目录仍保留，可在那里复查；若迁移到另一台电脑，重新运行当前平台获得新路径和新来源，不把重定位副本伪装为原运行。',
            '', '文件完整性见上一层文件校验清单.csv。']
        if version==VERSIONS[8][0]:note+=['','最新结果位于 [十二图对照](research_platform/runs/'+run.name+'/report/逐图对照.html)。可执行代码、JAR与配置位于 [平台](平台/使用这套平台.md)。']
        (target/version/'版本说明.md').write_text('\n'.join(note)+'\n',encoding='utf-8')
    index+=['','[最新十二图对照]('+VERSIONS[8][0]+'/research_platform/runs/'+run.name+'/report/逐图对照.html)',
        '', '[平台使用与升级指南]('+VERSIONS[8][0]+'/平台/使用这套平台.md)',
        '', f'历史/公共文件 {len(entries)} 项，当前可运行副本 {len(runtime)} 项；合计 {required/1024**3:.3f} GiB。复制后逐文件SHA256相等。共享证据与数据目录保存完整公开轨迹及原图，避免每版重复。']
    (target/'版本索引.md').write_text('\n'.join(index)+'\n',encoding='utf-8')
    platform=target/VERSIONS[8][0]/'平台'
    guide=['# 使用与升级这套平台','', '推荐以本目录作为后续创新工作副本。它包含当前完整Java源码、CloudSim JAR、Python脚本及运行所需输入和配置，首轮运行会编译生成bin。历史大规模测试保存在上一层分类目录。',
        '', '## 常用命令','', '在PowerShell中执行（每次运行使用新的输出目录）：','', '```powershell',f"Set-Location -LiteralPath '{platform}'",
        '.\\run_research_platform.ps1 -Mode Test',
        '.\\run_research_platform.ps1 -Mode Single -Config research_platform/config/default.properties -Output research_platform/runs/my_experiment_001 -Method BFD-GA',
        '# 完整矩阵：1096案例、27轨迹；需要等待执行和独立核验',
        '.\\run_research_platform.ps1 -Mode Matrix -Output research_platform/runs/my_matrix_001',
        '# 追加图2-26固定预算实验和十二图（同一矩阵只执行一次benchmark）',
        "& 'H:/Company_project_study_PHD/SOFTWARE/01_JDK/jdk8u504-b01/bin/java.exe' -Xmx2g -cp 'bin;lib/*' repro.ResearchFigureBenchmark research_platform/runs/my_matrix_001",
        "& 'C:/Users/袁鼎善/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' tools/research_figure_report.py --run research_platform/runs/my_matrix_001",
        '# 复查已完成的新运行，不重新仿真',
        '.\\run_research_platform.ps1 -Mode Verify -Output research_platform/runs/my_experiment_001','```',
        '', 'Single支持FFD、BFD、GA、GGA和BFD-GA；外部完整Host列表用-Mapping，自动标为CUSTOM。图报告只适用于完整Matrix及其补充benchmark，不能用Single替代十二图实验。',
        '', '默认参数见research_platform/config/default.properties。先复制配置到新文件再调整：CPU初始容量、过载阈值、遗传参数、UPS模块结构、目的策略和迁移端点功率。Matrix内部会覆盖矩阵定义字段，实际参数以每例存档为准。',
        '', '源码入口：ResearchPlacement为放置求解器；ResearchPolicy.Controller/ResearchExampleController为在线策略接口；ResearchDatacenter为事件和功率核算；ResearchConfig为物理参数；ResearchFigureBenchmark为规模实验。避免同时更改算法与物理核算后只比较能耗。',
        '', '## 升级流程','', '1. 复制平台目录为新版本，保持本版副本与历史测试不变。',
        '2. 修改一个算法或参数类别；保留种子、输入、资源档次及核算规则作对照。',
        '3. 运行-Mode Test，再运行Single；检查report/independent_checks.json为PASS。',
        '4. 需要论文逐图对照时运行Matrix、ResearchFigureBenchmark及research_figure_report.py。',
        '5. 保存新目录、source_snapshot、provenance、配置与报告；比较服务量、能耗和迁移，不仅比较曲线外观。',
        '', '更详细的自定义Controller与物理边界说明见 [平台接口指南](research_platform/README.md) 和 [物理假设](research_platform/物理假设与论文依据.md)。平台副本中的该接口指南引用旧基线的链接，旧基线实际在v07目录；本版结果在平台目录外的v08/research_platform/runs中。',
        '', '依赖：Java8与包含numpy、matplotlib、Pillow的Python。启动脚本优先使用本机既有路径，缺失时回退PATH；换电脑需配置java/python及上述显式补充实验命令。公开原始完整数据和论文图片在版本根目录共享证据与数据中，本平台副本保留实际使用的输入子集及运行配置。',
        '', '图2-17原文矛盾、图2-20/23分母、图2-25账单条件外推、图2-26未知停止规则仍在报告中保留。通过核验表示声明模型自洽，不表示作者全部细节唯一复原。']
    (platform/'使用这套平台.md').write_text('\n'.join(guide)+'\n',encoding='utf-8')
    result=dict(status='PASS',historical_files=len(entries),runnable_files=len(runtime),total_bytes=required,versions=9,all_copied_sha256_verified=True,source_run=str(run))
    (target/'归档核验.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS version archive',len(manifest),'files',target,flush=True)
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--archive-name',default='版本迭代');args=p.parse_args();archive(args.run,args.archive_name)
