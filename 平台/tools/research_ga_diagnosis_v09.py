"""Evidence-led v09 diagnosis; never changes inputs, simulations or acceptance criteria."""
import argparse,html,json,shutil,itertools
from pathlib import Path
import numpy as np
from paper_audit import rows,settings
from research_platform_audit import module_loss
from research_figure_report_v09 import plt,COLORS,write

ROOT=Path(__file__).resolve().parents[1]
METHODS=['GA','GGA','BFD-GA'];SIZES=[5,10,12,30,40,80,150,230,288];BUDGETS=[3,6,12,28,45,48,59]

def main(directory):
    run=Path(directory).resolve();out=run/'report';bench=out/'figure_benchmark'
    for p in [out/'independent_checks.json',bench/'independent_checks.json',out/'figure_checks.json']:
        if json.loads(p.read_text(encoding='utf-8'))['status']!='PASS':raise AssertionError(p)
    checks=list(rows(bench/'checks.csv'));history=list(rows(bench/'histories.csv'));frontier=list(rows(bench/'frontier.csv'))
    old=ROOT/'research_platform/runs/figure_rerun_20261013_v3'
    before={r['prefix']:r for r in rows(old/'summary.csv')};after=list(rows(run/'summary.csv'))
    unchanged=0
    for r in after:
        if r['method'] in ['FFD','BFD']:
            for k in ['server_kwh','ups_kwh','total_kwh','requested_mi','delivered_mi','finished']:
                if not np.isclose(float(r[k]),float(before[r['prefix']][k]),rtol=0,atol=1e-9):raise AssertionError(('Baseline changed',r['prefix'],k))
            unchanged+=1
    delta=[]
    for level in [10,70]:
        name=f'static_cap0.9_N+1DC_{level}_GA_101';new=next(r for r in after if r['prefix']==name);prev=before[name]
        def hosts(folder):return len({r['host_id'] for r in rows(folder/'cases'/f'{name}_initial.csv')})
        delta.append(dict(level=level,old_hosts=hosts(old),new_hosts=hosts(run),old_total_w=float(prev['total_kwh'])*12000,new_total_w=float(new['total_kwh'])*12000))
    write(out/'ga_static_before_after.csv',delta)
    shutil.copy2(ROOT/'research_platform/ga_fix_v09/ga_ablation.csv',out/'ga_ablation.csv')
    shutil.copy2(ROOT/'research_platform/ga_fix_v09/旧版根因证据.json',out/'旧版根因证据.json')
    fig,axs=plt.subplots(1,3,figsize=(15,5))
    for ax,m in zip(axs,METHODS):
        grid=np.array([[sum(r['within_absolute_precision']=='True' for r in checks if r['method']==m and int(r['n'])==n and int(r['budget'])==b) for b in BUDGETS] for n in SIZES])
        ax.imshow(grid,vmin=0,vmax=3,cmap='Blues',aspect='auto');ax.set_xticks(range(7),BUDGETS);ax.set_yticks(range(9),SIZES)
        for i in range(9):
            for j in range(7):ax.text(j,i,f'{grid[i,j]}/3',ha='center',va='center',color='white' if grid[i,j]>1 else 'black',fontsize=8)
        ax.set_title(m);ax.set_xlabel('实际代数预算');ax.set_ylabel('测试VM规模')
    fig.suptitle('全部测试点通过种子数：相同总功率目标，300代参照+0.01W');fig.tight_layout();fig.savefig(out/'全部规模通过热图.png');plt.close(fig)
    fig,axs=plt.subplots(1,3,figsize=(15,4));hitrows=[]
    for ax,n in zip(axs,[40,150,288]):
        reference=next(float(r['reference_w']) for r in checks if int(r['n'])==n)
        for m,color in zip(METHODS,COLORS[2:]):
            series=[]
            for seed in [101,202,303]:
                hs=[r for r in history if int(r['n'])==n and int(r['budget'])==300 and r['method']==m and int(r['seed'])==seed]
                if len(hs)!=301:raise AssertionError('Full history missing')
                series.append([float(r['objective_w'])-reference for r in hs])
            a=np.array(series);ax.plot(range(301),np.median(a,axis=0),label=m,color=color)
            ax.fill_between(range(301),a.min(axis=0),a.max(axis=0),alpha=.12,color=color)
        ax.axhline(.01,color='gray',ls='--',lw=.7);ax.set_yscale('symlog',linthresh=.01);ax.set_title(f'{n} VM：中位数及三种子范围')
        ax.set_xlabel('代数（0包含初始化）');ax.set_ylabel('距300代共同最好候选 / W');ax.legend(fontsize=8)
    fig.tight_layout();fig.savefig(out/'实际逐代收敛.png');plt.close(fig)
    for r in checks:
        if int(r['budget'])==300:hitrows.append({k:r[k] for k in ['n','method','seed','first_hit_gen','gap_w','solve_ms']})
    write(out/'首次达到目标.csv',hitrows)
    # Exhaustive small group spaces distinguish search failure from a structural gap.
    config=settings(bench/'config.properties');placements=list(rows(bench/'placements.csv'));exact=[]
    for n in [5,10,12,30,40]:
        base=[r for r in placements if r['method']=='BFD' and int(r['n'])==n]
        ids=sorted({int(r['host']) for r in base});watts=[float(config['host.idle.w'])+(float(config['host.max.w'])-float(config['host.idle.w']))*sum(float(r['demand']) for r in base if int(r['host'])==h) for h in ids]
        if len(watts)>6:continue
        best=float('inf')
        for assignment in itertools.product(range(5),repeat=len(watts)):
            rack=np.bincount(assignment,weights=watts,minlength=5)
            best=min(best,sum(watts)+sum(module_loss(x,config) for x in rack))
        reference=next(float(r['reference_w']) for r in checks if int(r['n'])==n)
        exact.append(dict(n=n,bfd_groups=len(ids),enumerated_assignments=5**len(ids),exact_bfd_group_min_w=best,joint_reference_w=reference,structural_gap_w=best-reference))
    write(out/'BFD分组小规模穷举.csv',exact)
    lines=['# v09 GA异常根因与修正报告','',
        '已完成实现修正和重新仿真。GA不再出现“全部测试规模不通过”，BFD-GA不再从3代起所有预算均为288台；但完整论文排名、图2-26逐点曲线及成本优势仍未恢复。此前将独立核验PASS或固定排序文字解释为复现成功是不充分的，本报告按实际数据更正。','',
        '## 1. 根因与修正','',
        '- 旧GA随机把VM分到100台Host，并仅修复超载：低负载也占用大量服务器，空载功率被放大。新版本采用随机顺序、随机可行驻留Host打包初始化；不向传统GA/GGA注入BFD答案。该启发式初始化是明确的工程重建，不能冒称作者原始实现。',
        '- 旧单点交叉未对齐父代的等价Host编号，会拆散相同的分组结构。新版本先做一一标签对齐：服务器目标允许全局等价重编号，总功率目标只在同一机架内对齐，保留父代UPS负载。',
        '- 旧GA按每个基因5%概率随机改Host，1004 VM每子代期望50.2次变异。新GA以每个染色体5%概率执行一次可行驻留Host迁移；BFD-GA同概率变异一个机架基因。概率作用层级改变必须声明，不能仅写“变异率未变”。GGA保留分组变异。',
        '- 旧图2-26采用总功率1%容差，且BFD-GA已预置BFD可行解，初始解很容易过线。因此“GA 0通过”是精度判据未过，不是CloudSim放置失败；BFD-GA平线是该试验口径造成的真实结果。新速度实验关闭集中BFD预置种子、保留第一步BFD分组，统一总功率目标，以独立300代求解的共同最好候选+0.01W作计算判据。0.01W在本轮结果出来前预先记录，不是作者判据或测量精度。',
        '- 主矩阵的传统GA/GGA仍使用服务器功耗目标，BFD-GA使用总功耗；速度补充实验统一total，故不能混同为完全相同实验。主矩阵BFD-GA保留BFD预置种子，而速度实验关闭；两套配置分别封存。',
        '- 报告原来写死“BFD-GA优于其余方法”，在新数据上不成立，已改为从实际CSV计算排序。','',
        '## 2. 同配置前后对比','',
        'N+1 DC、cap=0.9、seed=101、种群20、30代的实际静态案例；除声明的算法变化外，数据、物理模型和控制器相同。','',
        '| 目标负荷 | 旧GA启用Host | 新GA启用Host | 旧总功率W | 新总功率W |','|---|---:|---:|---:|---:|']
    for r in delta:lines.append(f'| {r["level"]}% | {r["old_hosts"]} | {r["new_hosts"]} | {r["old_total_w"]:.3f} | {r["new_total_w"]:.3f} |')
    lines+=['',f'FFD/BFD共{unchanged}组案例的服务器能耗、UPS能耗、请求量、实际交付量及完成迁移数与v08一致。',
        '', '独立消融使用种群40、30代、seed=101，两规模×四种初始化/算子组合×三算法，共24次，详见[原始消融CSV](ga_ablation.csv)。178 VM旧随机初始化GA最终61台，单改算子60台，改可行初始化12台；1004 VM对应97、99、78台。**收益主要来自可行初始化；仅改算子在1004 VM反而更差，不能归功于算子普遍更优。**这些消融不是多种子的统计优越性证明。',
        '', '## 3. 真实动态结果与论文比较','',
        '以下为N+1 DC、cap=0.9三种子均值。第一列控制仅用论文明确的90%过载迁移；第二列另加已声明的轻载整合假设。两种控制都报告，不选更接近原文的一种代替全部结论。','',
        '| 方法 | 仅过载迁移 kWh | 补充轻载整合 kWh | 正文偏差%（整合） | 图像偏差%（整合） |','|---|---:|---:|---:|---:|']
    aggregate=list(rows(out/'aggregate.csv'));cmp={r['method']:r for r in rows(out/'paper_energy_comparison.csv')}
    for m in ['FFD','BFD','GA','GGA','BFD-GA']:
        a=[next(float(r['mean_kwh']) for r in aggregate if r['scenario']=='n_plus_1_standby_cap0.9_'+ctl and r['method']==m) for ctl in ['threshold','consolidation']]
        lines.append(f'| {m} | {a[0]:.3f} | {a[1]:.3f} | {float(cmp[m]["text_deviation_pct"]):+.2f} | {float(cmp[m]["image_deviation_pct"]):+.2f} |')
    lines+=['','整合场景GA均值185.872低于BFD-GA 186.287 kWh，差距约0.22%，且小于各组三种子标准差，不能判定显著优劣。原文完整排序未恢复。所有方法的正文能耗偏差在15%内，但图像基准仍有四种方法超过15%；数值接近正文不等于算法趋势全部一致。服务缺口与每单位实际交付量能耗见[结果报告](结果报告.md)。',
        '', '## 4. 图2-26：已修正和仍不能恢复的部分','',
        '| 算法 | 3代 | 6代 | 12代 | 28代 | 45代 | 48代 | 59代 |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for m in METHODS:lines.append('| '+m+' | '+' | '.join(next(r['max_tested_passing_n'] for r in frontier if r['method']==m and int(r['budget'])==b) for b in BUDGETS)+' |')
    lines+=['','BFD-GA在3代到6代出现150→288上升，随后到达已测试上限。该结果不能写成“原论文图2-26恢复”。原文没有公开求解精度、终止条件、每规模负载、种群配置和完整代码，原曲线不可被唯一推导。288台早早达到目标并不必然是程序错误，也可能是该快照与判据较易；不能人为让算法延迟成功以画斜线。',
        '', '最大通过规模是已测离散点中的最大值，不是连续能力边界。例如BFD-GA 3代通过5/30/80/150，但10/12/40未三次全过，230/288也未全过；实例难度不随VM数必然递增。完整热图避免掩盖这些“空洞”。',
        '', '![全部规模通过热图](全部规模通过热图.png)','', '![真实逐代目标收敛](实际逐代收敛.png)',
        '', '首次命中来自每一代真实方案，而非插值。0代已满足判据的解保留为0；未命中保留空值。详见[首次命中CSV](首次达到目标.csv)、[全点判据](figure_benchmark/checks.csv)、[每代完整方案](figure_benchmark/histories.csv)。300代参照是固定预算最好可行候选，不能证明全局最优或已经收敛；相同种子短预算是长预算的前缀，不是独立统计重复。求解毫秒数包括第一步，但受硬件、JIT和运行顺序影响，未据此宣称速度优势。',
        '', '## 5. 图2-18/19/21/22/24/25与平台状态','',
        '十二图均由v09新运行重新生成。四张静态功率图中GA的异常多Host现象已消除；GA/GGA能耗接近、出现并列是线性服务器模型与整数Host数共同导致，不应强行拉开。图2-24的实际排序和双基准偏差已公开。图2-25仍使用表2-1时间权重，负节省率原样保留，行业金额仍是账单反推的条件估计；不能宣称恢复全部成本优势。',
        '', '真实Power Supply Aware数据中心仍执行Host实时功率→机架UPS输出→模块损耗→逐事件能耗积分，未用事后曲线拟合代替CloudSim。模型自洽、算法质量和与论文一致性是三项独立判断。缺失作者数据与控制细节的影响仍在。',
        '', '## 6. 核验与使用','',
        '1096个CloudSim案例、27条主矩阵求解轨迹独立核验PASS；速度实验648次遗传求解、9个BFD参考和41229个逐代实际方案全部复算PASS。旧v00–v08结果保留。主配置为research_platform/ga_fix_v09/config.properties，新算子可用research.genetic.operators=legacy切回旧行为。完整重跑命令见v09平台使用指南。']
    lines+=['','## 附表：固定BFD分组的可达下界','',
        '对不超过6个BFD服务器组的案例穷举所有机架分配，保持第一步分组不变。两步法固定分组后的最优值可以高于允许重组VM的共同参照，因此未达到共同精度未必是搜索没有收敛。此测试衡量共同解质量，不能命名为“算法不能求解”。[穷举明细](BFD分组小规模穷举.csv)。',
        '', '| VM数 | BFD组数 | 穷举组合 | 比共同参照高W |','|---|---:|---:|---:|']
    for r in exact:lines.append(f'| {r["n"]} | {r["bfd_groups"]} | {r["enumerated_assignments"]} | {r["structural_gap_w"]:.9f} |')
    (out/'GA异常根因与修正报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    page='<meta charset="utf-8"><title>v09求解过程核验</title><style>body{max-width:1300px;margin:25px auto;font:16px/1.7 sans-serif}img{width:100%}pre{white-space:pre-wrap}</style><a href="逐图对照.html">返回十二图</a>'
    page+='<h1>完整测试网格及实际优化过程</h1><p>3/3表示全部种子达到声明精度；最大通过尺寸不等于连续能力。曲线显示中位数及三种子范围。</p>'
    page+='<img src="全部规模通过热图.png"><img src="实际逐代收敛.png"><pre>'+html.escape('\n'.join(lines))+'</pre>'
    (out/'求解过程核验.html').write_text(page,encoding='utf-8')
    (out/'ga_diagnosis_checks.json').write_text(json.dumps(dict(status='PASS',unchanged_ffd_bfd_cases=unchanged,ablation_solves=24,static_comparisons=delta),ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS GA diagnosis, unchanged baselines',unchanged,'and full grid visualizations')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);main(p.parse_args().run)
