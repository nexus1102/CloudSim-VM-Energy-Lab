"""Generate reports only from independently verified, archived simulations."""
import argparse,csv,json,re,statistics,sys
from pathlib import Path
from collections import defaultdict
from research_platform_audit import verify

METHODS=['FFD','BFD','GA','GGA','BFD-GA']
WEIGHTS={10:.01,20:.22,30:.38,40:.26,50:.10,60:.02,70:.01}
def mean(rows,key):return statistics.mean(float(r[key]) for r in rows)
def write_csv(path,rows):
    if not rows:return
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def generate(directory,force=False):
    run=Path(directory).resolve();audit=verify(run,force=force);out=run/'report'
    with (run/'summary.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    grouped=defaultdict(list)
    for row in rows:
        scenario=row['prefix'].rsplit('_'+row['method']+'_',1)[0]
        grouped[(row['kind'],scenario,row['method'])].append(row)
    aggregate=[]
    for (kind,scenario,method),rs in grouped.items():
        vals=[float(r['total_kwh']) for r in rs];requested=mean(rs,'requested_mi');delivered=mean(rs,'delivered_mi')
        aggregate.append(dict(kind=kind,scenario=scenario,method=method,n=len(rs),mean_kwh=statistics.mean(vals),
            sd_kwh=statistics.stdev(vals) if len(vals)>1 else 0,mean_migrations=mean(rs,'finished'),
            requested_mi=requested,delivered_mi=delivered,unserved_pct=100*(1-delivered/requested) if requested else 0,
            kwh_per_billion_mi=statistics.mean(vals)/(delivered/1e9) if delivered else '',ups_kwh=mean(rs,'ups_kwh')))
    write_csv(out/'aggregate.csv',aggregate)
    lines=['# 研究平台验证结果报告','',f'独立核验：**{audit["status"]}**；实际案例 {audit["cases"]} 组，求解轨迹 {audit["solver_trajectories"]} 条。',
        '', '核验覆盖真实CloudSim事件、VM归属与资源、实际交付工作量、服务器功率、UPS模块损耗和迁移端点功率反馈。PASS表示在声明的模型和参数下实现自洽，不证明作者未公开的实现已被唯一恢复。',
        '', '全部分组指标见 [aggregate.csv](aggregate.csv)。能耗同时报告服务缺口与每十亿MI实际交付工作量能耗；不能仅凭少服务时的低能耗判定算法更好。三种子标准差描述本次重复波动，不等同于跨日期泛化证据。','']
    dynamic=[a for a in aggregate if a['kind']=='dynamic']
    if dynamic:
        lines+=['## 动态实验','', '| 场景 | 算法 | kWh均值±标准差 | 迁移均值 | 未交付请求% | kWh/十亿MI |','|---|---|---:|---:|---:|---:|']
        for a in dynamic:
            lines.append(f'| {a["scenario"]} | {a["method"]} | {a["mean_kwh"]:.3f} ± {a["sd_kwh"]:.3f} | {a["mean_migrations"]:.1f} | {a["unserved_pct"]:.4f} | {a["kwh_per_billion_mi"]:.3f} |')
        baseline=[a for a in dynamic if a['scenario']=='n_plus_1_standby_cap0.9_consolidation']
        if baseline:
            root=Path(__file__).resolve().parents[1]
            references=json.loads((root/'correction/comparison/summary.json').read_text(encoding='utf-8'))['energy_comparison']
            refs={r['method']:r for r in references};comparison=[]
            lines+=['','## 图2-24与正文分别比较','','图像读数为既有数字化估计，原始读图不确定度也保留。默认轻载整合是工程补充控制规则；其接近正文的结果不能据此反证规则就是作者实现。',
                '', '| 方法 | 本次kWh | 正文kWh | 正文偏差% | 图像估计kWh | 图像偏差% |','|---|---:|---:|---:|---:|---:|']
            for a in baseline:
                r=refs[a['method']];e=a['mean_kwh'];body=r['thesis_text_kwh'];img=r['reference_image_estimated_kwh']
                comparison.append(dict(method=a['method'],mean_kwh=e,text_kwh=body,text_deviation_pct=100*(e/body-1),image_estimate_kwh=img,image_deviation_pct=100*(e/img-1),image_uncertainty_kwh=r['image_reading_uncertainty_kwh']))
                lines.append(f'| {a["method"]} | {e:.3f} | {body:.3f} | {100*(e/body-1):.2f} | {img:.3f} | {100*(e/img-1):.2f} |')
            write_csv(out/'paper_energy_comparison.csv',comparison)
            ranked=sorted(baseline,key=lambda a:a['mean_kwh'])
            rank_text=' < '.join(a['method'] for a in ranked)
            proposed_rank=next(i+1 for i,a in enumerate(ranked) if a['method']=='BFD-GA')
            lines+=['',f'本次三种子能耗均值从低到高为 {rank_text}；BFD-GA位列第{proposed_rank}。均值顺序不代表差异统计显著，也不自动证明原文排名恢复。正文与图像基准不能择优使用；15%容差应分别判定。']
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,ax=plt.subplots(figsize=(9,4.5))
        for offset,controller in [(-.18,'threshold'),(.18,'consolidation')]:
            selected={a['method']:a for a in dynamic if a['scenario']=='n_plus_1_standby_cap0.9_'+controller}
            if len(selected)==5:
                ax.bar([i+offset for i in range(5)],[selected[m]['mean_kwh'] for m in METHODS],width=.36,
                    yerr=[selected[m]['sd_kwh'] for m in METHODS],capsize=3,label=controller)
        ax.set_xticks(range(5),METHODS);ax.set_ylabel('24 h energy (kWh)');ax.legend();fig.tight_layout()
        fig.savefig(out/'dynamic_energy.png',dpi=180);plt.close(fig)
        lines+=['','![动态能耗及三种子标准差](dynamic_energy.png)','']
    static={}
    for a in aggregate:
        match=re.fullmatch(r'static_cap([\d.]+)_(N\+1AC|N\+1DC|2NAC|2NDC)_(\d+)',a['scenario'])
        if match:static[(match[1],match[2],int(match[3]),a['method'])]=a
    weighted=[]
    for cap,arch in sorted({(k[0],k[1]) for k in static}):
        for method in METHODS[:-1]:
            pairs=[(w,static[(cap,arch,level,method)],static[(cap,arch,level,'BFD-GA')]) for level,w in WEIGHTS.items()]
            rate=sum(w*(1-p['mean_kwh']/b['mean_kwh']) for w,b,p in pairs)
            base=sum(w*b['mean_kwh'] for w,b,p in pairs);prop=sum(w*p['mean_kwh'] for w,b,p in pairs)
            upsbase=sum(w*b['ups_kwh'] for w,b,p in pairs);upsprop=sum(w*p['ups_kwh'] for w,b,p in pairs)
            weighted.append(dict(cap=cap,architecture=arch,baseline=method,time_weighted_saving_pct=100*rate,
                energy_weighted_saving_pct=100*(1-prop/base),ups_only_energy_saving_pct=100*(1-upsprop/upsbase),
                conditional_annual_saved_kwh=(base-prop)*12*8760))
    if weighted:
        write_csv(out/'weighted_static.csv',weighted)
        lines+=['## 静态加权指标','', '按表2-1的七档时间占比，分别计算Σw·(1−P提出/P基准)、1−ΣwP提出/ΣwP基准及UPS单独分母指标，见 [weighted_static.csv](weighted_static.csv)。年度能耗仅为本100台服务器模型按全年占比持续运行的条件推算；静态窗口300秒，因此功率换算系数为12。负节省率保留，不调整数据恢复排名。',
            '', '论文年度货币成本所用产业规模、费率与分母未完整公开，不能以本平台能耗直接证明原文成本优势。27条固定代数求解轨迹也不能替代作者未公开停止条件的图2-26速度结论。','']
    lines+=['## 适用边界','', '默认0W备用损耗和0W附加迁移硬件功率是未测定项的下界假设；20W敏感性场景不代表实测参数。CPU复制开销已经进入服务器功率与UPS负载。当前未建模脏页迭代、停机暂停、网络交换机独立耗电、UPS切换瞬态和故障概率。',
        '', '字面UPS公式与图2-17矛盾保留为独立验证，不用拟合曲线替代公式结论。GGA算子、轻载控制及硬件档次均有明确重建假设。',
        '', '运行目录中的source_snapshot及provenance.csv记录实际生产源码、JAR和输入；当前源码后续变化不改变历史结果来源。verified_v2矩阵早于接口异常传播、串行队列和带宽守卫增强；两个verified单运行用于验证增强后的接口。']
    (out/'结果报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Report generated:',out/'结果报告.md')
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');parser=argparse.ArgumentParser();parser.add_argument('--run',required=True)
    parser.add_argument('--force',action='store_true');args=parser.parse_args()
    generate(args.run,force=args.force)
