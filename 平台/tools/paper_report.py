"""Report and twelve scientific figures from final paper-aligned audited CSVs."""
from pathlib import Path
import csv,json,math,hashlib,html
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image as PILImage
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,PageBreak,Image,Spacer
from reportlab.lib.pagesizes import landscape,A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import pymupdf
ROOT=Path(__file__).resolve().parents[1];R=ROOT/'paper_alignment';F=R/'figures'
METHODS=['FFD','BFD','GA','GGA','BFD-GA'];DAYS=['20110303','20110306','20110309','20110322','20110325','20110403','20110409','20110411','20110412','20110420']
PALETTE=['#386b9d','#d78b29','#8555a4','#26856b','#c7433e']
plt.rcParams.update({'font.family':['Microsoft YaHei','SimHei'],'axes.unicode_minus':False,'font.size':10,'savefig.dpi':180})
def rows(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def stats(data,case):
    result={}
    for m in METHODS:
        a=[v for v in data if v['case']==case and v['method']==m];e=np.array([float(v['total_kwh']) for v in a]);n=len(e)
        if not n:continue
        result[m]={'n':n,'mean_kwh':float(e.mean()),'sd_kwh':float(e.std(ddof=1)) if n>1 else 0,
                   'migrations':float(np.mean([int(v['started']) for v in a])),
                   'shortage_pct':float(np.mean([100*(1-float(v['delivered_mi'])/float(v['requested_mi'])) for v in a])),
                   'kwh_per_billion_mi':float(np.mean([float(v['total_kwh'])/float(v['delivered_mi'])*1e9 for v in a]))}
    return result
def average_bins(prefix):
    values=np.zeros(288)
    for v in rows(R/'results'/f'{prefix}_segments.csv'):
        begin,end=float(v['begin_s']),float(v['end_s']);power=float(v['server_w'])+float(v['ups_loss_w'])
        for k in range(int(begin//300),min(288,int(math.ceil(end/300)))):
            values[k]+=power*max(0,min(end,(k+1)*300)-max(begin,k*300))/300
    return values
def save(fig,name):
    fig.savefig(F/(name+'.png'),bbox_inches='tight');fig.savefig(F/(name+'.svg'),bbox_inches='tight');plt.close(fig)
def decorate(ax,title,x='时间 / h',y='功率 / W'):
    ax.set_title(title);ax.set_xlabel(x);ax.set_ylabel(y);ax.grid(alpha=.2)
def main():
    audit=json.loads((R/'audit/independent_checks.json').read_text(encoding='utf-8'))
    if audit['status']!='PASS' or audit['dynamic_runs']!=540 or audit['static_runs']!=1400 or audit.get('performance_runs')!=540:
        raise RuntimeError('Final complete independent audit required: 540 dynamic / 1400 static / 540 benchmarks')
    F.mkdir(exist_ok=True);(R/'report').mkdir(exist_ok=True)
    data=rows(R/'results/dynamic_summary.csv');static=rows(R/'results/static_summary.csv');perf=rows(R/'results/performance.csv')
    source=json.loads((ROOT/'correction/comparison/summary.json').read_text(encoding='utf-8'))
    minimal=stats(data,'main');framework=stats(data,'framework_underload');comparisons=[]
    for m in METHODS:
        ref=next(v for v in source['energy_comparison'] if v['method']==m)
        for c,table in [('文字最小基线',minimal),('框架轻载整合重建',framework)]:
            e=table[m]['mean_kwh'];comparisons.append({'case':c,'method':m,'mean_kwh':e,'image_kwh':ref['reference_image_estimated_kwh'],
                'body_kwh':ref['thesis_text_kwh'],'image_error_pct':100*(e/ref['reference_image_estimated_kwh']-1),'body_error_pct':100*(e/ref['thesis_text_kwh']-1)})
    robust=[]
    for cohort in ['random','cohort25']:
        for day in DAYS:
            c='framework_underload' if day=='20110303' and cohort=='cohort25' else f'framework_{cohort}_{day}'
            a={v['method']:v for v in data if v['case']==c and v['seed']=='101'}
            robust.append({'cohort':cohort,'day':day,'bfd_ga_vs_bfd_pct':100*(1-float(a['BFD-GA']['total_kwh'])/float(a['BFD']['total_kwh']))})
    paired=[]
    for c in ['main','framework_underload']:
        a={(v['method'],v['seed']):float(v['total_kwh']) for v in data if v['case']==c}
        seeds=sorted({v['seed'] for v in data if v['case']==c},key=int)
        diff=np.array([a['GA',k]-a['GGA',k] for k in seeds]);half=2.045*diff.std(ddof=1)/np.sqrt(len(diff))
        paired.append({'case':c,'ga_minus_gga_kwh':float(diff.mean()),'ci95_low':float(diff.mean()-half),'ci95_high':float(diff.mean()+half),'gga_wins':int((diff>0).sum()),'n':len(diff)})
    summary={'minimal':minimal,'framework':framework,'comparison':comparisons,'robustness':robust,'paired_ga_gga':paired,'audit':{k:v for k,v in audit.items() if k!='checks'}}
    (R/'report/summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    with (R/'report/energy_comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
        out=csv.DictWriter(f,fieldnames=comparisons[0]);out.writeheader();out.writerows(comparisons)
    h=rows(R/'results/platform_fixed_hosts.csv');a=rows(R/'results/platform_fixed_assignments.csv')
    platform_config=dict(line.split('=',1) for line in (R/'results/platform_fixed_settings.properties').read_text(encoding='utf-8').splitlines() if '=' in line and not line.startswith('#'))
    platform_mips=float(platform_config['host.mips'])
    times=sorted({float(v['time_s']) for v in h});members=[13,15,16,17,18]
    series={vm:{float(v['time_s']):float(v['requested_mips'])/platform_mips for v in a if int(v['vm_id'])==vm} for vm in members}
    host={float(v['time_s']):float(v['cpu']) for v in h if v['host_id']=='6'}
    fig,ax=plt.subplots(figsize=(9,3.4));ax.stackplot(np.array(times)/3600,*[[series[vm][t] for t in times] for vm in members],labels=[f'VM{vm+1}' for vm in members],alpha=.65)
    ax.plot(np.array(times)/3600,[host[t] for t in times],color='black',lw=1,label='实际Host CPU');decorate(ax,'图2-15：机架2服务器2映射与CPU叠加',y='物理CPU占用率');ax.legend(ncol=6,fontsize=8);save(fig,'figure_2-15')
    seg=rows(R/'results/platform_fixed_segments.csv');x=[float(v['begin_s'])/3600 for v in seg]
    fig,ax=plt.subplots(figsize=(9,3.4))
    for rack in range(2):ax.plot(x,[float(v[f'rack{rack}_output_w']) for v in seg],label=f'UPS{rack+1}输出 = 机架Host功率和')
    decorate(ax,'图2-16：UPS输出功率（实际Host反馈）');ax.legend();save(fig,'figure_2-16')
    fig,ax=plt.subplots(figsize=(9,3.4));p=np.array([float(v['rack1_output_w']) for v in seg]);installed=float(platform_config['ups.usable.w'])*float(platform_config['ups.factor'])
    theory=float(platform_config['ups.a0'])*p*p/installed+float(platform_config['ups.a1'])*p+float(platform_config['ups.a2'])*installed
    ax.plot(x,[float(v['rack1_loss_w']) for v in seg],label='模块损耗');ax.plot(x,theory,'--',label='独立原式计算');decorate(ax,'图2-17：表2-6模型独立验收');ax.legend();save(fig,'figure_2-17')
    def values(arch,method,field):return [np.mean([float(v[field]) for v in static if v['family']=='physical_host_load' and v['architecture']==arch and v['method']==method and abs(float(v['target'])-level/100)<1e-6]) for level in range(10,71,10)]
    for num,arch in [(18,'N+1AC'),(19,'N+1DC'),(21,'2NAC'),(22,'2NDC')]:
        fig,axs=plt.subplots(1,2,figsize=(12,3.6))
        for m,color in zip(METHODS,PALETTE):
            actual=np.array(values(arch,m,'actual_host_demand'))*100
            axs[0].plot(actual,values(arch,m,'total_w'),marker='o',color=color,label=m,ls='--' if m=='BFD' else '-')
            axs[1].plot(actual,values(arch,m,'ups_w'),marker='o',color=color,label=m,ls='--' if m=='BFD' else '-')
        decorate(axs[0],f'图2-{num}：{arch} 总功率','总物理需求 / 100 Host容量 (%)');decorate(axs[1],'UPS损耗','总物理需求 / 100 Host容量 (%)');axs[0].legend(fontsize=8);save(fig,f'figure_2-{num}')
    for num,kind in [(20,'AC'),(23,'DC')]:
        fig,ax=plt.subplots(figsize=(9,3.4))
        for arch in ['N+1'+kind,'2N'+kind]:
            b=np.array(values(arch,'BFD','total_w'));proposed=np.array(values(arch,'BFD-GA','total_w'))
            ax.plot(np.array(values(arch,'BFD','actual_host_demand'))*100,100*(b-proposed)/b,'o-',label=arch)
        decorate(ax,f'图2-{num}：相对BFD的总功率下降','总物理需求 (%)','下降率 / %');ax.legend();save(fig,f'figure_2-{num}')
    fig,axs=plt.subplots(1,3,figsize=(17,4.1));axs[0].imshow(PILImage.open(ROOT/'evidence/original_2-24.png'));axs[0].axis('off');axs[0].set_title('原图2-24（参考）')
    for ax,case,title in [(axs[1],'main','文字最小基线'),(axs[2],'framework_underload','框架轻载整合重建')]:
        for m,color in zip(METHODS,PALETTE):ax.plot(np.arange(288)/12,average_bins(f'{case}_{m}_101'),color=color,lw=.9,label=m)
        decorate(ax,title,y='300秒区间平均功率 / W');ax.legend(fontsize=7,ncol=2)
    lower=min(axs[1].get_ylim()[0],axs[2].get_ylim()[0]);upper=max(axs[1].get_ylim()[1],axs[2].get_ylim()[1])
    axs[1].set_ylim(lower,upper);axs[2].set_ylim(lower,upper);fig.tight_layout();save(fig,'figure_2-24')
    fig,ax=plt.subplots(figsize=(9,3.5));xx=np.arange(5);ax.bar(xx-.18,[minimal[m]['mean_kwh'] for m in METHODS],.36,label='文字基线');ax.bar(xx+.18,[framework[m]['mean_kwh'] for m in METHODS],.36,label='框架重建');ax.set_xticks(xx,METHODS);decorate(ax,'调度语义对24小时能耗的影响','算法','能耗 / kWh');ax.legend();save(fig,'controller_energy')
    fig,axs=plt.subplots(1,2,figsize=(11,3.6));axs[0].bar(METHODS,[framework[m]['shortage_pct'] for m in METHODS],color=PALETTE);decorate(axs[0],'服务量代价','算法','CPU需求未满足 / %')
    axs[1].bar(METHODS,[framework[m]['kwh_per_billion_mi'] for m in METHODS],color=PALETTE);decorate(axs[1],'按实际完成MI归一化','算法','kWh / 十亿MI');save(fig,'service_cost')
    fig,ax=plt.subplots(figsize=(10,3.5))
    for cohort in ['random','cohort25']:ax.plot(range(10),[v['bfd_ga_vs_bfd_pct'] for v in robust if v['cohort']==cohort],'o-',label=cohort)
    ax.axhline(0,color='gray',lw=.8);ax.set_xticks(range(10),DAYS,rotation=25);decorate(ax,'十天稳健性：BFD-GA相对BFD','公开轨迹日期','总能耗下降 / %');ax.legend();save(fig,'robustness')
    fig,ax=plt.subplots(figsize=(10,3.5));weights=np.array([1,22,38,26,10,2,1])/100
    for j,m in enumerate(['FFD','BFD','GA','GGA']):
        gains=[]
        for arch in ['N+1AC','N+1DC','2NAC','2NDC']:
            b=np.dot(weights,values(arch,m,'total_w'));pr=np.dot(weights,values(arch,'BFD-GA','total_w'));gains.append(100*(1-pr/b))
        ax.bar(np.arange(4)+(j-1.5)*.18,gains,.18,label=m)
    ax.set_xticks(range(4),['N+1AC','N+1DC','2NAC','2NDC']);decorate(ax,'图2-25：条件加权电费下降比例','架构','成本下降 / %');ax.legend();save(fig,'figure_2-25')
    fig,ax=plt.subplots(figsize=(9,3.5))
    for m in ['GA','BFD-GA']:
        frontier=[]
        for budget in [3,6,12,28,45,59]:
            feasible=[n for n in [5,10,12,30,40,80,150,230,288] if np.mean([v['within_1pct']=='true' for v in perf if v['method']==m and int(v['budget'])==budget and int(v['vm_count'])==n])>=.8]
            frontier.append(max(feasible) if feasible else 0)
        ax.plot([3,6,12,28,45,59],frontier,'o-',label=m)
    decorate(ax,'图2-26：有限网格求解成功规模','迭代代数','VM数量');ax.legend();save(fig,'figure_2-26')
    report(summary,paired,robust)
    notes={15:'固定布局及CPU叠加通过；公开替代轨迹不同，不要求逐点波形一致。',16:'UPS输出等于真实机架Host功率和；绝对波形受所选轨迹影响。',17:'表2-6原式独立验收通过；表参数与原图量级矛盾保留，未调参贴图。',
           18:'总负载增加与供电优化机制可检验；全部算法排序未恢复。',19:'总负载增加与供电优化机制可检验；全部算法排序未恢复。',
           20:'节能率按实际数据计算；峰值和逐点变化尚不能认定与原图一致。',21:'高负载GA/GGA可能优于BFD-GA；如实保留。',22:'高负载GA/GGA可能优于BFD-GA；如实保留。',23:'节能率按实际数据计算；峰值和逐点变化尚不能认定与原图一致。',
           24:'三方对照：原图、文字最小基线、框架轻载重建。两种新控制曲线使用共同纵轴，原图尺度保留。',
           25:'条件加权相对费用；相对GA/GGA的加权优势未恢复，非原文绝对金额复现。',26:'明确的1%功率/80%种子成功判据；相对规模差异可见，原图迭代增长曲线未恢复。'}
    gallery=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>论文与修正版逐图对照</title>',
             '<style>body{font:16px/1.7 "Microsoft YaHei",sans-serif;max-width:1600px;margin:32px auto;padding:0 20px;color:#203c4b}section{margin:40px 0;border-top:1px solid #ddd} .pair{display:flex;gap:20px}.pair figure{width:50%;margin:0}img{width:100%;height:auto}figcaption{font-weight:bold}a{color:#386b9d}@media(max-width:800px){.pair{display:block}.pair figure{width:100%}}</style>',
             '<h1>图2-15至图2-26：原论文与当前修正结果</h1><p>功能链路验收与趋势一致性分开判断。原图保持原始尺度，逐图说明未达标项；作者未知设置没有通过拟合补造。</p><p><a href="论文一致性修正报告.pdf">完整报告</a> · <a href="../../correction/论文平台扩展与仿真思路核对.md">核对文档</a></p>']
    for num in range(15,27):
        original=ROOT/f'evidence/original_2-{num}.png'
        if not original.is_file():raise FileNotFoundError(original)
        gallery.append(f'<section><h2>图2-{num}</h2><p>{notes[num]}</p>')
        if num==24:gallery.append('<img src="../figures/figure_2-24.png" alt="原图及两个重建控制的三方对照">')
        else:gallery.append(f'<div class="pair"><figure><figcaption>原论文</figcaption><img src="../../evidence/original_2-{num}.png" alt="原图2-{num}"></figure><figure><figcaption>当前修正结果</figcaption><img src="../figures/figure_2-{num}.png" alt="修正图2-{num}"></figure></div>')
        gallery.append('</section>')
    gallery.append('</html>');(R/'report/逐图对照.html').write_text('\n'.join(gallery),encoding='utf-8')
    outputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for base in ['figures','report'] for p in (R/base).iterdir() if p.is_file()}
    (R/'audit/deliverable_hashes.json').write_text(json.dumps(outputs,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS paper report, 12 numbered PNG/SVG figures and supplementary figures')
def report(summary,paired,robust):
    pdfmetrics.registerFont(TTFont('Chinese',str(Path('C:/Windows/Fonts/simhei.ttf'))))
    styles={k:ParagraphStyle(k,fontName='Chinese',fontSize=size,leading=lead,spaceAfter=8,textColor=colors.HexColor('#203c4b')) for k,size,lead in [('title',21,28),('heading',16,21),('body',10,16),('cell',8.5,12)]}
    story=[]
    def para(text,style='body'):story.append(Paragraph(text,styles[style]))
    def page(title):
        if story:story.append(PageBreak())
        para(title,'heading')
    def table(items,widths):
        t=Table([[Paragraph(html.escape(str(v)),styles['cell']) for v in row] for row in items],colWidths=widths,repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e0edf2')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f5f7f9')]),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story.append(t);story.append(Spacer(1,8))
    def image(name,width=742,maxheight=350):
        im=Image(str(F/(name+'.png')));scale=min(width/im.imageWidth,maxheight/im.imageHeight);im.drawWidth=im.imageWidth*scale;im.drawHeight=im.imageHeight*scale;story.append(im)
    para('第二章：论文一致性修正与独立验证','title');para('CloudSim 3.0.3 / Java 8 | 2026-10-12','heading')
    para('完成图2-14映射、218 W/218.3 W分离、两步分组、策略接口、标准VM_MIGRATE事件、实际Host反馈和独立UPS验收。最终运行：540组动态、1400组静态、540组算法求解基准，另有平台和迁移边界测试。')
    para('<b>结论：供电感知数据中心的已公开功能链路验证通过；完整作者实现仍不可确认。</b>论文未说明轻载整合及在线目的规则。分别报告文字最小基线和CloudSim框架行为重建；后者恢复首日BFD-GA最低、GGA低于GA的核心排序，但不保证所有日期/负载都保持该排序。')
    table([['修正项','落实与证据'],['真实模块','PowerSupplyAwareDataCenter extends PowerDatacenter；PowerEfficiencyAwarePolicy extends PowerVmAllocationPolicyAbstract'],['CPU与UPS','独立Python由VM实际分配重建CPU，按原式独立计算UPS及事件积分；不是同函数自比'],['迁移','源端服务下降、目标复制CPU、双端开启及UPS损耗；端点互斥、RAM/BW/存储预留'],['公开数据','完整作者发布十天PlanetLab数据：11746条VM日轨迹、3382848采样，原始幅值不修改'],['未建模项','无硬件依据的脏页、内存/交换机附加功耗和启动能量；不能称为完整硬件成本']], [135,607])
    page('参数、论文规则与重建边界')
    table([['项目','论文明确内容','实际运行与假设'],['规模','100 Host、5机架；动态100 VM','一致；同构Host2500 MIPS/1 PE，VM四档MIPS是公开示例重建'],['功率','平台218/350 W，主实验218.3/350 W','分别读取platform/main.properties；无VM睡眠0 W，驻留零CPU VM仍空载耗电'],['UPS','N+1/2N、AC/DC模型；平台表2-6','平台2kW字面系数；主7kW、N=4均分因子1.25、图2-5拟合系数均为重建'],['GA/GGA','编码和算法类别，未给完整参数','40个体、60代，交叉.8、变异.05；总功率目标主方案，server_only敏感性'],['动态','超过90%随机选择一个VM','文字基线每300s每过载源选1个；全局整合不作为基线'],['框架对照','原文未公开轻载子流程','依据原生MigrationAbstract存在轻载撤离，独立重建，非作者代码'],['资源与网络','未给RAM、带宽及迁移细节','VM512MB，Host64GB/1Gbit；半带宽迁移，单端点串行，512MB为8.192秒']], [100,230,412])
    para('实际参数保存在每次运行的_settings.properties；JSON不再仅作为配置记录。原始数据和历史两版报告保持保留。图2-9采用0.9容量验收，但不能据此把物理容量或所有静态工况都改为0.9。')
    for num,title in [(15,'平台：实际VM映射与CPU叠加'),(16,'平台：UPS输出来自实际服务器功率'),(17,'平台：UPS独立理论验收')]:
        page(title);image(f'figure_2-{num}');para('20条公开原始轨迹最大CPU≤18%，确保图示固定布局可行；未经峰值缩放。固定图示与PEA-FF规则重建分别运行，无迁移。图2-17严格使用表2-6，因此量级与原论文图示仍存在未解决矛盾。')
    for num,title in [(18,'N+1交流'),(19,'N+1直流'),(20,'交流节能率'),(21,'2N交流'),(22,'2N直流'),(23,'直流节能率')]:
        page(f'图2-{num}：{title}');image(f'figure_2-{num}');para('主静态横轴为总物理需求/100 Host容量，通过VM数量改变、保留原始采样幅值；另有固定100 VM平均CPU横轴敏感性。部分FFD/BFD曲线重合，但算法语义辨别案例已通过。高负载下GA/GGA可能找到更少服务器，BFD不保证全局最少，不能强制BFD-GA在所有点最低。')
    page('图2-24：原图、文字基线与框架重建');image('figure_2-24',maxheight=300)
    para('新曲线为含迁移的300秒区间平均功率；单种子101展示波形，统计表采用30种子均值。图2-13只支持运行与功率反馈循环，不支持每步全局重新放置。原生CloudSim静态阈值同时有轻载整合，论文没有说明是否保留，因此两个控制口径并列，不能以数值更近决定哪个就是作者实现。')
    page('图像与正文：分别按15%容差验收')
    table([['方案','算法','均值kWh','原图偏差%','正文偏差%']]+[[v['case'],v['method'],f"{v['mean_kwh']:.3f}",f"{v['image_error_pct']:+.2f}",f"{v['body_error_pct']:+.2f}"] for v in summary['comparison']], [180,90,145,150,177])
    para('原图BFD-GA估读154.54kWh，保守读图误差±1.5kWh，非置信区间；正文184.98kWh，其他正文绝对值由节能率反推。两类参考来源不同，两列必须分别验收。')
    para('数值目标：10%为较严格目标，15%为预设上限。框架重建BFD-GA两列均在15%内；GA正文偏差17.29%超限。框架排序虽恢复GGA低于GA、BFD低于FFD，但GA低于BFD，原文完整排名仍未恢复。')
    page('迁移代价与实际服务量');image('service_cost',maxheight=220)
    para('源CPU复制开销和目标10%复制CPU已进入实际功率；源任务只处理一次，窗口前进度已扣除。源/目标端均占资源，按事件边界积分。CPU需求未满足比例包含超配和迁移性能影响；kWh/十亿完成MI用于避免把少做任务误判为节能，但不等于已验证相同SLA或等工作量时长。')
    table([['算法','框架能耗kWh','未满足CPU%','迁移次数均值','kWh/十亿MI']]+[[m,f"{summary['framework'][m]['mean_kwh']:.3f}",f"{summary['framework'][m]['shortage_pct']:.3f}",f"{summary['framework'][m]['migrations']:.1f}",f"{summary['framework'][m]['kwh_per_billion_mi']:.3f}"] for m in METHODS],[90,150,150,170,182])
    page('稳健性与GA/GGA配对统计');image('robustness',maxheight=270)
    table([['方案','GA-GGA均值kWh','95%区间','GGA胜出/30']]+[[v['case'],f"{v['ga_minus_gga_kwh']:.3f}",f"[{v['ci95_low']:.3f}, {v['ci95_high']:.3f}]",v['gga_wins']] for v in paired],[195,170,210,167])
    para('统计单位为种子重复和不同日期，不把288个相关采样当独立样本。正差值支持GGA低于GA；95%区间使用30个配对种子t(29)=2.045。十天部分日期节能率为负，须保留，不能据首日排名宣称所有输入成立。')
    for num,note in [(25,'电价不变时费用与能耗成正比。按表2-1权重计算属于条件加权；未指定国家电费基数，避免把缺少依据的绝对金额作为验证。此条件下相对GA/GGA的加权降幅未恢复，不能认定原图所有成本优势已经复现。'),(26,'成功定义为相对60代BFD-GA已知可行参考总功率≤1%且5种子成功率≥80%。这是明确重建标准，不是作者未公开的收敛定义；有限网格最大288，不代表算法理论上限。本次网格曲线较平，支持相对求解规模差异，但未恢复原图随迭代增长的曲线，不能据此宣称原收敛曲线重现。')]:
        page(f'图2-{num}：成本与计算性能');image(f'figure_2-{num}');para(note)
    page('最终验收与复跑')
    para('模块实现验收：映射、真实CPU、UPS输出、独立损耗、迁移生命周期、工作量、24h覆盖和积分通过。框架重建支持主要节能机制和首日GA/GGA排序；文字最小基线与部分日期/高负载的次级排名仍不一致。科学限制与实现BUG分开记录。')
    para('原作者数据无法取得：使用完整公开替代数据并保留种子/样本来源。资源、UPS拟合参数、在线目的节点与轻载撤离没有作者源码，因此不能宣称恢复唯一作者实现。论文表2-6与图2-17、图2-24与正文能耗矛盾继续分别列示。')
    para('复跑：powershell -ExecutionPolicy Bypass -File run_paper_alignment.ps1。仅检查现有结果：同命令添加 -VerifyOnly；完整公开数据校验添加 -VerifyDataset。参数修改在paper_alignment/config，Java实际读取；所有新结果位于paper_alignment/results。')
    para('来源：本地博士论文第二章2.4-2.6及用户截图；CloudSim 3.0.3官方PowerDatacenter、MigrationAbstract和TimeSharedOverSubscription源码；beloglazov/planetlab-workload-traces固定提交344ffdbf7e528bfa6f276014e889e68a0cb640c2。详见实施计划、逐阶段审计及源/输入哈希清单。')
    path=R/'report/论文一致性修正报告.pdf'
    def footer(c,d):c.setFont('Chinese',8);c.drawString(45,22,'论文一致性修正 | 原始公开轨迹 | 模型与控制口径分别验收');c.drawRightString(795,22,str(d.page))
    SimpleDocTemplate(str(path),pagesize=landscape(A4),leftMargin=45,rightMargin=45,topMargin=35,bottomMargin=38).build(story,onFirstPage=footer,onLaterPages=footer)
    render=R/'audit/render';render.mkdir(exist_ok=True);pdf=pymupdf.open(path)
    for i,page in enumerate(pdf):page.get_pixmap(matrix=pymupdf.Matrix(1.2,1.2)).save(render/f'page_{i+1:02}.png')
    print('PDF pages',len(pdf))
if __name__=='__main__':main()
