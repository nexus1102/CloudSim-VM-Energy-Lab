"""Twelve native plots and side-by-side source comparisons; no outcome fitting."""
from pathlib import Path
import csv, json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
plt.rcParams.update({'font.family': 'Microsoft YaHei', 'font.size': 10, 'axes.unicode_minus': False,
                     'axes.spines.top': False, 'axes.spines.right': False, 'savefig.dpi': 180})
METHODS = ['FFD', 'BFD', 'GA', 'GGA', 'BFD-GA']
ARCH = ['N+1AC', 'N+1DC', '2NAC', '2NDC']
SEEDS = [101, 202, 303, 404, 505]
LOADS = np.arange(1, 8) / 10
WEIGHTS = np.array([.01, .22, .38, .26, .10, .02, .01])
COLORS = ['#315b9a', '#42a879', '#c96696', '#d9ae30', '#d75b36']
NOTES, METRICS = {}, []

def read(name):
    with (ROOT / 'results' / (name + '.csv')).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

static, dynamic, performance = read('static'), read('dynamic_summary'), read('performance')
assert len(static) == 700 and len(dynamic) == 25 and len(performance) == 540
assert all(float(r['cpu_error']) < 1e-8 and float(r['power_error_w']) < 1e-5 for r in static + dynamic)

def vals(arch, load, method, field):
    return np.array([float(r[field]) for r in static if r['architecture'] == arch
                     and abs(float(r['load']) - load) < 1e-6 and r['method'] == method])

def reductions(arch, field='total_w'):
    return np.array([100 * (vals(arch,l,'BFD',field).mean() - vals(arch,l,'BFD-GA',field).mean())
                     / vals(arch,l,'BFD',field).mean() for l in LOADS])

def decorate(ax, x='时间 / h', y='功率 / W'):
    ax.set_xlabel(x); ax.set_ylabel(y); ax.grid(axis='y', color='#dde2ea', alpha=.65)
    if x == '时间 / h': ax.set_xlim(0,24); ax.set_xticks(np.arange(0,25,4))

def save(fig, num, title, note):
    fig.suptitle(f'图 2-{num}  {title} | 复现实测', fontweight='bold', fontsize=14)
    fig.tight_layout(rect=[0, .035, 1, .94])
    path = ROOT / 'figures' / f'reproduced_2-{num}.png'
    fig.savefig(path); fig.savefig(path.with_suffix('.svg')); plt.close(fig)
    original = ROOT / 'evidence' / f'original_2-{num}.png'
    comp, axes = plt.subplots(1, 2, figsize=(16, 6.8))
    for ax, image_path, label in zip(axes, [original, path], ['论文原图', '公开替代输入的 CloudSim 复现']):
        ax.imshow(Image.open(image_path)); ax.axis('off'); ax.set_title(label, fontsize=14, pad=16)
    comp.suptitle(f'图 2-{num} 对照', fontsize=18, fontweight='bold')
    comp.text(.5, .035, '左：原文证据；右：独立仿真。图形相似或不相似均不等于数值验证通过。', ha='center', fontsize=11)
    comp.tight_layout(rect=[0, .07, 1, .94]); comp.savefig(ROOT / 'comparison' / f'comparison_2-{num}.png'); plt.close(comp)
    NOTES[str(num)] = {'title': title, 'note': note}

