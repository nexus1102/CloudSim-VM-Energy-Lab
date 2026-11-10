"""Final explanation from actual v10 simulations; failure to recover a thesis trend remains explicit."""
import argparse,json,shutil
from pathlib import Path
from paper_audit import rows
from research_platform_audit import sha,close
from research_figure_report_v09 import write

ROOT=Path(__file__).resolve().parents[1]

def main(directory):
    run=Path(directory).resolve();out=run/'report';bench=out/'figure_benchmark'
    for f in [out/'independent_checks.json',out/'figure_checks.json',bench/'independent_checks.json']:
        if json.loads(f.read_text(encoding='utf-8'))['status']!='PASS':raise AssertionError(f)
    old=ROOT/'research_platform/runs/ga_fix_v09_20261013';previous={r['prefix']:r for r in rows(old/'summary.csv')}
    current=list(rows(run/'summary.csv'));now={r['prefix']:r for r in current};same=0;equal_groups=0
    for r in current:
        if r['method']!='BFD-GA':
            for k in ['server_kwh','ups_kwh','total_kwh','requested_mi','delivered_mi','finished']:close(float(r[k]),float(previous[r['prefix']][k]))
            same+=1
        if r['kind']=='static' and r['method']=='BFD-GA':
            base=now[r['prefix'].replace('_BFD-GA_','_BFD_')];close(float(r['server_kwh']),float(base['server_kwh']));equal_groups+=1
    if sha(run/'inputs/static_30.csv')!=sha(bench/'input.csv'):raise AssertionError('Matrix and search-study input mismatch')
    frontier=list(rows(bench/'frontier.csv'));check=list(rows(bench/'checks.csv'));agg=list(rows(out/'aggregate.csv'))
    shutil.copy2(old/'report/ga_ablation.csv',out/'旧初始化与算子消融.csv')
    shutil.copy2(old/'report/ga_static_before_after.csv',out/'旧GA异常前后对照.csv')
    lines=['# GA与图2-26最终修正说明（v10）','',
        '本轮修复了GA的搜索退化、BFD-GA交叉与变异机制，以及“无规模通过=无法放置”的报告误判，重新执行全部1096个CloudSim案例和规模试验。**原论文完整排序和图2-26逐点形状仍未复现；不能把核验PASS写成论文趋势完全恢复。**','',
        '## 直接原因与上一轮遗漏','',
        '1. 旧GA随机分到全部100台Host，修复只解决超载而不解决分散，低负载178 VM案例仍占69台Host；逐基因5%随机改Host使1004 VM每子代期望50.2次变异，破坏聚集。能耗矩阵采用明确声明的随机可行打包初始种群、等价Host标签对齐及一次可行VM变异，178 VM案例降至12台，1004 VM降至78台。消融证明主要收益来自初始化，不应声称算子普遍更优。',
        '2. 旧规模判据是共同总功率1%：不包含作者停止条件，还可能要求服务器目标GA达到供电目标参考值。BFD-GA预置BFD解导致初始即过线。v09换0.01W仍有同类缺陷：GA可以重组VM，BFD-GA却固定BFD分组，两者最优功率不必相等。小规模穷举已证明这种不可达差距。',
        '3. v09把针对直接GA的一次变异限制也套给BFD-GA，导致长机架染色体每代变异机会过少；BFD-GA的等价机架编号又未在交叉前对齐。本轮用独立开关research.rack.operators=aligned_gene修复：同构UPS机架标签对齐，每机架基因按5%概率变异；保留第一步BFD完整分组和机架容量检查。旧行为可切回legacy。',
        '4. v09可行打包初始种群对少量VM可能在零代已经最优；将其拿来测“传统直接GA的搜索规模”会把预处理收益误算作遗传搜索。新规模实验使用random_hosts及修复，关闭GA/GGA的BFD种子，BFD-GA关闭集中BFD预置种子。能耗主矩阵继续采用可行打包的工程重建，不能将这两种初始化混称为作者唯一实现。',
        '5. 旧报告固定写“BFD-GA优于所有算法”已删除，排序从本次CSV计算；新版本不强迫GA/GGA及FFD/BFD名次。','',
        '## 原论文直接支持与缺失','',
        '核对第二章PDF第39/43/45/46/55/60页（论文印刷页30/34/36/37/46/51）：传统目标为服务器功率、两步法第一步BFD、第二步以服务器为基因位记录机架编号并优化服务器+UPS总功率，表2-3描述轮盘赌、交叉和变异。2.6.5给出迭代预算与规模，却未给精度、终止规则、各规模VM请求值及遗传参数。正文48代与图轴45代也有差别，本轮两者均实际计算。',
        '', '“每Host最多4台VM”出现在100 VM、100 Host、5 UPS的搜索空间示例，不能证明是全部仿真的真实硬件参数。新规模实验同时报告当前128VM资源上限及4VM限制情景；后一情景通过显式VM RAM=Host RAM/4实现，其余数据和功率公式相同。未把4VM限制偷偷加到178–1004 VM静态矩阵，否则大规模会真实不可行。','',
        '## 图2-26的新测量定义','',
        '- 可行性：每VM完整分配，CPU/RAM/BW/存储、Host/机架功率约束满足。所有1296个求解及82458个逐代方案均可行；“0命中”只能表示未达目标质量，不能叫GA放置失败。',
        '- 目标质量：GA/GGA按原生服务器功率目标，BFD-GA按固定BFD分组的总功率目标。参照来自300代同类搜索空间的最好可行候选，没有跨搜索空间套用不可达总功率。',
        '- 主判据：GA/GGA达到参考Host数量（1e-7W仅保护舍入）；BFD-GA满足P−P_ref≤0.01×(P_BFD集中−P_ref)+1e-7W。1%以可优化功率差额为分母，剔除不能由机架优化改变的常数项；不再用1%整个机房总功率。严格1e-7W命中曲线也完整保留。',
        '- 规模前沿：九个离散规模里三个种子全部达到声明目标的最大值；不保证更小规模全部通过，不能解释为理论容量。实际耗时含第一步BFD、初始化和求解，另输出59代三种子中位数；JIT和运行顺序影响时间，不将代数直接换成秒数。',
        '- 上述判据是可验证的工程重建，不是作者公开规则或全局最优证书。1%差额规则在修正机架算子的最终测试之前记录，两种精度和两种资源情景都报告，不选择更像原图的一种。','',
        '| 资源情景/方法 | 3 | 6 | 12 | 28 | 45 | 48 | 59 |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for p in ['current128','example4']:
        for m in ['GA','GGA','BFD-GA']:
            vals=[next(r['max_tested_quality_n'] for r in frontier if r['profile']==p and r['method']==m and int(r['budget'])==b) for b in [3,6,12,28,45,48,59]]
            lines.append('| '+p+'/'+m+' | '+' | '.join(vals)+' |')
    lines+=['', 'GA已不再全为0，但BFD-GA在当前资源主判据下仍可很早达到288台测试上限而变平；4VM情景主判据由230升至288，严格精度却长期只有12台三次全命中。**这说明“必须是某条斜线”并非代码正确性的充分条件。原图逐点上升还取决于未公开的工作负载、资源限制、求解精度和停止方法；不能故意延迟成功或逐规模调容差造出它。**全部失败、早期通过和不同精度都可复核。',
        '', '![两资源情景](figures/figure_2-26.png)','', '![所有测试点命中率](全部规模命中率.png)','', '![严格精度](严格精度规模.png)','', '![实际耗时](实际计算耗时.png)',
        '', '## 一条必须遵守的能耗恒等式','',
        '在本章线性服务器模型下，P_server=N_on×218.3+131.7×ΣVM物理CPU需求。两步法仅将第一步BFD的完整服务器组换机架，N_on和总需求均不变，所以静态BFD-GA与BFD服务器功率必然相等，节省只能来自UPS。本次全部168组静态BFD-GA/BFD对应案例均验证这一恒等式。若要求保持完整BFD分组却让BFD-GA服务器分量严格低于BFD，就是额外改变算法或算例，不能靠调整功率模型实现。',
        '', f'与v09相比，{same}个非BFD-GA案例的服务器/UPS能耗、请求/交付量和迁移数保持一致；只有BFD-GA启用新增机架算子。静态BFD分组服务器功率恒等{equal_groups}组通过。所有Host功率→UPS模块→真实CloudSim事件积分仍按同一物理模型执行，没有后处理拟合能耗。',
        '', '## 动态能耗及验收边界','', '| 方法 | 仅过载迁移kWh | 补充轻载整合kWh |','|---|---:|---:|']
    for m in ['FFD','BFD','GA','GGA','BFD-GA']:
        vals=[next(float(r['mean_kwh']) for r in agg if r['scenario']=='n_plus_1_standby_cap0.9_'+ctl and r['method']==m) for ctl in ['threshold','consolidation']]
        lines.append(f'| {m} | {vals[0]:.3f} | {vals[1]:.3f} |')
    lines+=['', '主矩阵1096例、27条轨迹已独立核验；十二图PNG/SVG均重绘。正文184.98 kWh及原图数字化基准分别报告，15%容差分别判断。轻载整合为补充假设、完整控制细节仍未知；年度成本是条件外推。图2-18/19/21/22的GA异常能耗已修正，但完整算法顺序不保证恢复。','',
        '查阅[全部指标](aggregate.csv)、[双基准偏差](paper_energy_comparison.csv)、[完整规模数据](figure_benchmark/checks.csv)、[每代真实方案](figure_benchmark/histories.csv)、[旧初始化消融](旧初始化与算子消融.csv)。旧v00–v09及本次第一次规模诊断保留；v10可运行副本与指南位于版本迭代/v10_GA与规模实验口径修正。']
    (out/'GA与图2-26最终修正说明.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (out/'final_fix_checks.json').write_text(json.dumps(dict(status='PASS',unchanged_non_bfd_ga_cases=same,bfd_server_identity_cases=equal_groups,benchmark_input_hash=sha(bench/'input.csv')),ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS v10 explanation and fixed-BFD server-power identity',equal_groups)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);main(p.parse_args().run)
