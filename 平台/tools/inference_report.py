"""Auditable inference, independent algebra and controlled reconstruction contrasts."""
from pathlib import Path
from collections import defaultdict
import csv, json, hashlib, math, sys, argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from paper_audit import audit, rows, close, settings

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'paper_alignment/inference'; D=R/'results'
METHODS=['FFD','BFD','GA','GGA','BFD-GA']
VARIANTS=['total_original','total_common','server_original','server_common']
COLORS=['#386b9d','#d78b29','#8555a4','#26856b','#c7433e']
plt.rcParams.update({'font.family':['Microsoft YaHei','SimHei'],'axes.unicode_minus':False,'font.size':10})

def dump(name,data):
    (R/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def write_csv(name,data):
    with (R/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)

def power_bound(it,s):
    installed=float(s['ups.usable.w'])*float(s['ups.factor']); racks=int(s['racks'])
    return (1+float(s['ups.a1']))*it+float(s['ups.a0'])*it*it/(racks*installed)+racks*float(s['ups.a2'])*installed

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description='Independent audits and explicit unmeasured cost parameters; no fitted coefficients.')
    parser.add_argument('--extra-migration-joule',type=float,default=0,help='Additional uncounted hardware joules per completed migration')
    parser.add_argument('--service-penalty-kwh-per-billion-mi',type=float,default=0,help='Unserved-work penalty divided by electricity price, in kWh-equivalent per billion MI')
    args=parser.parse_args();q=args.extra_migration_joule;rho=args.service_penalty_kwh_per_billion_mi
    if not all(math.isfinite(t) and t>=0 for t in [q,rho]):parser.error('Cost parameters must be finite and nonnegative')
    s=settings(ROOT/'paper_alignment/config/main.properties')
    manifest=json.loads((ROOT/'paper_alignment/public_migration/audit/final_manifest.json').read_text(encoding='utf-8'))
    # The only historical file authorized for an appended current audit is the comparison document.
    mutable='correction/论文平台扩展与仿真思路核对.md'
    for name,digest in manifest.items():
        name=name.replace('\\','/')
        if name!=mutable and hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise AssertionError('Historical artifact changed: '+name)
    dynamic=list(rows(D/'dynamic_summary.csv'))
    expected={(v,m,str(101*k)) for v in VARIANTS for m in METHODS for k in range(1,6)}
    if len(dynamic)!=100 or {(x['variant'],x['method'],x['seed']) for x in dynamic}!=expected:
        raise AssertionError('Incomplete/duplicate dynamic matrix')
    checks=[audit(D/x['prefix'],x) for x in dynamic]
    old=list(rows(ROOT/'paper_alignment/public_migration/results/summary.csv'))
    for x in dynamic:
        if x['variant']=='total_original':
            prior=next(z for z in old if z['day']=='20110303' and z['controller']=='framework_underload'
                       and z['destination']=='cloudsim_min_power' and z['method']==x['method'] and z['seed']==x['seed'])
            for key in ['total_kwh','requested_mi','delivered_mi','started','migration_seconds']:
                close(float(x[key]),float(prior[key]),.000001)
        actual=settings(D/(x['prefix']+'_settings.properties'))
        if actual['controller']!='framework_underload' or actual['migration.destination']!='cloudsim_min_power':
            raise AssertionError('Confounded online controller')
        if int(x['native_calls'])<=0:raise AssertionError('Native finder was not called')
    bench=list(rows(D/'benchmark.csv')); history=list(rows(D/'histories.csv'))
    key=lambda x:tuple(x[k] for k in ['variant','n','method','seed'])
    cases={key(x):x for x in bench}; hg=defaultdict(list);pg=defaultdict(list)
    expected_bench={(v,str(n),m,str(101*k)) for v in VARIANTS for n in [5,10,12,30,40,80,150,230,288]
                    for m in ['GA','GGA','BFD-GA'] for k in range(1,6)}
    if len(bench)!=540 or set(cases)!=expected_bench or len(history)!=540*61:raise AssertionError('Incomplete benchmarks')
    for x in history:hg[key(x)].append(x)
    for x in rows(D/'benchmark_placements.csv'):pg[key(x)].append(x)
    for k,x in cases.items():
        h=sorted(hg[k],key=lambda z:int(z['generation']));p=sorted(pg[k],key=lambda z:int(z['vm']))
        if [int(z['generation']) for z in h]!=list(range(61)) or [int(z['vm']) for z in p]!=list(range(int(x['n']))):
            raise AssertionError('Missing history generation / VM')
        values=np.array([float(z['objective_w']) for z in h])
        if not np.isfinite(values).all() or np.any(np.diff(values)>1e-7):raise AssertionError('Invalid elitist history')
        u=np.zeros(100);count=np.zeros(100,dtype=int)
        for z in p:
            demand=float(z['demand']);host=int(z['host'])
            if not 0<=host<100 or not 0<=demand<=1:raise AssertionError('Invalid packing')
            u[host]+=demand;count[host]+=1
        if np.max(u)>1+1e-8 or np.max(count)>128:raise AssertionError('Infeasible packing')
        watts=np.where(count>0,float(s['host.idle.w'])+(float(s['host.max.w'])-float(s['host.idle.w']))*u,0)
        outputs=watts.reshape(5,20).sum(axis=1);installed=7000*1.25
        if np.max(outputs)>7000+1e-7:raise AssertionError('UPS output capacity')
        loss=np.sum(.0549*outputs**2/installed+.0077*outputs+.0207*installed)
        close(float(x['server_w']),float(watts.sum()));close(float(x['ups_w']),float(loss))
        close(float(x['total_w']),float(watts.sum()+loss));close(values[-1],float(x['objective_w']))
        close(values[-1],float(x['total_w'] if k[2]=='BFD-GA' or k[0].startswith('total') else x['server_w']))
        if int(x['hosts'])!=np.count_nonzero(count):raise AssertionError('Awake count')
    summaries=[]; paired=[]; added=[]
    for v in VARIANTS:
        by={m:{int(z['seed']):z for z in dynamic if z['variant']==v and z['method']==m} for m in METHODS}
        for m in METHODS:
            a=list(by[m].values()); energies=np.array([float(z['total_kwh']) for z in a])
            summaries.append({'variant':v,'method':m,'n':5,'mean_kwh':float(energies.mean()),'sd_kwh':float(energies.std(ddof=1)),
                              'shortage_pct':float(np.mean([100*(1-float(z['delivered_mi'])/float(z['requested_mi'])) for z in a])),
                              'mean_migrations':float(np.mean([int(z['started']) for z in a])),
                              'kwh_per_billion_mi':float(np.mean([float(z['total_kwh'])/float(z['delivered_mi'])*1e9 for z in a]))})
        for a,b in [('GGA','GA'),('BFD','FFD'),('BFD-GA','BFD')]:
            delta=np.array([float(by[a][seed]['total_kwh'])-float(by[b][seed]['total_kwh']) for seed in sorted(by[a])])
            margin=2.776445105*delta.std(ddof=1)/math.sqrt(5)
            paired.append({'variant':v,'comparison':a+' - '+b,'mean_kwh':float(delta.mean()),'ci95_low':float(delta.mean()-margin),'ci95_high':float(delta.mean()+margin),
                           'interpretation':'Paired t interval across five algorithm seeds on one fixed day; not workload-wide proof'})
        for m in METHODS[:-1]:
            a=next(z for z in summaries if z['variant']==v and z['method']=='BFD-GA');b=next(z for z in summaries if z['variant']==v and z['method']==m)
            delta=b['mean_kwh']-a['mean_kwh'];dn=a['mean_migrations']-b['mean_migrations']
            added.append({'variant':v,'baseline':m,'benefit_kwh':delta,'extra_migrations':dn,
                          'extra_joule_per_migration_at_tie':delta*3600000/dn if dn else None,
                          'meaning':'E_corrected_kWh=E_simulated_kWh+q_joule*N/3600000; q>=0 excludes already counted CPU energy'})
    generalized=[]
    for x in dynamic:
        missing=float(x['requested_mi'])-float(x['delivered_mi']);extra=q*int(x['finished'])/3600000
        penalty=rho*missing/1e9
        if not math.isfinite(float(x['total_kwh'])+extra+penalty):raise ValueError('Cost parameters overflow; choose a finite hardware/service cost scale')
        generalized.append({'prefix':x['prefix'],'variant':x['variant'],'method':x['method'],'seed':x['seed'],
                            'simulated_energy_kwh':float(x['total_kwh']),'extra_hardware_kwh':extra,'service_penalty_kwh_equivalent':penalty,
                            'generalized_cost_kwh_equivalent':float(x['total_kwh'])+extra+penalty,
                            'q_joule_per_migration':q,'rho_kwh_equivalent_per_billion_mi':rho})
    raw=np.loadtxt(ROOT/'correction/inputs/cohort25_20110303.csv',delimiter=',');types=np.resize([1,.8,.4,.2],100)
    alpha=float((raw*types[:,None]).mean()/raw.mean());bounds=[]
    for target in [184.98,154.5358]:
        installed=8750;A=.0549/(5*installed);B=1+.0077;C=5*.0207*installed;P=target*1000/24
        it=2*(P-C)/(B+math.sqrt(B*B+4*A*(P-C)))
        close(power_bound(it,s),P,1e-6)
        bounds.append({'target_kwh':target,'it_upper_w':it,'alpha_necessary_upper_full_service':it/8750})
    # Independence of linear terms: excess rack loss is precisely a0/S times sum squared deviations.
    rng=np.random.default_rng(77)
    for _ in range(100):
        p=rng.uniform(0,7000,5);L=np.sum(.0549*p*p/8750+.0077*p+.0207*8750)
        close(L-(power_bound(p.sum(),s)-p.sum()),.0549/8750*np.sum((p-p.mean())**2),1e-7)
    static=list(rows(ROOT/'paper_alignment/results/static_summary.csv'));cost=[]
    weights={str(k/100):w for k,w in zip(range(10,71,10),[.01,.22,.38,.26,.10,.02,.01])}
    for family in ['physical_host_load','vm_average_cpu']:
        for arch in ['N+1 AC','2N AC','N+1 DC','2N DC']:
            arch_key=arch.replace(' ','');power={}
            for m in METHODS:
                power[m]=sum(w*np.mean([float(z['total_w']) for z in static if z['family']==family and z['architecture']==arch_key and z['method']==m
                                       and abs(float(z['target'])-float(level))<1e-8]) for level,w in weights.items())
            for m in METHODS[:-1]:
                delta=power[m]-power['BFD-GA']
                cost.append({'family':family,'architecture':arch_key,'baseline':m,'weighted_delta_w':float(delta),
                             'saving_pct':float(100*delta/power[m]),'annual_saved_kwh_per_dc':float(8.76*delta),
                             'annual_dollar_formula':'annual_saved_kwh_per_dc * price_USD_per_kWh * equivalent_DC_count'})
    if any(not math.isfinite(z['saving_pct']) for z in cost):raise AssertionError('Static cost coverage incomplete')
    write_csv('动态对照汇总.csv',summaries);write_csv('配对差异与区间.csv',paired);write_csv('迁移额外硬件开销反转阈值.csv',added);write_csv('静态负载分布加权电费.csv',cost)
    write_csv('参数化迁移与服务广义成本.csv',generalized)
    reference=json.loads((ROOT/'correction/comparison/summary.json').read_text(encoding='utf-8'))['energy_comparison']
    comparisons=[]
    for x in summaries:
        ref=next(z for z in reference if z['method']==x['method'])
        comparisons.append(dict(variant=x['variant'],method=x['method'],image_error_pct=100*(x['mean_kwh']/ref['reference_image_estimated_kwh']-1),
                                body_error_pct=100*(x['mean_kwh']/ref['thesis_text_kwh']-1)))
    write_csv('原图与正文双基准偏差.csv',comparisons)
    dump('audit/independent_checks.json',{'status':'PASS','dynamic':100,'benchmarks':540,'histories':32940,'historical_compatibility':25,
                                        'checks':checks,'analytic_bounds':bounds,'alpha':alpha,'q_joule_per_migration':q,'rho_kwh_equivalent_per_billion_mi':rho})
    fig,axes=plt.subplots(1,2,figsize=(13,4.5))
    for j,m in enumerate(METHODS):
        selected=[z for z in summaries if z['method']==m];x=np.arange(4)+.14*(j-2)
        axes[0].errorbar(x,[z['mean_kwh'] for z in selected],yerr=[z['sd_kwh'] for z in selected],fmt='o',capsize=3,color=COLORS[j],label=m)
        axes[1].plot(x,[z['kwh_per_billion_mi'] for z in selected],'o',color=COLORS[j])
    for ax in axes:ax.set_xticks(range(4));ax.set_xticklabels(VARIANTS,rotation=15);ax.grid(axis='y',alpha=.2)
    axes[0].set_ylabel('24小时能耗 / kWh（均值 ± 种子标准差）');axes[1].set_ylabel('kWh / 实际完成十亿MI');axes[0].legend(ncol=3,fontsize=9,loc='upper center',bbox_to_anchor=(.5,1.16))
    fig.tight_layout();fig.savefig(R/'动态能耗与服务量.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(13,7))
    for row,v in enumerate(VARIANTS[:2]):
        for col,n in enumerate([40,150,288]):
            sample=pg[next(k for k in pg if k[1]==str(n))]; demand=sum(float(z['demand']) for z in sample)
            it=math.ceil(demand-1e-10)*218.3+131.7*demand;lb=power_bound(it,s)
            ax=axes[row,col]
            for m in ['GA','GGA','BFD-GA']:
                trajectories=np.array([[float(z['objective_w']) for z in sorted(hg[(v,str(n),m,str(seed))],key=lambda t:int(t['generation']))]
                                       for seed in [101,202,303,404,505]])
                ax.plot(range(61),100*(trajectories.mean(axis=0)/lb-1),label=m)
            ax.set_title(f'{v}, {n} VM');ax.set_xlabel('迭代次数（0为初始种群）');ax.set_ylabel('距解析下界 / %');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.tight_layout();fig.savefig(R/'逐代求解轨迹与解析下界.png',dpi=180);plt.close(fig)
    lines=['# 重建假设推导、修正与可识别边界','',
           '完成时间：2026-10-13。新增100组动态对照、540组求解基准、32940个逐代记录；独立审计PASS。15项默认历史解/轨迹逐位回归及24项种群规模检查通过，25组动态基线与之前公开目的节点结果一致。旧结果与旧核心源码保持不变。','',
           '## 1. 可以解决什么，仍不能证明什么','',
           '已经修正可配置种群数组错误，建立初始化/目标函数对照，推导UPS第二步目标及负载容量必要约束，明确在线控制状态与额外迁移硬件成本的计算接口，并纠正图2-26的对照含义。不能从公开论文唯一恢复作者的随机种子、修复算子、GGA细节、停止准则、轻载控制和迁移硬件参数。结果接近不是作者实现同一性的证明。','',
           '## 2. 数学约束与正确第二步目标','',
           r'令服务器利用率总和为D，开启服务器数为K，则P_IT=218.3K+131.7D。N+1 DC当前参数S=7000×1.25=8750 W，单UPS损耗L(p)=0.0549p²/S+0.0077p+0.0207S。',
           r'五台UPS保持通电、K和D固定时，总损耗的可变部分仅为Σp_r²；Σp_r²=P_IT²/5+Σ(p_r-P_IT/5)²。因此第二步是在机架容量限制下减小输出功率不均衡，既不能拆开第一步VM组，也不能将“避免轻载UPS”误写成任意关机。100组独立代数恒等式检查通过。',
           'BFD是启发式装箱，并不保证所有输入下全局最少服务器；FFD和BFD在许多负载上会产生相同组，不能人为增加差异。已有七VM反例确认实现分别使用3台、2台。GA/GGA允许改变VM分组，理论上可在某些负载上比固定BFD分组更省电，故不存在BFD-GA对所有数据都最优的定理。','',
           '## 3. 25%利用率与缺失容量比例','',
           '100 VM平均CPU25%且VM=Host容量、全部需求被服务时，D平均=25；K≥D，P_IT≥350D，IT一天至少210 kWh。按当前五台UPS常通电模型计入损耗，必要下界进一步提高。',
           f'当前原始公开数据的容量加权有效比例α={alpha:.6f}；不是作者参数。若用平均负载不加权的25%代替物理主机需求，会改变装箱数量和全部功耗。',
           f'利用Jensen下界，若服务完整且采用当前UPS参数，正文184.98 kWh要求α≤{bounds[0]["alpha_necessary_upper_full_service"]:.6f}；原图估计154.5358 kWh要求α≤{bounds[1]["alpha_necessary_upper_full_service"]:.6f}。这些只是必要条件，不能据此拟合一个作者α。存在服务损失时必须用实际完成MI修正，不能直接套用满服务界。','',
           '## 4. 实现细节与排名对照','',
           '新增EvidencePlacement是版本化修正版：评价数组按实际种群长度分配，支持20/30/40/60；保留原求解器用于历史哈希和默认40逐位回归。common仅为所有遗传方法加入同一个BFD初始个体，未挑选更有利种子。total以服务器+UPS为GA/GGA目标；server以传统服务器目标为GA/GGA目标；BFD-GA始终优化供电总目标。所有动态实验使用相同公开原生目的节点和同一轻载重建控制器，五个固定种子101至505。','',
           '| 设置 | FFD | BFD | GA | GGA | BFD-GA |','|---|---:|---:|---:|---:|---:|']
    for v in VARIANTS:lines.append('|'+v+'|'+'|'.join(f'{next(z for z in summaries if z["variant"]==v and z["method"]==m)["mean_kwh"]:.3f}' for m in METHODS)+'|')
    lines+=['','单位kWh。改变目标函数/初始个体能够改变GA与GGA顺序，仍不能恢复正文完整顺序BFD-GA<BFD<FFD<GGA<GA。不能从这四组中只选更接近的设置来宣称排序问题已解决；五种子区间只衡量同一天算法随机性，不能代表全部PlanetLab负载。现有1400组静态结果也必须保留负节约值。','',
            '## 5. 在线控制规则与迁移开销','',
            '论文可直接确认的是CPU>90%时随机选择一个VM。当前按300秒样本评估每个非繁忙过载源，每源最多选择一个VM；目的节点调用CloudSim公开findHostForVm，先检查CPU/RAM/BW/storage及繁忙端点，再按最小服务器增量功率选择。选择VM、选目的节点、执行迁移是三个独立层次。','论文不能唯一确认轻载主机是否整机疏散、一次处理多少源、是否反复选择到脱离过载、请求CPU或实际分配CPU判定、并发和排队。当前framework_underload只整合一个可完全疏散的轻载源；它不是原生完整控制器。literal threshold作为论文文字最小基线保留在之前的540/140组结果中，不能与轻载扩展混为同一实验。','当前已计迁移持续时间、源CPU服务损失、目的复制CPU、繁忙端点、实际Cloudlet完成MI与供电积分。源CPU和目的CPU功耗已在仿真中，不可再次添加同一CPU代价。脏页迭代和网络/内存硬件额外功耗没有测量证据，不能称硬件全成本已还原。',
            r'可执行的完整参数接口：E_corrected=E_simulated+q×N/3.6e6（kWh）；q为每次迁移未计入的额外硬件焦耳，q≥0。比较两方法时q_tie=3.6e6(E_base-E_proposed)/(N_proposed-N_base)。正阈值才是非负成本可能导致的反转点；负值不是可接受硬件参数；分母为0则额外等额成本不改变能耗差。结果见CSV，不把q设为拟合值。按实际完成MI的单位服务能耗一并报告；这是服务诊断而非严格等服务重跑或完整SLA成本。','',
            f'参数接口已实现：Python脚本支持 --extra-migration-joule q 与 --service-penalty-kwh-per-billion-mi rho。当前q={q:g} J/次、rho={rho:g} kWh等价/十亿MI；默认0表示未测量项不强填。广义成本=实际能耗+qN/3.6e6+rho×未服务MI/1e9。rho是未服务惩罚除以电价后的价值尺度，不是额外物理耗电。完整参数化逐次结果见“参数化迁移与服务广义成本.csv”，硬件物理全成本仍依赖测量。','',
            '## 6. 电费与图2-25','',
            '论文2.6.4估计的是全美国行业每年成本，不是100台服务器机房直接节省亿美元。正文示例N+1 AC相对BFD/GGA为1.38/1.31亿美元；N+1 DC为1.62/1.57亿美元。仅凭本机房功耗无法唯一还原全行业规模与电价、IT/UPS能耗占比。',
            r'按表2-1权重(1%,22%,38%,26%,10%,2%,1%)和10%–70%静态负载，ΔE_year=8760Σw_l(P_base,l-P_proposed,l)/1000；ΔC=价格×等效机房数×ΔE_year。正的共同换算系数不会改变成本优势的符号或排序；缺乏电力基数时不应制造美元柱高。输出两种负载解释、四种架构、全部四种基准的32项年电量与相对节约；负值照报。','',
            '## 7. 图2-26与收敛','',
            '论文图2-26是迭代预算与可求解VM规模，不是功耗收敛曲线。正文列3/6/12/28/48/59次，图轴列3/6/12/28/45/59次，存在48与45差异；论文未给“可求解”的精度/可行性/停止准则。旧复现的“距BFD-GA参考解1%以内”属于补充判据，并且单一方法参考会偏向BFD-GA，不能作为原图完整复现。',
            '新结果记录全部61代且不以单方法参考判断成功，采用公共解析下界：K≥ceil(D)，P_IT≥218.3ceil(D)+131.7D，再叠加UPS均衡下界。该界是松弛界而非已证明可达到的最优值。全部方法从第0代已有可行解，因此若把“可求解”只理解成可行装箱，传统GA也可以处理288VM，不能恢复原图仅5–10VM的结论。当前观察到两步法在这些静态案例上有更好的最终功率与搜索结构优势，但原图规模曲线仍无法唯一恢复。','',
            '## 8. 验收与复跑','',
            '原图与正文双基准偏差全部独立输出，不能只选更近的一项。趋势、排名稳定性、服务量、成本符号和逐代记录分别验收；用户10%–15%的数值容差仅用于可比指标，不证明作者未知细节已经还原。当前结论为：平台/公式/两步结构的可验证复现加公开在线策略重建；完整排名、行业绝对成本和图2-26的作者停机语义尚未解决，不宜宣称全章结果完整恢复。','',
            '复跑：在复现结果目录依次执行 build.ps1；Java8 -cp "bin;lib/*" repro.InferenceExperiments；捆绑Python tools/inference_report.py。文件覆盖仅限本分支新实验目录。','',
            '来源：论文PDF页41–46、58–61与表2-1；[CloudSim公开目的节点与原生完整控制源码](https://github.com/Cloudslab/cloudsim/blob/cloudsim-3.0.3/modules/cloudsim/src/main/java/org/cloudbus/cloudsim/power/PowerVmAllocationPolicyMigrationAbstract.java)；[Falkenauer 1996 GGA/HGGA原文](https://www.macs.hw.ac.uk/~dwcorne/Teaching/falkenauer96hybrid.pdf)。当前GGA算子是明确重建，不声称等于作者GGA或完整HGGA。']
    (R/'重建假设推导与修正报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    dump('audit/final_manifest.json',{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
         for p in list(R.rglob('*'))+[ROOT/'src/repro/EvidencePlacement.java',ROOT/'src/repro/InferenceExperiments.java',Path(__file__).resolve()]
         if p.is_file() and p.name!='final_manifest.json'})
    print('PASS 100 independent dynamic audits, 540 solver audits, 32940 histories, historical compatibility, 100 analytic identities, 32 cost cases')

if __name__=='__main__':main()