# Platform validation: actual host 6 = rack 2, server 2, as drawn in Figure 2-14.
vmrows, hostrows = read('validation_vm'), read('validation_hosts')
t = np.arange(288) / 12
fig, ax = plt.subplots(figsize=(10, 5))
vms = [14, 16, 17, 18, 19]
stack = np.array([[float(r['cpu']) for r in vmrows if int(r['vm_id']) == i] for i in vms])
actual = np.array([float(r['allocated_cpu']) for r in hostrows if int(r['host_id']) == 6])
ax.stackplot(t, stack, labels=[f'VM {i}' for i in vms], alpha=.75)
ax.plot(t, actual, 'k-', lw=1, label='CloudSim 实测 CPU'); ax.set_ylim(0, 1.1)
decorate(ax, y='CPU 占用率 / p.u.'); ax.legend(ncol=3, fontsize=9)
save(fig, 15, 'CPU 占用率验证', f'实测与5台VM之和最大误差 {np.max(abs(actual-stack.sum(axis=0))):.3g}。替代轨迹，不能计算与作者轨迹的逐点误差。')
fig, ax = plt.subplots(figsize=(10, 5))
server = np.array([[float(r['power_w']) for r in hostrows if int(r['host_id']) == h] for h in [5, 6, 7]])
ax.stackplot(t, server, labels=['Server 1', 'Server 2', 'Server 3'], alpha=.75)
ax.plot(t, server.sum(axis=0), 'k-', lw=1, label='UPS 输出（实测服务器之和）')
decorate(ax); ax.legend(ncol=2, fontsize=9)
save(fig, 16, '机架输出功率验证', 'UPS输出严格等于机架服务器功率之和。表2-5空载218 W，主实验218.3 W；本验证沿用218.3 W并记录0.3 W/服务器的差别。')
fig, ax = plt.subplots(figsize=(10, 5))
output = server.sum(axis=0)
theory = 2000 * (.0241*(output/2000)**2 + .0353*(output/2000) + .0617)
simulation = np.array([float(r['rack1_loss_w']) for r in read('validation_times')])
assert np.max(abs(simulation-theory)) < 1e-7
ax.plot(t, simulation, color='#387b56', lw=1, label='仿真模块损耗')
ax.scatter(t[::4], theory[::4], s=12, color='#cc6284', label='独立公式计算')
ax.axhspan(67, 73, color='#d45b39', alpha=.15, label='论文图约 67-73 W')
decorate(ax, y='UPS 损耗 / W'); ax.legend(ncol=2, fontsize=9)
save(fig, 17, 'UPS 损耗验证：按原表参数', f'原表与原图不相容：空载下限123.4 W；本次 {simulation.min():.2f}-{simulation.max():.2f} W。理论/模块一致，与论文绝对值未吻合。')

static_estimates=[]
original30={'N+1AC':(13180,12930,60),'N+1DC':(13050,12750,70),'2NAC':(14350,14230,60),'2NDC':(13780,13635,60)}
for num, arch in [(18,'N+1AC'), (19,'N+1DC'), (21,'2NAC'), (22,'2NDC')]:
    fig, ax = plt.subplots(figsize=(11, 5.7)); x = np.arange(7); width = .15
    hatches = ['xx', '..', '///', '\\\\', '']
    for k, method in enumerate(METHODS):
        s = np.array([vals(arch,l,method,'server_w').mean() for l in LOADS])
        u = np.array([vals(arch,l,method,'ups_loss_w').mean() for l in LOADS])
        sd = np.array([vals(arch,l,method,'total_w').std(ddof=1) for l in LOADS])
        positions = x + (k-2)*width
        ax.bar(positions, s, width, color='#65a7c9', edgecolor='#355c71', hatch=hatches[k], linewidth=.3)
        ax.bar(positions, u, width, bottom=s, color='#eaa953', edgecolor='#94713c', hatch=hatches[k], linewidth=.3,
               label=method, yerr=sd, error_kw={'lw': .6, 'capsize': 1})
    ax.set_xticks(x, [f'{l:.0%}' for l in LOADS]); ax.legend(ncol=5, fontsize=9)
    decorate(ax, x='100台VM平均 CPU 占用率', y='服务器（蓝）+ UPS损耗（橙） / W')
    inset=ax.inset_axes([.06,.56,.35,.31])
    total30=np.array([vals(arch,.3,m,'total_w').mean() for m in METHODS])
    inset.bar(np.arange(5),total30,color=COLORS)
    inset.set_ylim(total30.min()-100,total30.max()+100)
    inset.set_xticks(np.arange(5),['FFD','BFD','GA','GGA','B-GA'],fontsize=7)
    inset.tick_params(axis='y',labelsize=7); inset.set_title('30% 工况总功率 / W（局部放大）',fontsize=8)
    b,p,uncertainty=original30[arch]
    for method,estimate in [('BFD',b),('BFD-GA',p)]:
        actual30=vals(arch,.3,method,'total_w').mean()
        static_estimates.append({'figure':f'2-{num}','architecture':arch,'load':.3,'method':method,
            'thesis_visual_estimate_w':estimate,'estimated_reading_uncertainty_w':uncertainty,
            'reproduced_w':float(actual30),'relative_difference_pct':100*(actual30-estimate)/estimate})
    save(fig, num, f'{arch} 五算法功率', f'5种子均值±标准差；服务器部分BFD-GA与BFD严格相同。30%原图估读：BFD约{b} W、BFD-GA约{p} W（±{uncertainty} W）；本次分别{total30[1]:.1f}、{total30[4]:.1f} W。UPS容量/冗余及系数有假设，未达精确数值复现。')

