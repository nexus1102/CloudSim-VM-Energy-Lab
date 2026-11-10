"""Twelve figures from a newly executed matrix and fixed-budget benchmark."""
import argparse,csv,html,json,math,shutil,sys
from pathlib import Path
from collections import defaultdict
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image,ImageOps,ImageDraw
from research_platform_report import generate,METHODS
from research_figure_benchmark_audit_v10 import audit
from paper_audit import rows,settings

ROOT=Path(__file__).resolve().parents[1]
COLORS=['#386b9d','#d78b29','#8555a4','#26856b','#c7433e']
plt.rcParams.update({'font.family':['Microsoft YaHei','SimHei'],'axes.unicode_minus':False,'font.size':10,'savefig.dpi':180})
def write(path,items):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(items[0]));w.writeheader();w.writerows(items)
def bins(path):
    power=np.zeros(288);covered=np.zeros(288)
    for r in rows(path):
        a,b=float(r['begin_s']),float(r['end_s']);p=float(r['server_w'])+float(r['ups_loss_w'])
        for k in range(int(a//300),min(288,int(math.ceil(b/300)))):
            dt=max(0,min(b,(k+1)*300)-max(a,k*300));power[k]+=dt*p;covered[k]+=dt
    np.testing.assert_allclose(covered,300,atol=1e-7,rtol=0)
    return power/300
def main(directory):
    run=Path(directory).resolve();generate(run);bench=audit(run/'report/figure_benchmark');out=run/'report';figdir=out/'figures';original=out/'original'
    figdir.mkdir(exist_ok=True);original.mkdir(exist_ok=True)
    for n in range(15,27):shutil.copy2(ROOT/f'evidence/original_2-{n}.png',original/f'original_2-{n}.png')
    def save(fig,n):
        fig.tight_layout();fig.savefig(figdir/f'figure_2-{n}.png');fig.savefig(figdir/f'figure_2-{n}.svg');plt.close(fig)
    def label(ax,title,x='时间 / h',y='功率 / W'):
        ax.set_title(title);ax.set_xlabel(x);ax.set_ylabel(y);ax.grid(alpha=.18,axis='y')
    prefix=run/'cases/platform_literal';hp=list(rows(Path(str(prefix)+'_hosts.csv')));ap=list(rows(Path(str(prefix)+'_assignments.csv')))
    hosts=defaultdict(dict);vms=defaultdict(dict)
    for r in hp:hosts[int(r['host_id'])][float(r['time_s'])]=r
    for r in ap:vms[int(r['vm_id'])][float(r['time_s'])]=r
    times=sorted(hosts[6]);x=np.array(times)/3600;members=[13,15,16,17,18]
    contributions=np.array([[float(vms[vm][t]['allocated_mips'])/2500 for t in times] for vm in members])
    cpu=np.array([float(hosts[6][t]['cpu']) for t in times]);cpuerror=float(np.max(abs(contributions.sum(axis=0)-cpu)))
    if cpuerror>1e-8:raise AssertionError('Figure 2-15 CPU stacking identity')
    fig,ax=plt.subplots(figsize=(10,3.6));ax.stackplot(x,*contributions,labels=[f'VM{v+1}' for v in members],alpha=.7)
    ax.plot(x,cpu,color='black',lw=.9,label='真实Host CPU');label(ax,'图2-15 固定布局：机架2服务器2',y='物理CPU占用率');ax.legend(ncol=6,fontsize=8);save(fig,15)
    seg=list(rows(Path(str(prefix)+'_segments.csv')));ts=np.array([float(r['begin_s']) for r in seg]);xs=ts/3600
    fig,ax=plt.subplots(figsize=(10,3.6));powers=np.array([[float(hosts[h][t]['power_w']) for t in ts] for h in [5,6,7]])
    output=np.array([float(r['rack1_output_w']) for r in seg]);rackerror=float(np.max(abs(powers.sum(axis=0)-output)))
    if rackerror>1e-6:raise AssertionError('Figure 2-16 rack power feedback')
    ax.stackplot(xs,*powers,labels=['服务器1','服务器2','服务器3'],alpha=.7);ax.plot(xs,output,color='black',lw=1,label='UPS2输出')
    label(ax,'图2-16 服务器功率汇总到UPS输出');ax.legend(ncol=4);save(fig,16)
    theory=.0241*output**2/2000+.0353*output+.0617*2000;loss=np.array([float(r['rack1_loss_w']) for r in seg]);losserror=float(np.max(abs(loss-theory)))
    if losserror>1e-6:raise AssertionError('Figure 2-17 literal equation')
    fig,ax=plt.subplots(figsize=(10,3.6));ax.plot(xs,loss,label='字面模型仿真');ax.plot(xs,theory,'--',label='独立公式计算')
    label(ax,'图2-17 表2-6字面公式验证（保留与原图量级矛盾）',y='UPS损耗 / W');ax.legend();save(fig,17)
    static=list(rows(run/'summary.csv'));static=[r for r in static if r['kind']=='static'];data=[]
    for cap in ['0.9','1.0']:
        for arch in ['N+1AC','N+1DC','2NAC','2NDC']:
            for level in range(10,71,10):
                for method in METHODS:
                    rs=[r for r in static if r['prefix'].startswith(f'static_cap{cap}_{arch}_{level}_{method}_')]
                    if len(rs)!=3:raise AssertionError('Static seed cardinality')
                    def avg(key):return float(np.mean([float(r[key]) for r in rs]))
                    demand=avg('requested_mi')/(300*2500*100)
                    data.append(dict(cap=cap,architecture=arch,level=level,method=method,actual_host_demand_pct=100*demand,
                        server_w=avg('server_kwh')*12000,ups_w=avg('ups_kwh')*12000,total_w=avg('total_kwh')*12000,
                        sd_total_w=float(np.std([float(r['total_kwh'])*12000 for r in rs],ddof=1))))
    write(out/'figure_static_metrics.csv',data)
    def values(arch,method,key,cap='0.9'):
        return np.array([next(r[key] for r in data if r['cap']==cap and r['architecture']==arch and r['level']==l and r['method']==method) for l in range(10,71,10)])
    xx=np.arange(7);levels=list(range(10,71,10));hatches=['xx','..','//','\\\\','']
    for n,arch in [(18,'N+1AC'),(19,'N+1DC'),(21,'2NAC'),(22,'2NDC')]:
        fig,ax=plt.subplots(figsize=(11,4.3))
        for j,method in enumerate(METHODS):
            loc=xx+(j-2)*.16;server=values(arch,method,'server_w');ups=values(arch,method,'ups_w')
            ax.bar(loc,server,.15,color='#6ba8d0',hatch=hatches[j],edgecolor='#25465d',linewidth=.4,label=method)
            ax.bar(loc,ups,.15,bottom=server,color='#eca45c',hatch=hatches[j],edgecolor='#795638',linewidth=.4,
                yerr=values(arch,method,'sd_total_w'),capsize=1.5)
        ax.set_xticks(xx,[f'{l}%' for l in levels]);label(ax,f'图2-{n} {arch}：蓝=服务器，橙=UPS；cap=0.9','目标总物理需求 / 100 Host容量','服务器+UPS功率 / W');ax.legend(ncol=5,fontsize=8);save(fig,n)
    rates=[]
    for n,prefixarch in [(20,'N+1'),(23,'2N')]:
        fig,axs=plt.subplots(1,2,figsize=(12,3.8))
        for j,(metric,title) in enumerate([('total_w','服务器+UPS总功率分母'),('ups_w','UPS损耗单独分母')]):
            for k,supply in enumerate(['AC','DC']):
                arch=prefixarch+supply;b=values(arch,'BFD',metric);p=values(arch,'BFD-GA',metric);r=100*(1-p/b)
                axs[j].bar(xx+(k-.5)*.33,r,.32,label=supply)
                for level,rate in zip(levels,r):rates.append(dict(figure=n,architecture=arch,level=level,denominator=metric,saving_pct=float(rate)))
            axs[j].set_xticks(xx,[f'{l}%' for l in levels]);axs[j].axhline(0,color='gray',lw=.7)
            label(axs[j],f'图2-{n} {title}','目标总物理需求','BFD-GA相对BFD下降 / %');axs[j].legend()
        save(fig,n)
    write(out/'figure_saving_denominators.csv',rates)
    fig,axs=plt.subplots(1,2,figsize=(14,4));dynamicbins=[]
    for ax,controller in zip(axs,['threshold','consolidation']):
        for method,color in zip(METHODS,COLORS):
            curve=bins(run/f'cases/n_plus_1_standby_cap0.9_{controller}_{method}_101_segments.csv')
            ax.plot(np.arange(288)/12,curve,color=color,lw=.9,label=method)
            for k,power in enumerate(curve):dynamicbins.append(dict(controller=controller,method=method,seed=101,begin_s=k*300,mean_total_w=float(power)))
        label(ax,'图2-24 '+('仅90%过载迁移' if controller=='threshold' else '补充轻载整合（工程假设）'),y='300秒区间平均功率 / W');ax.legend(ncol=2,fontsize=8)
    low=min(ax.get_ylim()[0] for ax in axs);high=max(ax.get_ylim()[1] for ax in axs)
    for ax in axs:ax.set_ylim(low,high)
    save(fig,24);write(out/'figure_dynamic_bins.csv',dynamicbins)
    weighted=list(rows(out/'weighted_static.csv'));cost=[];archs=['N+1AC','2NAC','N+1DC','2NDC'];base_low=8.014888e9;base_high=8.075802e9
    fig,axs=plt.subplots(1,2,figsize=(13,4))
    for j,method in enumerate(METHODS[:-1]):
        rate=np.array([float(next(r['time_weighted_saving_pct'] for r in weighted if r['cap']=='0.9' and r['architecture']==a and r['baseline']==method)) for a in archs])
        center=rate/100*(base_low+base_high)/2/1e6;error=np.abs(rate)/100*(base_high-base_low)/2/1e6;loc=np.arange(4)+(j-1.5)*.19
        axs[0].bar(loc,rate,.18,label=method);axs[1].bar(loc,center,.18,yerr=error,capsize=2,label=method)
        for arch,r in zip(archs,rate):
            estimates=sorted([r/100*base_low/1e6,r/100*base_high/1e6]);cost.append(dict(architecture=arch,baseline=method,time_weighted_pct=float(r),
                conditional_million_usd_low=estimates[0],conditional_million_usd_high=estimates[1],bill_low_usd=base_low,bill_high_usd=base_high,source='Thesis rounding-based reverse inference, not independently measured industry bill'))
    for ax in axs:ax.set_xticks(range(4),archs);ax.axhline(0,color='gray',lw=.7);ax.legend(ncol=2,fontsize=8)
    label(axs[0],'图2-25 时间加权节省率','架构','Σw×分档节省率 / %');label(axs[1],'图2-25 反推行业账单的条件外推','架构','年度节省 / 百万美元（条件）');save(fig,25);write(out/'figure_conditional_cost.csv',cost)
    frontier=list(rows(out/'figure_benchmark/frontier.csv'));budgets=[3,6,12,28,45,48,59]
    fig,axs=plt.subplots(2,2,figsize=(14,8))
    for i,(metric,precision) in enumerate([('max_tested_quality_n','可优化差额1%'),('max_tested_precision_n','严格1e-7W精度')]):
        for ax,profile in zip(axs[i],['current128','example4']):
            for method,color in [('GA',COLORS[2]),('GGA',COLORS[3]),('BFD-GA',COLORS[4])]:
                y=[int(next(r[metric] for r in frontier if r['profile']==profile and r['method']==method and int(r['budget'])==b)) for b in budgets]
                ax.plot(range(7),y,'o-',label=method,color=color)
            ax.set_xticks(range(7),budgets);label(ax,'图2-26 '+precision+' / '+('128VM资源上限' if profile=='current128' else '论文示例4VM资源上限'),'代数（45与48均实算）','达声明目标的已测最大VM数');ax.legend(fontsize=8)
    save(fig,26)
    checks=list(rows(out/'figure_benchmark/checks.csv'));sizes=[5,10,12,30,40,80,150,230,288]
    fig,axs=plt.subplots(2,3,figsize=(15,8))
    for i,profile in enumerate(['current128','example4']):
        for j,method in enumerate(['GA','GGA','BFD-GA']):
            ax=axs[i,j];grid=np.array([[sum(r['quality_pass']=='True' for r in checks if r['profile']==profile and r['method']==method and int(r['n'])==n and int(r['budget'])==b) for b in budgets] for n in sizes])
            ax.imshow(grid,aspect='auto',cmap='Blues',vmin=0,vmax=3);ax.set_xticks(range(7),budgets);ax.set_yticks(range(9),sizes)
            for a in range(9):
                for b in range(7):ax.text(b,a,f'{grid[a,b]}/3',ha='center',va='center',fontsize=8,color='white' if grid[a,b]>1 else 'black')
            ax.set_title(profile+' '+method);ax.set_xlabel('代数');ax.set_ylabel('VM数')
    fig.tight_layout();fig.savefig(out/'全部规模命中率.png');plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(13,4))
    for ax,profile in zip(axs,['current128','example4']):
        for method,color in zip(['GA','GGA','BFD-GA'],COLORS[2:]):
            y=[np.median([float(r['solve_ms']) for r in checks if r['profile']==profile and r['method']==method and int(r['budget'])==59 and int(r['n'])==n]) for n in sizes]
            ax.plot(sizes,y,'o-',label=method,color=color)
        label(ax,'实际59代耗时 '+profile,'VM数','三种子求解耗时中位数 / ms');ax.legend()
    fig.tight_layout();fig.savefig(out/'实际计算耗时.png');plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(13,4))
    for ax,profile in zip(axs,['current128','example4']):
        for method,color in zip(['GA','GGA','BFD-GA'],COLORS[2:]):
            y=[int(next(r['max_tested_precision_n'] for r in frontier if r['profile']==profile and r['method']==method and int(r['budget'])==b)) for b in budgets]
            ax.plot(range(7),y,'o-',label=method,color=color)
        ax.set_xticks(range(7),budgets);label(ax,'严格计算精度 '+profile,'代数','达1e-7W精度的最大已测VM数');ax.legend()
    fig.tight_layout();fig.savefig(out/'严格精度规模.png');plt.close(fig)
    notes={15:'固定布局下VM已分配CPU叠加与真实Host CPU一致；替代轨迹不能逐点匹配作者波形。',
        16:'显示机架2三个驻留Host功率叠加与UPS输出一致，包含实际Host反馈。',
        17:'独立字面公式与仿真一致；表2-6空载损耗123.4W已高于原图约70W，矛盾保留。',
        18:'N+1 AC：三种子功率分量及波动；完整算法排序以本次原始结果为准。',
        19:'N+1 DC：保留UPS曲线重建与备用损耗假设，不用选种子恢复排序。',
        20:'对应N+1的AC/DC比较；总功率及UPS损耗两种分母分别计算。',
        21:'2N AC：两套N模块均担负载，服务器与UPS分开核算。',
        22:'2N DC：同样明确模块结构，未模拟故障切换瞬态。',
        23:'对应2N的AC/DC比较；原图纵轴与正文口径不一致，两种分母并列。',
        24:'固定种子101展示两种控制；三种子能耗及正文/图像双偏差另见结果报告，不择优选择曲线。',
        25:'使用Σw×分档节省率；金额为从原文反推账单的条件外推，不是独立获得行业账单或完整费用复现。',
        26:'1296次真实求解；GA/GGA按原生服务器目标，BFD-GA按固定BFD分组总功率目标。无集中BFD预置种子。采用同类300代最好可行参照；BFD-GA允许可优化功率差额的1%，另报告1e-7W严格精度。两资源假设均显示，4VM是原文搜索空间示例，不能确认为作者实验参数。最大命中规模不是理论容量，所有方法全部方案可行。停止判据未知，原图逐点形状仍不能保证；完整命中率、耗时及严格口径均保留。'}
    page=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>图2-15至2-26重跑对照</title>',
        '<style>body{font:16px/1.7 "Microsoft YaHei",sans-serif;max-width:1600px;margin:30px auto;padding:0 20px;color:#203c4b}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}img{width:100%}section{border-top:1px solid #ddd;padding:20px 0}figure{margin:0}@media(max-width:800px){.pair{grid-template-columns:1fr}}</style>',
        '<h1>v10 GA与规模实验修正：十二图对照</h1><p>所有图均使用实际新运行数据。实现核验、趋势与数值容差分别判断；完整排名与原图2-26逐点曲线仍需按报告限定。</p><a href="结果报告.md">数值报告</a> · <a href="逐图核验.md">逐图核验</a> · <a href="GA与图2-26最终修正说明.md">根因与最终修正说明</a>']
    md=['# v10十二图重跑核验','', '新主矩阵1096案例、27条轨迹；补充图2-26为1296次原生目标求解，两资源情景，每代82458个实际方案独立核验通过。PASS是实现核验，不是论文趋势恢复。',
        '',f'图2-15最大CPU叠加误差 {cpuerror:.3g}；图2-16功率汇总误差 {rackerror:.3g}W；图2-17字面公式误差 {losserror:.3g}W。',
        '', '原作者一天数据缺失，平台验证20VM使用已有明确标识替代输入；静态使用公开快照、动态使用公开PlanetLab一天100VM。静态横轴为目标占总Host容量的需求，实际值另列CSV。',
        '', '| 图号 | 本次解释与限制 |','|---|---|']
    for n in range(15,27):
        page.append(f'<section><h2>图2-{n}</h2><p>{html.escape(notes[n])}</p><div class="pair"><figure><figcaption>原论文</figcaption><img src="original/original_2-{n}.png"></figure><figure><figcaption>当前重新仿真</figcaption><img src="figures/figure_2-{n}.png"></figure></div></section>')
        md.append(f'| 2-{n} | {notes[n]} |')
    page.append('<h2>全部规模与真实计算性能</h2><p>3/3为三个种子全达到声明目标。零代可行不等于优化完成。两精度口径同时保留。</p><img src="全部规模命中率.png"><img src="实际计算耗时.png"><img src="严格精度规模.png"></html>');(out/'逐图对照.html').write_text('\n'.join(page),encoding='utf-8');(out/'逐图核验.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    tiles=[]
    for n in range(15,27):
        im=Image.open(figdir/f'figure_2-{n}.png').convert('RGB');tile=Image.new('RGB',(640,270),'white');tile.paste(ImageOps.contain(im,(640,245)),(0,25));ImageDraw.Draw(tile).text((10,5),f'Figure 2-{n}',fill='black');tiles.append(tile)
    contact=Image.new('RGB',(1920,1080),'white')
    for i,tile in enumerate(tiles):contact.paste(tile,((i%3)*640,(i//3)*270))
    contact.save(out/'十二图总览.png')
    missing=[str(p) for n in range(15,27) for ext in ['png','svg'] if not (p:=figdir/f'figure_2-{n}.{ext}').is_file()]
    if missing:raise AssertionError(missing)
    result=dict(status='PASS',figures=12,formats=['PNG','SVG'],cpu_stack_error=cpuerror,rack_power_error_w=rackerror,literal_loss_error_w=losserror,benchmark=bench)
    (out/'figure_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS 12 new figures, PNG/SVG, metrics and original comparison gallery')
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');p=argparse.ArgumentParser();p.add_argument('--run',required=True);main(p.parse_args().run)
