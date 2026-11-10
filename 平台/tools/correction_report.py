"""Measured correction report. Reference digitization is never a simulator input."""
from pathlib import Path
import csv,json,html,hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image as PILImage
import pymupdf
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,PageBreak,Image,Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4,landscape
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT=Path(__file__).resolve().parents[1];COR=ROOT/'correction'
for d in ['figures','comparison','audit/render']: (COR/d).mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'font.family':'Microsoft YaHei','font.size':10,'axes.unicode_minus':False,
                     'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':180})
METHODS=['FFD','BFD','GA','GGA','BFD-GA'];COLORS=['#273ba4','#75a933','#cf75a9','#c5ad20','#bd3d33']
def read(name,old=False):
    with ((ROOT if old else COR)/'results'/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(name,rows):
    with (COR/'comparison'/name).open('w',encoding='utf-8-sig',newline='') as f:
        out=csv.DictWriter(f,fieldnames=list(rows[0]));out.writeheader();out.writerows(rows)
def save(fig,name):
    fig.tight_layout();fig.savefig(COR/'figures'/f'{name}.png');fig.savefig(COR/'figures'/f'{name}.svg');plt.close(fig)
def style(ax,y='功率 / W'):
    ax.set_xlabel('时间 / h');ax.set_ylabel(y);ax.set_xlim(0,24);ax.set_xticks(np.arange(0,25,4));ax.grid(axis='y',alpha=.25)
def measured(prefix,method,seed=101):return read(f'{prefix}_{method}_{seed}_times.csv')
dynamic,stable,static=read('dynamic_summary.csv'),read('stable_summary.csv'),read('static_summary.csv')
assert (len(dynamic),len(stable),len(static))==(126,25,700)
assert max(float(r['cpu_error']) for r in dynamic+stable+static)<1e-8
assert max(float(r['power_error_w']) for r in dynamic+stable+static)<1e-5
data=json.loads((COR/'config/data_manifest.json').read_text(encoding='utf-8'))
publisher=json.loads((ROOT/'data/public/planetlab_complete/manifest.json').read_text(encoding='utf-8'))
main={};times=np.arange(288)/12
fig,ax=plt.subplots(figsize=(11,5.3))
for method,color in zip(METHODS,COLORS):
    rows=measured('stable_main',method);assert len(rows)==288 and [int(x['time_s']) for x in rows]==list(range(0,86400,300))
    watts=np.array([float(x['total_w']) for x in rows]);ax.plot(times,watts,label=method,color=color,lw=1,
            linestyle='--' if method=='BFD' else '-')
    summary=[r for r in stable if r['method']==method];energies=np.array([float(r['total_kwh']) for r in summary])
    assert abs(watts.sum()*300/3600000-float(summary[0]['total_kwh']))<1e-6
    main[method]={'mean_kwh':float(energies.mean()),'sd_kwh':float(energies.std(ddof=1)),
                  'mean_w':float(energies.mean()*1000/24),'migrations_mean':float(np.mean([int(r['migrations']) for r in summary]))}
ax.legend(ncol=5,fontsize=9,loc='upper right');style(ax);ax.set_ylim(5500,8000)
ax.set_title('图2-24 修正：未经缩放的原始轨迹，单次运行 seed101',fontweight='bold')
fig.text(.5,.012,'20110303 / 100 VM / 原VM平均CPU 25% / 同一稳定周期控制；FFD与BFD功率重合',ha='center',fontsize=9)
fig.subplots_adjust(bottom=.16);save(fig,'figure_2-24_corrected')
fig,axes=plt.subplots(1,2,figsize=(16,7))
for ax,path,title in zip(axes,[ROOT/'evidence/original_2-24.png',COR/'figures/figure_2-24_corrected.png'],['论文原图','修正后的真实 CloudSim 回放']):
    ax.imshow(PILImage.open(path));ax.axis('off');ax.set_title(title,fontsize=15)
fig.suptitle('图2-24 原图与修正结果',fontsize=18,fontweight='bold')
fig.text(.5,.025,'没有平移时间、缩放功率、平滑轨迹或搜索最贴图种子；未知原轨迹不要求逐点重合。',ha='center',fontsize=11)
save(fig,'figure_2-24_comparison')

# Approximate digitization: axes calibrated at x205..1181, y64=8000W, y455=6000W.
pixels=np.array(PILImage.open(ROOT/'evidence/original_2-24.png').convert('RGB')).astype(float)
r,g,b=np.moveaxis(pixels,2,0)
masks={'BFD-GA':(r>150)&(g<145)&(b<145)&(r>1.5*g)&(r>1.5*b)&(abs(g-b)<30)&(r-b>70)&(r-g>70),
 'GA':(r>170)&(b>130)&(g<190)&(r-g>40)&(b-g>25),
 'FFD':(b>100)&(r<145)&(g<160)&(b>1.25*r)&(b>1.1*g),
 'BFD':(g>100)&(r<180)&(b<160)&(g>1.1*r)&(g>1.2*b),
 'GGA':(r>155)&(g>155)&(b<145)&(r>1.4*b)&(g>1.4*b)}
reference,digitized={},[]
for method in METHODS:
    values=[];counts=[]
    for t in times:
        x=int(round(205+t/24*976));yy=np.where(masks[method][180:450,max(205,x-1):min(1182,x+2)])[0]+180
        values.append(6000+(455-np.median(yy))*2000/391 if len(yy) else np.nan);counts.append(len(yy))
    values=np.array(values);good=np.flatnonzero(np.isfinite(values));assert len(good)>144
    filled=np.interp(np.arange(288),good,values[good]);reference[method]=filled
    for i,t in enumerate(times):digitized.append({'method':method,'time_h':t,'estimated_power_w':filled[i],
       'observed_color_pixels':counts[i],'interpolated':not bool(counts[i]),'status':'coarse image estimate, not author raw data or simulation input'})
write('figure24_reference_digitized.csv',digitized)
comparisons=[];stated={'BFD-GA':184.98,'FFD':184.98/.9768,'BFD':184.98/.9799,'GA':184.98/.932,'GGA':184.98/.9666}
for method in METHODS:
    estimated=float(reference[method].mean()*24/1000)
    comparisons.append({'method':method,'corrected_mean_kwh':main[method]['mean_kwh'],'corrected_sd_kwh':main[method]['sd_kwh'],
       'reference_image_estimated_kwh':estimated,'image_reading_uncertainty_kwh':1.5,'thesis_text_kwh':stated[method],
       'relative_to_image_pct':100*(main[method]['mean_kwh']/estimated-1),'relative_to_text_pct':100*(main[method]['mean_kwh']/stated[method]-1)})
write('figure24_energy_comparison.csv',comparisons)
fig,ax=plt.subplots(figsize=(11,4.8));ax.plot(times,reference['BFD-GA'],'--',color='#647885',label='原图粗数字化估读（非原始数据）')
ax.plot(times,[float(x['total_w']) for x in measured('stable_main','BFD-GA')],color=COLORS[-1],label='修正后的独立原始轨迹回放')
style(ax);ax.legend(fontsize=9);ax.set_title('BFD-GA：原图参考与新公开数据（不进行波形对齐）');save(fig,'reference_overlay')

ablation=[r for r in dynamic if r['case'].startswith('ablation')]+[r for r in stable if r['method']=='BFD-GA' and r['seed']=='101']
write('ablation_summary.csv',ablation)
labels=['旧变换/同MIPS/过载','同100原始/同MIPS/过载','同100原始/异构/过载','同100原始/异构/周期',
        '25%原始组/同MIPS/周期','25%原始组/异构/过载','25%原始组/异构/稳定周期']
fig,ax=plt.subplots(figsize=(12,5.5));ax.barh(labels,[float(x['total_kwh']) for x in ablation],color=['#bf5653']+['#5293ae']*5+['#34795a'])
for i,x in enumerate(ablation):ax.text(float(x['total_kwh'])+3,i,f'{float(x["total_kwh"]):.2f}',va='center',fontsize=9)
ax.invert_yaxis();ax.set_xlabel('24 h 服务器+UPS能量 / kWh');ax.set_xlim(0,410);ax.grid(axis='x',alpha=.25)
ax.set_title('BFD-GA 消融：按相邻受控因素解释，不能跨不同工作量直接归因');save(fig,'ablation_energy')
fig,ax=plt.subplots(figsize=(11,4.8))
for prefix,label,color in [('ablation_v1','旧变换数据/同MIPS/仅过载','#bc4e4b'),
                         ('ablation_cohort25_overload','同25%原始组/异构/仅过载','#d39336'),
                         ('stable_main','同25%原始组/异构/稳定周期','#34795a')]:
    ax.plot(times,[int(x['active_hosts']) for x in measured(prefix,'BFD-GA')],label=label,color=color)
style(ax,'开机主机数');ax.legend(fontsize=9);ax.set_title('调度碎片：只过载迁移与回收空主机的区别');save(fig,'active_hosts_diagnosis')
migration=[]
for method in METHODS:
    old=np.mean([int(x['migrations']) for x in dynamic if x['case']=='main' and x['method']==method]);new=main[method]['migrations_mean']
    migration.append({'method':method,'periodic_migrations_mean':old,'stable_migrations_mean':new,'reduction_pct':100*(old-new)/old})
write('migration_stability.csv',migration)
fig,ax=plt.subplots(figsize=(10,4.8));x=np.arange(5)
ax.bar(x-.18,[m['periodic_migrations_mean'] for m in migration],.36,label='周期重排',color='#a5b8c4')
ax.bar(x+.18,[m['stable_migrations_mean'] for m in migration],.36,label='稳定化周期重排',color='#467e91')
ax.set_xticks(x,METHODS);ax.set_ylabel('24 h 实际VM迁移次数');ax.legend();ax.grid(axis='y',alpha=.25);ax.set_title('稳定化减少等价映射迁移，但迁移次数仍高');save(fig,'migration_counts')
days=list(publisher['counts']);robust=[];fig,ax=plt.subplots(figsize=(11,4.8))
for cohort,color in [('random','#547b9e'),('cohort25','#bf5856')]:
    saving=[]
    for day in days:
        case='main' if cohort=='cohort25' and day=='20110303' else f'{cohort}_{day}'
        select=[z for z in dynamic if z['case']==case and z['seed']=='101']
        energy={z['method']:float(z['total_kwh']) for z in select};pct=100*(energy['BFD']-energy['BFD-GA'])/energy['BFD']
        saving.append(pct);robust.append({'date':day,'cohort':cohort,'bfd_kwh':energy['BFD'],'bfd_ga_kwh':energy['BFD-GA'],'saving_pct':pct})
    ax.plot(np.arange(10),saving,'o-',label=cohort+'：100VM原始轨迹',color=color)
ax.set_xticks(np.arange(10),[d[4:6]+'/'+d[6:] for d in days]);ax.set_xlabel('2011年数据日期');ax.set_ylabel('相对BFD总能量降低 / %');ax.legend();ax.grid(axis='y',alpha=.25)
ax.set_title('完整十日发布的跨日期验证：未选择最接近原图的日期');save(fig,'ten_day_robustness');write('ten_day_robustness.csv',robust)
for num,arch in [(18,'N+1AC'),(19,'N+1DC'),(21,'2NAC'),(22,'2NDC')]:
    fig,ax=plt.subplots(figsize=(11,5));x=np.arange(7);width=.15
    for k,method in enumerate(METHODS):
        selected=[z for z in static if z['architecture']==arch and z['method']==method]
        s=np.array([np.mean([float(z['server_w']) for z in selected if abs(float(z['target_host_load'])-l/100)<1e-6]) for l in range(10,71,10)])
        u=np.array([np.mean([float(z['ups_loss_w']) for z in selected if abs(float(z['target_host_load'])-l/100)<1e-6]) for l in range(10,71,10)])
        ax.bar(x+(k-2)*width,s,width,color='#67a7c5',hatch=['xx','..','///','\\\\',''][k],edgecolor='#37607a',lw=.3)
        ax.bar(x+(k-2)*width,u,width,bottom=s,label=method,color='#e8a24e',edgecolor='#9c7246',lw=.3)
    ax.set_xticks(x,[str(l)+'%' for l in range(10,71,10)]);ax.legend(ncol=5,fontsize=8);ax.set_ylabel('服务器(蓝)+UPS(橙) / W')
    ax.set_xlabel('100台物理主机总需求档位；通过VM数量178-1004控制，非VM平均CPU');ax.set_title(f'图2-{num} 补充：{arch} 未变换真实快照（工况口径已改变）');save(fig,f'raw_static_2-{num}')

summary={'dataset':{'commit':publisher['commit'],'traces':11746,'samples':3382848},'main':main,'energy_comparison':comparisons,
         'ablation':ablation,'migration':migration,'robustness':robust,'cpu_max_error':max(float(z['cpu_error']) for z in dynamic+stable+static)}
(COR/'comparison/summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
pdfmetrics.registerFont(TTFont('Chinese','C:/Windows/Fonts/simhei.ttf'))
styles={k:ParagraphStyle(k,fontName='Chinese',fontSize=s,leading=s*1.5,spaceAfter=9,textColor=colors.HexColor('#203d50')) for k,s in [('title',22),('head',16),('body',10.5),('cell',9),('small',8.5)]}
story=[]
def p(text,style='body'):story.append(Paragraph(text,styles[style]))
def page(title):
    if story:story.append(PageBreak())
    p(title,'head')
def table(rows,widths):
    item=Table([[Paragraph(html.escape(str(v)),styles['cell']) for v in row] for row in rows],colWidths=widths,repeatRows=1)
    item.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e3edf3')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f6f8fa')]),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    story.extend([item,Spacer(1,12)])
