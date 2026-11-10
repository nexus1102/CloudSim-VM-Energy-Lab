"""Evidence-based destination report; author evidence and replacement policies are separated."""
from pathlib import Path
import csv,json,math,hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from paper_audit import settings
ROOT=Path(__file__).resolve().parents[1];R=ROOT/'paper_alignment/public_migration'
METHODS=['FFD','BFD','GA','GGA','BFD-GA'];SEEDS=['101','202','303','404','505']
plt.rcParams.update({'font.family':['Microsoft YaHei','SimHei'],'axes.unicode_minus':False,'font.size':10,'savefig.dpi':180})
def rows(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def bins(p):
    out=np.zeros(288)
    for v in rows(Path(str(p)+'_segments.csv')):
        a,b=float(v['begin_s']),float(v['end_s']);power=float(v['server_w'])+float(v['ups_loss_w'])
        for k in range(int(a//300),min(288,int(math.ceil(b/300)))):out[k]+=power*max(0,min(b,300*(k+1))-max(a,300*k))/300
    return out
def markdown_table(header,data):
    return '\n'.join(['| '+' | '.join(header)+' |','| '+' | '.join(['---']*len(header))+' |']+['| '+' | '.join(map(str,row))+' |' for row in data])
def main():
    audit=json.loads((R/'audit/independent_checks.json').read_text(encoding='utf-8'))
    if audit['status']!='PASS' or audit['runs']!=140:raise RuntimeError('Complete 140-case independent audit required')
    (R/'report').mkdir(exist_ok=True);(R/'figures').mkdir(exist_ok=True)
    data=rows(R/'results/summary.csv');old=rows(ROOT/'paper_alignment/results/dynamic_summary.csv')
    historical={k.replace('\\','/'):v for k,v in json.loads((ROOT/'paper_alignment/audit/final_manifest.json').read_text(encoding='utf-8')).items()}
    for name in ['PaperPlacement','SupplyPowerModel','PaperHost','PowerSupplyAwareDataCenter','PaperRun','PaperTrace']:
        rel=f'src/repro/{name}.java'
        if hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()!=historical[rel]:raise RuntimeError('Historical baseline physics/initial algorithm changed: '+rel)
    input_hashes={k.replace('\\','/'):v for k,v in json.loads((ROOT/'paper_alignment/audit/source_input_hashes.json').read_text(encoding='utf-8')).items()}
    for day in ['20110303','20110306','20110309']:
        rel=f'correction/inputs/cohort25_{day}.csv'
        if hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()!=input_hashes[rel]:raise RuntimeError('Historical baseline input changed: '+rel)
    keys=['hosts','racks','step.seconds','host.mips','host.ram.mb','host.bandwidth.kbps','host.storage.mb','vm.mips','vm.ram.mb','host.idle.w','host.max.w','cpu.trigger','packing.cap','ups.usable.w','ups.factor','ups.a0','ups.a1','ups.a2','population','generations','crossover','mutation','genetic.objective','controller']
    for row in data:
        case=('main' if row['controller']=='threshold' else 'framework_underload') if row['day']=='20110303' else (row['case'] if row['controller']=='threshold' else 'framework_'+row['case'])
        baseline=settings(ROOT/'paper_alignment/results'/f"{case}_{row['method']}_{row['seed']}_settings.properties")
        actual=settings(R/'results'/f"{row['prefix']}_settings.properties")
        for key in keys:
            if actual[key]!=baseline[key]:raise RuntimeError(f'Legacy comparison parameter mismatch {row["prefix"]}: {key}')
    summary=[];paired=[]
    for controller in ['threshold','framework_underload']:
        for destination in ['legacy','cloudsim_min_power','ups_min_power']:
            for method in METHODS:
                a=[v for v in old if v['case']==('main' if controller=='threshold' else 'framework_underload') and v['method']==method and v['seed'] in SEEDS] if destination=='legacy' else [v for v in data if v['day']=='20110303' and v['controller']==controller and v['destination']==destination and v['method']==method]
                if len(a)!=5 or {v['seed'] for v in a}!=set(SEEDS):raise AssertionError('Paired five-seed baseline missing')
                e=np.array([float(v['total_kwh']) for v in a]);short=np.array([100*(1-float(v['delivered_mi'])/float(v['requested_mi'])) for v in a])
                summary.append({'controller':controller,'destination':destination,'method':method,'n':5,'mean_kwh':float(e.mean()),'sd_kwh':float(e.std(ddof=1)),
                                'shortage_pct':float(short.mean()),'migrations':float(np.mean([int(v['started']) for v in a])),
                                'kwh_per_billion_mi':float(np.mean([float(v['total_kwh'])*1e9/float(v['delivered_mi']) for v in a]))})
            selected=old if destination=='legacy' else data
            get=lambda m:{v['seed']:float(v['total_kwh']) for v in selected if v['method']==m and v['seed'] in SEEDS and (v['case']==('main' if controller=='threshold' else 'framework_underload') if destination=='legacy' else v['day']=='20110303' and v['controller']==controller and v['destination']==destination)}
            ga,gga=get('GA'),get('GGA');d=np.array([ga[k]-gga[k] for k in SEEDS]);half=2.776*d.std(ddof=1)/np.sqrt(5)
            paired.append({'controller':controller,'destination':destination,'ga_minus_gga_kwh':float(d.mean()),'ci95_low':float(d.mean()-half),'ci95_high':float(d.mean()+half)})
    def entry(c,d,m):return next(v for v in summary if (v['controller'],v['destination'],v['method'])==(c,d,m))
    for field,name,label in [('mean_kwh','energy','24小时能耗 / kWh'),('shortage_pct','service','CPU需求未满足 / %')]:
        fig,axs=plt.subplots(1,2,figsize=(12,4));x=np.arange(5)
        for ax,c,title in zip(axs,['threshold','framework_underload'],['仅过载随机一VM','加入框架轻载重建']):
            for j,(d,l) in enumerate([('legacy','既有目的重建'),('cloudsim_min_power','原生服务器增量'),('ups_min_power','UPS增量扩展')]):
                ax.bar(x+(j-1)*.25,[entry(c,d,m)[field] for m in METHODS],.25,label=l,
                       yerr=[entry(c,d,m)['sd_kwh'] for m in METHODS] if field=='mean_kwh' else None,capsize=2)
            ax.set_xticks(x,METHODS);ax.set_title(title);ax.set_ylabel(label);ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8)
        fig.tight_layout();fig.savefig(R/f'figures/{name}.png',bbox_inches='tight');plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(12,3.8))
    for ax,c,title in zip(axs,['threshold','framework_underload'],['BFD-GA：仅过载','BFD-GA：框架轻载重建']):
        for d,l in [('legacy','既有目的重建'),('cloudsim_min_power','原生服务器增量'),('ups_min_power','UPS增量扩展')]:
            if d=='legacy':prefix=ROOT/'paper_alignment/results'/f"{'main' if c=='threshold' else 'framework_underload'}_BFD-GA_101"
            else:prefix=R/'results'/f'{c}_{d}_BFD-GA_20110303_101'
            ax.plot(np.arange(288)/12,bins(prefix),label=l,lw=.8)
        ax.set_title(title);ax.set_xlabel('时间 / h');ax.set_ylabel('300秒区间平均总功率 / W');ax.grid(alpha=.2);ax.legend(fontsize=8)
    lo=min(ax.get_ylim()[0] for ax in axs);hi=max(ax.get_ylim()[1] for ax in axs)
    for ax in axs:ax.set_ylim(lo,hi)
    fig.tight_layout();fig.savefig(R/'figures/dynamic.png',bbox_inches='tight');plt.close(fig)
    source=json.loads((ROOT/'correction/comparison/summary.json').read_text(encoding='utf-8'));comparison=[]
    for v in summary:
        ref=next(x for x in source['energy_comparison'] if x['method']==v['method']);e=v['mean_kwh']
        comparison.append({**v,'image_error_pct':100*(e/ref['reference_image_estimated_kwh']-1),'body_error_pct':100*(e/ref['thesis_text_kwh']-1)})
    for name,table in [('summary',summary),('reference_comparison',comparison),('paired_ga_gga',paired)]:
        with (R/'report'/f'{name}.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=table[0]);w.writeheader();w.writerows(table)
    (R/'report/summary.json').write_text(json.dumps({'statistics':summary,'reference_comparison':comparison,'paired_ga_gga':paired,'audit':{k:v for k,v in audit.items() if k!='checks'}},ensure_ascii=False,indent=2),encoding='utf-8')
    literature=[['叶桂森等，2022','A mission-driven two-step virtual machine commitment for energy saving of modern data centers through UPS and server coordinated optimizations','[Applied Energy 322,119467](https://doi.org/10.1016/j.apenergy.2022.119467)','两步BFD→机架GA最直接对应；公开预览说明CloudSim4.0，全文此次未取得'],
                ['叶桂森等，2022','Power Supply Cloudsim: An Extension of CloudSim for Modeling and Simulation of Power Supply Devices in Cloud Data Centers','[IEEE I&CPS Asia](https://ieeexplore.ieee.org/document/9949768/)；DOI 10.1109/ICPSAsia55496.2022.9949768','供电模型库扩展直接对应；此次未定位公开代码仓库'],
                ['Beloglazov与Buyya，2012','CCPE：动态VM整合与PABFD','[作者公开全文](https://beloglazov.info/papers/2012-optimal-algorithms-ccpe.pdf)；DOI 10.1002/cpe.1867','6.3节、Algorithm2给目的选择；Algorithm1给整合流程，可公开取得']]
    text=['# 公开在线迁移算法：检索、公式、接入与对照','检索及实验日期：2026-10-12。新结果独立保存在public_migration；原18页报告与540/1400结果保留。',
          '## 找到了什么，尚未确认什么','[济南大学官方教师资料](https://cse.ujn.edu.cn/info/1582/21481.htm)确认该叶桂森于2017/09～2023/07在山东大学读电气工程博士。以下是与本章最相关的公开论文，不是完整著作目录。',markdown_table(['作者/年份','论文','来源','相关性/访问范围'],literature),
          '此次用姓名、两篇题名、PowerSupplyAwareDataCenter/PowerEfficiencyAwareVMAllocationPolicy类名及GitHub相关关键词检索，未定位作者在线目的源码或附件。OpenAlex元数据记录两步论文非OA，出版商全文未获取；不能由此断言全文一定没有目的规则。此前“作者没有公开算法”的说法应收窄为“现有材料尚未定位作者所用规则”。不要求联系作者。',
          '## CloudSim本身提供完整的目的节点选择','官方[MigrationAbstract 3.0.3](https://raw.githubusercontent.com/Cloudslab/cloudsim/cloudsim-3.0.3/modules/cloudsim/src/main/java/org/cloudbus/cloudsim/power/PowerVmAllocationPolicyMigrationAbstract.java)的findHostForVm/getNewVmPlacement已有明确实现；[4.0源码](https://raw.githubusercontent.com/Cloudslab/cloudsim/cloudsim-4.0/modules/cloudsim/src/main/java/org/cloudbus/cloudsim/power/PowerVmAllocationPolicyMigrationAbstract.java)同样提供。它选择可行目标中增量服务器功率最小者，不感知UPS。',
          r'$$h^*(v)=\arg\min_{h\in\mathcal F(v)}\left[P_h(u_h+d_v)-P_h(u_h)\right]$$',
          'u_h为实际分配CPU，d_v为VM请求MIPS/Host MIPS；可行集合检查CPU、RAM、BW、存储并排除源/忙/过载端点。原生THR用请求CPU判断迁入后过载；对CPU为0的目标有跳过过载检查的例外，适配保留该行为并检查物理容量。原生候选逐个比较，严格小于时替换最优。',
          'THR检测过载、RS选择迁出VM、PABFD选择目的节点，三者不是一个“随机目标算法”。原生完整整合会重复选择VM直到过载解除，也可撤离多个轻载源；论文文字只明确过载随机选一个VM。因此THR-RS/PABFD是高度相关的框架候选，但没有证据确认作者原样使用整个控制器。',
          '[原论文PABFD伪代码所在页](../evidence/Beloglazov_algorithm_page_18.png)和[完整公开论文](../evidence/Beloglazov_Buyya_2012_CCPE.pdf)已保存，官方源码/DOI元数据/URL与SHA256见[证据目录](../evidence/manifest.json)。',
          '## 版本与当前接入范围','两步期刊论文预览写CloudSim4.0；当前实验用3.0.3。逐方法比较表明findHostForVm、预估功率及过载选VM循环去空白后相同，轻载函数只有日志写法不同。这支持目的核心在当前版本兼容；不证明完整4.0平台已复现。',
          f'[PublicMigrationDestination.java](../../../src/repro/PublicMigrationDestination.java)继承原生StaticThreshold，实际调用父类findHostForVm；在隔离资源快照上运行，阈值与资源预检用无副作用计算，避免原生临时vmCreate改变真实VM归属。实际原生核心调用{audit["native_finder_calls"]}次。完整THR-RS控制器未直接替换，仍保留论文每次随机一VM、种子控制和既有迁移事件/成本。',
          '新开关migration.destination为legacy、cloudsim_min_power或ups_min_power。前者保留已有重建；中者是原生目的核心的资源快照适配；后者是明确的自定义UPS扩展，不能冒称叶桂森原算法。新方案在五种初始放置后统一目的规则，评价的是初始放置及同一在线策略的组合；原有legacy各方法在线规则不同，不能只把差异解释成替换一个权重。',
          r'UPS扩展：$$h^*(v)=\arg\min_{h\in\mathcal F(v)}[P_{\rm total}(M_{v\to h})-P_{\rm total}(M)],\quad P_{\rm total}=\sum_iP_i+\sum_rL_r(\sum_{i\in r}P_i).$$',
          '该扩展同步考虑迁出源与迁入目标、启用状态和每机架UPS损耗。评分是稳态功率增量；迁移持续时间、源性能下降和目标复制CPU进入实际仿真积分，但没有在目的评分中另造脏页/交换机能量。',
          '```mermaid\nflowchart TD\n A[读取当前CPU与资源] --> B{CPU超过90%}\n B -->|是| C[每源随机选一个VM]\n C --> D[按请求CPU排序待迁VM]\n D --> E[排除源/过载/忙端点]\n E --> F[原生最小服务器增量 或 UPS总功率增量]\n F --> G{目标资源可行}\n G -->|是| H[预约端点并执行有时长迁移]\n G -->|否| I[保留原位置并记录未迁移]\n H --> J[实际Host与UPS功率/服务量积分]\n B -->|轻载开关开启| K[最轻载源全部VM可撤离才生成串行计划]\n K --> F\n I --> J\n```',
          '## 已执行对照与结果','140个24h实验完成：20110303每组合5种子共100运行；20110306/09每组合种子101各20运行。100VM×288原始采样、五初始算法、100Host/5机架、UPS参数与迁移成本固定。140运行独立段积分/UPS代数/事件/实际工作量通过；其中20有逐Host/VM详细核验。',
          '下表均为首日5个相同种子均值；旧legacy也只取同样5种子，不混入30种子均值。能耗图误差条为种子标准差。',
          markdown_table(['控制','目的','初始算法','kWh','未满足CPU%','平均迁移','kWh/十亿MI'],[[v['controller'],v['destination'],v['method'],f"{v['mean_kwh']:.3f}",f"{v['shortage_pct']:.3f}",f"{v['migrations']:.1f}",f"{v['kwh_per_billion_mi']:.3f}"] for v in summary]),
          '![能耗及种子标准差](../figures/energy.png)','![实际服务量代价](../figures/service.png)','![BFD-GA种子101实际动态曲线](../figures/dynamic.png)',
          '## 原图与正文分别核对','两种新目的策略的框架轻载情景如下；全部控制情景的双来源偏差在reference_comparison.csv。原图估读存在读图误差；正文其他方法由原文节能率反推，不选择较接近的列替代另一列。',
          markdown_table(['目的','算法','能耗kWh','原图偏差%','正文偏差%'],[[v['destination'],v['method'],f"{v['mean_kwh']:.3f}",f"{v['image_error_pct']:+.2f}",f"{v['body_error_pct']:+.2f}"] for v in comparison if v['controller']=='framework_underload' and v['destination']!='legacy']),
          '## 可以得出的结论与限制','原生目的算法已找到并实际接入，可以作为公开有依据的在线基线；UPS模式作为研究扩展对照。接入公开算法不等于确认作者用法，也不保证恢复原文所有排名。轻载开关、作者硬件/资源、原始轨迹与图文矛盾仍是影响因素。',
          '同构线性服务器下，已开启可行目标的增量功率常为相同常数(Pmax-Pidle)·d_v，原生严格浮点比较与遍历顺序会影响并列选择；它不保护第一步BFD分组，也不维护最初的UPS机架分布。因此动态运行可减弱初始放置差异，不能把一条原生目标规则强加给五种算法后要求原文排序必然重现。',
          '三日BFD-GA单种子明细和全部140运行在results/summary.csv；后两日不能作为五种子统计。五种子不足以据微小差值判定稳定GA/GGA排名，配对区间见paired_ga_gga.csv。实际服务量已计入，但缺少同SLA、脏页/网络设备等参数，不宣称完整硬件迁移成本。',
          '## 复跑','在复现结果目录执行：\n```powershell\npowershell -ExecutionPolicy Bypass -File .\\run_public_migration.ps1\n# 只核验已有140运行并重生成报告/图\npowershell -ExecutionPolicy Bypass -File .\\run_public_migration.ps1 -VerifyOnly\n```','新入口自动选择两种目标/两个控制情景并写独立目录，不修改旧主配置。全部阶段审计及源/结果哈希在audit。']
    (R/'report/公开在线迁移算法检索与接入报告.md').write_text('\n\n'.join(text),encoding='utf-8')
    print('PASS public-destination evidence report, paired CSV and three scientific plots')
if __name__=='__main__':main()