digit20 = {'N+1AC': [1.1,2.35,2.05,1.7,1.1,.9,.72], 'N+1DC': [1.8,2.8,2.38,2.01,1.71,1.08,.88]}
digit23 = {'2NAC': [1.2,2.3,2.8,3.1,3.5,2.4,2.2], '2NDC': [28.5,28.,25.8,23.5,21.2,17.5,15.1]}
for num, architectures in [(20,ARCH[:2]), (23,ARCH[2:])]:
    fig, axes = plt.subplots(1,2,figsize=(12,5.2)); x=np.arange(7)
    for k, arch in enumerate(architectures):
        total, loss = reductions(arch), reductions(arch,'ups_loss_w')
        axes[0].bar(x+(k-.5)*.3,total,.3,label=arch,color=COLORS[k])
        axes[1].plot(x,loss,'o-',label=arch+'：仅UPS损耗',color=COLORS[k])
        if num == 20: axes[0].plot(x,digit20[arch],'--',color=COLORS[k],label=arch+'原图估读')
        else: axes[1].plot(x,digit23[arch],'--',color=COLORS[k],label=arch+'原图估读')
        for l,a,b in zip(LOADS,total,loss): METRICS.append({'metric':'reduction','architecture':arch,'load':l,'total_pct':a,'ups_only_pct':b})
    for ax in axes: ax.set_xticks(x,[f'{l:.0%}' for l in LOADS]); ax.legend(fontsize=8); decorate(ax,x='CPU 占用率',y='相对 BFD 下降率 / %')
    axes[0].set_title('服务器 + UPS 总功率'); axes[1].set_title('仅 UPS 功率损耗')
    save(fig,num,'能耗下降率与分母辨析','原图估读用于视觉比较，非精确原始数据。图2-23直流高柱可能采用UPS单独损耗分母，与正文总功率指标不一致；原文未解释，不能代为确定。')

fig, ax = plt.subplots(figsize=(11,5.5))
for method,color in zip(METHODS,COLORS):
    series=np.array([[float(r['total_w'])/1000 for r in read(f'dynamic_{method}_{seed}_times')] for seed in SEEDS])
    mean=series.mean(axis=0); ci=2.776*series.std(axis=0,ddof=1)/np.sqrt(5)
    ax.plot(t,mean,label=method,color=color,lw=1); ax.fill_between(t,mean-ci,mean+ci,color=color,alpha=.08)
ax.legend(ncol=5,fontsize=9); decorate(ax,y='机房实时总功率 / kW')
save(fig,24,'24 h 动态功率（5种子均值与95%区间）','当前在线迁移策略未重现原文184.98 kWh和排序。只随机移出过载VM，无未说明的周期性全局合并；原图BFD-GA约6.4 kW的量级与正文184.98/24=7.71 kW亦有差异。')

fig, ax = plt.subplots(figsize=(11,5.5)); x=np.arange(4); width=.19
cost_rows=[]
for k,method in enumerate(['BFD','FFD','GA','GGA']):
    costs=[]
    for arch in ['N+1AC','2NAC','N+1DC','2NDC']:
        saving=np.array([100*(vals(arch,l,method,'total_w').mean()-vals(arch,l,'BFD-GA','total_w').mean())/vals(arch,l,method,'total_w').mean() for l in LOADS])
        cost=float(saving@WEIGHTS)*80 # 8 billion USD / 100 / million.
        reference={('N+1AC','BFD'):138,('N+1AC','GGA'):131,('N+1DC','BFD'):162,('N+1DC','GGA'):157}.get((arch,method),'NA')
        costs.append(cost); cost_rows.append({'architecture':arch,'baseline':method,'saving_million_usd':cost,'thesis_stated_million_usd':reference})
    ax.bar(x+(k-1.5)*width,costs,width,label=method,color=COLORS[k])