def image(name,width=746):
    im=Image(str(COR/'figures'/f'{name}.png'));w,h=im.imageWidth,im.imageHeight;im.drawWidth=width;im.drawHeight=width*h/w;story.append(im)
p('复现异常诊断与修正','title');p('完整权威 PlanetLab 发布数据 / 图2-24专项 / 2026-10-12','head')
p('完成原发布者十日整库下载、11746条VM日轨迹/3382848点完整性核验；运行151组动态及700组未变换真实快照静态实验。旧结果、旧报告及原图保持可追溯，修正结果单独存放。')
p('<b>修正结论：</b>旧图上升异常由非线性输入变换、未经依据的同MIPS假设和只过载迁移的碎片累积共同造成；旧在线BFD-GA不完整。修正数据处理、资源单位和完整两步重排后，BFD-GA平均功率约'+f'{main["BFD-GA"]["mean_w"]:.1f}'+' W，开机主机15-19台随负载变化，不再从28台累积到53台。')
table([['状态','明确结论'],['已修复实现问题','原数据不变换；VM百分比×VM MIPS/Host MIPS；90%触发与100%容量分开；周期完整五算法；实际分配/积分校验'],['机制结果','主案例BFD-GA相对BFD约2.29%节能；对照图回到原图功率量级，仍保留原始波动'],['仍不能确定','未知原论文数据日期/ID与设备参数；原图积分约155kWh与正文184.98kWh不同；GA/GGA节能幅度未精确重现'],['迁移限制','稳定化减少等价迁移约15.8%，但仍约20578次/天；瞬时迁移且未计附加损耗，不直接视为生产策略']], [180,566])
p('不以外观接近作为精确复现证据；没有拟合论文功率曲线、调整时间、平滑原数据或搜索最贴图种子。','small')
page('原因、证据和修正方案')
table([['原因','可验证证据','修正'],['上一版非线性变换','同100VM原均值11.886%，被odds变换到25%；峰值人为压到约85%。','原始0-100整数只除100；按VM日均值选择25%组，另报告随机组。'],['同MIPS无原文依据','原版100VM×25%相当于25台主机需求；服务器能量下界210kWh。','用官方VM类型作参考情景，真实MIPS请求核验；同MIPS保留消融，不假称作者硬件。'],['只过载迁移导致碎片','旧版28->53台；同一新25%组17->30台。','五算法共同300秒完整重新优化，回收空主机；明确这是控制层补充假设。'],['在线BFD-GA退化','旧insert以迁移VM的主机号为基因，没有第二步服务器组->机架编码。','每次完整BFD组内放置，再按服务器组->机架GA；稳定化处理等价编号。'],['原文参数/图文不一致','表2-6损耗下限123.4W，图2-17约70W；图2-24积分和正文也不同。','保持公式；将原表、图估读及仿真分开报告，需要作者勘误/参数才能精确恢复。']], [155,290,301])
p('负载25%必须说明相对于VM还是Host。修正主案例原VM平均25%，但按所采用VM MIPS类型计算，平均总主机需求约14.441台容量（100台主机的14.441%）；不能仍按25台主机计算。')
page('完整数据来源与使用范围')
table([['日期','VM日文件数','全日期原VM平均CPU%','原始25%组均值%']]+[[d,publisher['counts'][d],f"{next(x['mean_cpu'] for x in data['daily_statistics'] if x['date']==d)*100:.3f}",f"{next(x['mean_vm_cpu'] for x in data['selections'] if x['date']==d and x['kind']=='cohort25')*100:.3f}"] for d in days], [130,130,250,236])
p('原发布者：<link href="https://github.com/beloglazov/planetlab-workload-traces">Anton Beloglazov / PlanetLab workload traces</link>；采集背景为Princeton CoMon。固定Git commit：'+publisher['commit']+'。整库ZIP、Git树、逐文件Git blob SHA1/SHA256及文件数均核验。')
p('完整的是作者公开的十日实验发布，非全球PlanetLab全部历史。完整原文件位于data/public/planetlab_complete/raw；发布数据只有CPU百分比，没有论文UPS参数、VM MIPS及迁移耗时。模拟用100VM以匹配论文动态规模，各日随机组与25%条件组的全部原文件名存于清单。','small')
page('参数、控制器和比较口径')
table([['参数','落实与边界'],['服务器/机架','100同构Host，5机架；218.3/350 W；Host单PE2500 MIPS为保留的假设。'],['VM MIPS','2500/2000/1000/500，源于CloudSim3.0.3官方power/Constants.java。仅借用VM类型；不是完整照搬其异构双核Host设置，也不是论文已知设置。'],['UPS','N+1DC，可用7 kW、装机因子1.25；a0/a1/a2=0.0549/0.0077/0.0207是前版图2-5近似重建，仍有不确定度。'],['算法与预算','FFD/BFD/GA/GGA/BFD-GA；GA/GGA服务器目标，BFD-GA总功率目标；40种群×60代、交叉0.8、变异0.05。'],['动态控制','每300秒共同调用完整算法；稳定化按同参数UPS对称机架/主机匹配，无目标收益不迁移。触发90%，可行物理上限100%；真实100%单VM不会被裁剪。'],['采样/能量','288×300秒=24h；零阶保持，左矩形积分，W*s/3600000为kWh；每VM一在线Cloudlet；结束状态InExec。'],['物理验证',f'读取实际allocated MIPS；CPU最大误差{summary["cpu_max_error"]:.3g}；功率误差<1e-5W；288点和VM数全部断言。']], [165,581])
p('周期重新优化是合理的补充控制情景，不能由论文一句“过载随机迁移”证明作者也采用它。GA/GGA本实现与未公开作者版本可能不同，因此算法排序和百分比只作独立实验结论。')
page('图2-24：原图与修正结果');image('figure_2-24_comparison')
p('右图为预先选定最早日期20110303、seed101的单次运行，不是五种子的平滑均值。FFD/BFD在此组功率重合，原始波动未移除。完整SVG可独立放大。')
page('修正图2-24原生图');image('figure_2-24_corrected')
p('功率5955-7522 W之间的变化来自公开原始轨迹。它仍不可能与未知的作者100条轨迹逐点相同；当前修正针对量纲、调度机制及功率量级，而不是重构未知随机波形。','small')
page('定量比较：原图估读与正文分开')
table([['算法','修正均值kWh','原图估读kWh','正文kWh','对图估读差%','对正文差%']]+[[x['method'],f"{x['corrected_mean_kwh']:.3f}",f"{x['reference_image_estimated_kwh']:.2f}",f"{x['thesis_text_kwh']:.3f}",f"{x['relative_to_image_pct']:+.2f}",f"{x['relative_to_text_pct']:+.2f}"] for x in comparisons], [105,125,130,125,130,131])
p('图像粗数字化的坐标标定、颜色阈值、缺失插值标志均保存。±1.5 kWh仅为保守读图容差，不是经作者数据验证的统计置信区间；估读没有作为仿真输入。原图约6.45 kW意味着约155 kWh，而184.98 kWh/24h=7.7075 kW，不能同时要求同一输出曲线满足这两种目标。')
p('当前BFD-GA与FFD/BFD的相对节能约2.29%，与正文2.32%/2.01%在同一量级；对GA/GGA的优势较小，与正文6.8%/3.34%不符。完整原数据、遗传参数和算子缺失时，不应为重现该排序而故意削弱基线算法。')
page('原图估读叠加：不同输入保留不同波形');image('reference_overlay')
p('黑/灰虚线为原图粗数字化，红线为新公开轨迹独立回放。均值接近不能证明作者数据被恢复；峰谷时刻与波动幅度的差异保留，不计算无共同输入依据的逐点复现RMSE。')
page('消融证据：数据、资源和调度分别比较');image('ablation_energy')
p('同25%原始组、同异构VM类型：仅过载221.319 kWh，完整周期156.089 kWh，控制策略差约29.47%。同100原始组：仅过载143.684 kWh，完整周期93.008 kWh。只更换数据仍会累积轻载主机。')
p('旧变换组364.214 kWh与同100原始组212.918 kWh的工作量均值不同，不能把其全部差额解释为算法节能；这是未经依据的数据变换改变实验工况的证据。','small')
page('主机状态与迁移成本边界');image('active_hosts_diagnosis')
p('橙/绿使用同一25%原始组及同一VM资源，区别只有控制器。旧变换/同MIPS红线作为历史异常参照，不能与新工作量直接计算算法下降率。')
page('稳定化对照');image('migration_counts')
p(f'BFD-GA平均迁移从{migration[-1]["periodic_migrations_mean"]:.0f}减到{migration[-1]["stable_migrations_mean"]:.0f}，下降{migration[-1]["reduction_pct"]:.2f}%，能耗不变。主要问题仍是周期全量重排。')
p('实际系统建议增加迁移收益门槛、最短驻留时间和迁移预算，并用RAM/BW确定延迟和测量附加能耗。当前论文无这些参数，本次保留理想瞬时模型及实际迁移计数，不能宣称这一能耗优先情景已证明生产运行最优。')
page('跨日期验证');image('ten_day_robustness')
p('十个日期均已使用，每日两种明确选择规则，同一seed101比较五算法。随机组代表公开释放中一般抽样工况；25%组是条件工况，有选择偏差，不能当作整个数据集均值。稳定化只在主案例额外重复5个种子，其余日期采用相同周期控制参照。')
page('静态真实快照与旧图的区别')
table([['目标物理负载%','实际达到%','VM数','快照时间']]+[[f"{x['target_host_load']*100:.0f}",f"{x['actual_host_load']*100:.3f}",x['vm_count'],f"20110303 / {x['time_s']/3600:.3f} h"] for x in data['static_snapshots']], [160,180,140,266])
p('此次静态完全保留原CPU采样值，以VM数量控制100台主机总物理需求。旧版是固定100VM再改变VM平均CPU，两者不能直接计算“数值复现误差”。新700条结果及图2-18/19/21/22真实快照补充图均输出；旧图12张对照保持作为历史证据。')
p('同理，原文未给的全国电费基数、UPS市场占比等不能从公开CPU数据恢复。本次不把旧版假设成本当作权威数据结论。')
page('UPS异常应怎样修正')
table([['诊断情景','900 W输出、2 kW额定时损耗','结论'],['式2-2 + 表2-6原系数','164.9305 W；空载下限123.4 W','不可能同时匹配图2-17约67-73 W'],['图2-5 DC近似重建系数','约70.5645 W','说明不同系数可以解释图的量级，但不证明作者实际采用了它'],['修正路径','保留二次公式；分别报告原表与图重建情景','需作者勘误、原始UPS效率点或厂家实测曲线，不能默默交换系数或调额定功率']], [210,240,296])
p('UPS公式本身在本平台通过独立计算验证。原表参数与原图一致性是不同问题；下载CPU数据不能消除该矛盾。建议获得实测效率后先由P_loss=P_output×(1/eta-1)换算，再拟合a0/a1/a2并报告残差和负载范围。')
p('其余异常：图2-23必须分别核对UPS损耗与机房总功率的分母；图2-25需明确原年度电费与成本口径，不能用假设全国基数当权威实测；图2-26缺少成功/收敛判据，应报告既定预算的可行率、目标值和耗时，不能强行恢复未知最大规模定义。')
page('复跑、审计与产物定位')
table([['路径','用途'],['data/public/planetlab_complete/','完整作者发布ZIP/raw、Git树、SHA清单'],['correction/config/、inputs/','十日抽样清单、25%条件组、真实快照和假设记录'],['correction/results/','151动态、700静态实测及逐机架、主机、任务CSV'],['correction/figures/、comparison/','修正图2-24、原图估读、消融、迁移和跨日期结论'],['run_correction.ps1','重跑全部修正；-SkipExperiments仅图和报告；-VerifyDataset检验整库'],['correction/audit/','旧源码备份、4阶段九维审计、原图标定、报告渲染及文件哈希']], [300,446])
p('编译、真实CloudSim单100%VM/异构MIPS/机架不变映射/主机回收、原结果回归、完整批量和积分验证通过。四阶段没有未修复代码审计问题。输入选择、VM/Host参数、UPS系数、周期触发及瞬时迁移均有明确状态，仍需作者数据才能声称精确复现。')
p('权威来源：<link href="https://github.com/beloglazov/planetlab-workload-traces">数据原发布者</link>；<link href="https://codeen.cs.princeton.edu/comon/">Princeton CoMon</link>；<link href="https://raw.githubusercontent.com/Cloudslab/cloudsim/cloudsim-3.0.3/modules/cloudsim-examples/src/main/java/org/cloudbus/cloudsim/examples/power/Constants.java">CloudSim 3.0.3 官方参数源文件</link>。','small')
def footer(canvas,doc):
    canvas.setFont('Chinese',8);canvas.setFillColor(colors.HexColor('#687d8b'));canvas.drawString(46,24,'修正诊断 | 原始完整发布数据 | 机制验证与数值吻合分开报告');canvas.drawRightString(795,24,str(doc.page))
document=SimpleDocTemplate(str(COR/'修正诊断报告.pdf'),pagesize=landscape(A4),leftMargin=46,rightMargin=46,topMargin=36,bottomMargin=43,title='复现异常诊断与修正')
document.build(story,onFirstPage=footer,onLaterPages=footer)
pdf=pymupdf.open(COR/'修正诊断报告.pdf')
for i,page in enumerate(pdf):page.get_pixmap(matrix=pymupdf.Matrix(1.4,1.4)).save(COR/'audit/render'/f'page_{i+1:02d}.png')
hashes={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for folder in ['src/repro','correction/inputs','correction/config','correction/results','correction/figures','correction/comparison'] for path in (ROOT/folder).rglob('*') if path.is_file()}
hashes['correction/修正诊断报告.pdf']=hashlib.sha256((COR/'修正诊断报告.pdf').read_bytes()).hexdigest()
(COR/'audit/output_hashes.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'PASS correction report: {len(pdf)} pages; complete dataset, measured five algorithms, independent reference estimates')