ax.set_xticks(x,['N+1AC','2NAC','N+1DC','2NDC']); ax.legend(ncol=4); decorate(ax,x='供电架构',y='年电费节省 / 百万美元（假设全国基数80亿美元）')
save(fig,25,'年电费成本折算','按表2-1权重将各负载下降率加权，再乘假设的80亿美元全国电费基数。该基数由原文结果近似反推，不是现行美国统计，也不是论文明确给出的实验输入。')

fig, ax = plt.subplots(figsize=(11,5.4)); budgets=[3,6,12,28,45,59]; capacity_rows=[]
for method,color in [('GA',COLORS[0]),('BFD-GA',COLORS[4])]:
    solved=[]
    for b in budgets:
        sizes=sorted({int(r['vm_count']) for r in performance if int(r['budget'])==b})
        accepted=[n for n in sizes if sum(r['success']=='true' for r in performance if int(r['budget'])==b and int(r['vm_count'])==n and r['method']==method)>=4]
        maximum=max(accepted,default=0); solved.append(maximum)
        capacity_rows.append({'budget':b,'method':method,'max_tested_success_vm_count':maximum})
    ax.plot(budgets,solved,'o-',color=color,label=method+' 当前明确判据')
ax.plot(budgets,[12,30,40,150,230,288],'o--',color='#e8b099',label='BFD-GA 原文正文约值（第5点原文写48）')
ax.plot(budgets,[5,6,7,8,9,10],'--',color='#a2bddc',label='GA 原文5-10范围示意，非原始逐点值')
ax.set_xticks(budgets); ax.legend(fontsize=8); decorate(ax,x='遗传迭代预算',y='成功的最大已测试 VM 规模')
save(fig,26,'迭代预算与成功问题规模','本次成功判据：≤BFD主机数，功率≤固定BFD主机数的均衡机架下界×1.01，5种子至少4次成功；测试网格5-288台。原文成功判据缺失，结果不能等同于原作者最大规模。')

summary=[]
targets={'N+1AC':(2.09,1.72),'N+1DC':(2.47,2.01),'2NAC':(.93,.79),'2NDC':(1.13,.95)}
for arch in ARCH:
    r=reductions(arch); peak,weighted=targets[arch]
    summary.append({'architecture':arch,'reproduced_max_pct':float(r.max()),'reproduced_weighted_pct':float(r@WEIGHTS),
                    'thesis_reported_pct':peak,'thesis_weighted_pct':weighted,'weighted_error_pp':float(r@WEIGHTS)-weighted})
refenergy={'BFD-GA':184.98,'FFD':184.98/(1-.0232),'BFD':184.98/(1-.0201),'GA':184.98/(1-.068),'GGA':184.98/(1-.0334)}
dynsummary=[]
for method in METHODS:
    v=np.array([float(r['total_kwh']) for r in dynamic if r['method']==method])
    dynsummary.append({'method':method,'mean_kwh':float(v.mean()),'sd_kwh':float(v.std(ddof=1)),
                       'thesis_kwh':refenergy[method],'relative_error_pct':100*(v.mean()-refenergy[method])/refenergy[method]})
summary_data={'static':summary,'dynamic':dynsummary,'cost':cost_rows,'capacity':capacity_rows,
              'figures':NOTES,'validation_loss_range_w':[float(simulation.min()),float(simulation.max())],
              'largest_cpu_error':max(float(r['cpu_error']) for r in static+dynamic)}
(ROOT/'comparison/summary.json').write_text(json.dumps(summary_data,ensure_ascii=False,indent=2),encoding='utf-8')
def write_csv(name,rows):
    with (ROOT/'comparison'/name).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
write_csv('static_summary.csv',summary); write_csv('dynamic_comparison.csv',dynsummary)
write_csv('cost_comparison.csv',cost_rows); write_csv('performance_capacity.csv',capacity_rows); write_csv('reduction_details.csv',METRICS)
write_csv('static_30pct_visual_comparison.csv',static_estimates)
print('PASS: 12 figures, 12 source comparisons, numerical summaries; all based on Java CSV')
