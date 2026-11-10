"""Chinese PDF report, render validation, and browsable artifact index."""
from pathlib import Path
import json, csv, html, hashlib
import numpy as np
import pymupdf
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT=Path(__file__).resolve().parents[1]
S=json.loads((ROOT/'comparison/summary.json').read_text(encoding='utf-8'))
P=json.loads((ROOT/'config/parameters.json').read_text(encoding='utf-8'))
FONT=Path('C:/Windows/Fonts/simhei.ttf')
pdfmetrics.registerFont(TTFont('Chinese',str(FONT)))
styles={
 'title':ParagraphStyle('title',fontName='Chinese',fontSize=23,leading=31,textColor=colors.HexColor('#173449'),spaceAfter=18),
 'heading':ParagraphStyle('heading',fontName='Chinese',fontSize=16,leading=23,textColor=colors.HexColor('#21536d'),spaceAfter=12),
 'body':ParagraphStyle('body',fontName='Chinese',fontSize=10.5,leading=17,spaceAfter=9),
 'small':ParagraphStyle('small',fontName='Chinese',fontSize=8.5,leading=13,spaceAfter=7),
 'cell':ParagraphStyle('cell',fontName='Chinese',fontSize=9,leading=13),
}
story=[]
def para(text,style='body'):
    story.append(Paragraph(text,styles[style]))
def table(rows,widths):
    cells=[[Paragraph(html.escape(str(v)),styles['cell']) for v in row] for row in rows]
    item=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
    item.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e2edf3')),
         ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f6f8fa')]),
         ('LINEBELOW',(0,0),(-1,0),.8,colors.HexColor('#9bb6c5')),('VALIGN',(0,0),(-1,-1),'TOP'),
         ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
         ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    story.append(item); story.append(Spacer(1,12))
def page(title):
    if story: story.append(PageBreak())
    para(title,'heading')
def img(path,width=746):
    image=Image(str(path))
    original_width,original_height=image.imageWidth,image.imageHeight
    image.drawWidth=width; image.drawHeight=width*original_height/original_width
    story.append(image)

para('第二章 CloudSim 复现与逐图评估','title')
para('数据中心供电-负载协同优化运行技术研究 / 叶桂森<br/>交付日期：2026-10-12 | 传统 CloudSim 3.0.3 + Java 8','heading')
para('已完成可运行模型、五种放置方法、700组静态CloudSim运行、25组24 h动态运行、540组收敛基准和81组敏感性工况，并对图2-15至图2-26逐图对照。')
para('<b>结论：模型与约束验证通过；现有信息支持机制复现，不能声称论文数值精确复现。</b>原作者数据、完整代码及若干参数未提供，且论文内存在公式/参数/图文矛盾。动态节能排序及184.98 kWh未重现。')
table([['交付项','状态与证据'],['式2-1/2-2/2-3/2-4及2-10至2-17','已实现；公式映射在第2页及说明/公式与参数.md'],
       ['真实CloudSim执行','实际Host、VM、Cloudlet、Broker、VmAllocationPolicy；读已分配MIPS核验CPU'],
       ['五种算法','FFD、BFD、GA、GGA、BFD-GA；GGA及动态增量算子有明确实现假设'],
       ['12张图','figures/原生PNG+SVG；comparison/原图-复现对照PNG'],
       ['模型验证误差',f'全部CPU最大绝对误差 {S["largest_cpu_error"]:.3g}，功率误差断言<1e-5 W'],
       ['复现可信范围','同一模型下算法机制比较；绝对数字受公开替代数据和未给参数影响']], [170,576])
para('原论文PDF SHA256：'+P['source_pdf_sha256'],'small')
para('阅读范围：PDF第30-61页，即印刷页21-52。原图证据位于evidence；未覆盖或改动原论文。','small')

page('公式实现：明确单位、状态及约束')
table([['原公式','代码落实（功率W，时间秒，能量kWh）'],
 ['(2-1)、(2-12)','服务器开启：P_i=P_idle+(P_max-P_idle)×sum(w_j)；主实验218.3 W / 350 W。无VM的休眠主机0 W。'],
 ['(2-2)、(2-14)','P_loss=P_UPS×[a0×(P_o/P_UPS)^2+a1×(P_o/P_UPS)+a2]；a0为二次、a1为一次、a2为空载。'],
 ['(2-3)、(2-13)','eta=P_o/(P_o+P_loss)。P_o=0时eta=0。'],
 ['(2-4)、(2-15)','机架总输入功率=sum(P_i)/eta=P_o+P_loss。零负载用加法形式，保留已通电UPS的空载损耗。'],
 ['(2-10)','优化目标为所有机架服务器+UPS总输入功率之和最小。'],
 ['(2-11)','保持VM资源需求总和；额外验证每个VM唯一映射，避免仅总和相等却遗漏/重复VM。'],
 ['(2-16)','每台主机sum(w_j)<=1；动态迁移使用0.9阈值。'],
 ['(2-17)','每机架服务器功率之和<=UPS可用输出容量；冗余装机容量不作为额外可用负载。']], [160,586])
para('<b>冗余扩展为假设：</b>N+1采用N=4且所有5模块均分输出，装机/可用容量比1.25；2N两路均分，装机/可用比2。并联相同模块汇总后仍为二次公式，只将系数的额定基数改为总装机容量。未仿真故障或电池充放电。')
para('<b>硬矛盾：</b>表2-6的a2=0.0617、额定2 kW，UPS空载损耗已为123.4 W；图2-17全曲线约67-73 W。900 W输出得164.9305 W；互换a0/a2仍得104.9585 W。保持原式原表作为验证，不能通过无依据调参消除差异。')

page('仿真平台、案例、参数与公平比较')
table([['项目','论文已给','本次落实 / 假设'],
 ['规模','100台同构服务器、5机架、每架20台','主实验一致；静态100 VM为假设，动态100 VM为原文'],
 ['服务器功率','218.3 W空载，350 W满载','线性；有VM但当前CPU为0仍算开启'],
 ['CPU/MIPS与非CPU资源','未给VM/Host MIPS、RAM/BW/Storage','VM与Host均2500 MIPS；1 vCPU；非CPU资源给足，不额外约束'],
 ['UPS额定与冗余','未给主实验额定、N+1中的N、均分/热备模式','可用7 kW（20×350 W）；N=4均分；2N均分'],
 ['AC/DC系数','图2-5给效率/损耗曲线，表2-6仅验证案例一组系数','AC(0.0376,0.0069,0.0319)，DC(0.0549,0.0077,0.0207)为图形近似重建，非作者精确参数'],
 ['数据','PlanetLab历史CPU；动态平均25%','20110303抽100条，seed=42；288点×300s；单调odds变换均值25%'],
 ['GA预算','未给数值','种群40，60代，交叉0.8，变异0.05，精英1，5种子'],
 ['动态迁移','超过90%随机选VM迁移','反复随机移出至90%内，只重放这些VM；其余固定；瞬时迁移，无能耗附加项']], [120,247,379])
para('算法：FFD/BFD按CPU需求降序；GA编码VM→主机，目标服务器功率；GGA整组交叉、冲突移除、BFD重插和整组变异，目标服务器功率；BFD-GA先BFD组内放置，再编码服务器组→机架，目标总功率。第二步保存原BFD方案为精英候选，静态不会劣于该方案。')
para('动态增量阶段：GA/GGA在固定其余VM时搜索迁移VM的主机映射；BFD-GA沿用供电感知目标。该增量扩展不等同于作者未公开的动态源码，也不等同于每采样全局重新合并。仅过载迁移可能累积轻载主机，解释能耗偏大，但不证明其是唯一原因。','small')

page('定量结果与复现限制')
table([['架构','本次最大下降%','本次加权%','正文报告值%','正文加权%','加权差/百分点']]+[
 [r['architecture'],f"{r['reproduced_max_pct']:.3f}",f"{r['reproduced_weighted_pct']:.3f}",f"{r['thesis_reported_pct']:.2f}",f"{r['thesis_weighted_pct']:.2f}",f"{r['weighted_error_pp']:+.3f}"] for r in S['static']], [110,130,130,130,120,126])
para('相对BFD的服务器+UPS总功率下降；按表2-1权重1%、22%、38%、26%、10%、2%、1%加权。正文2.09%/2.47%等数值未明确对应负载点，不能直接视为原图最高值。')
table([['动态算法','本次均值 kWh','种子标准差','原文/正文反推 kWh','相对偏差%']]+[
 [r['method'],f"{r['mean_kwh']:.3f}",f"{r['sd_kwh']:.3f}",f"{r['thesis_kwh']:.3f}",f"{r['relative_error_pct']:+.1f}"] for r in S['dynamic']], [120,150,140,190,146])
para('<b>动态并未重现：</b>在VM和Host同MIPS假设下，100 VM平均CPU25%意味着平均需求25台主机容量。服务器功率下界为350×25=8750 W，24 h至少210 kWh，尚未计UPS。因此184.98 kWh在这一容量比例下不可能；论文缺少VM/Host MIPS比例，不能从25%直接确定物理负载。')
para('原图2-24的BFD-GA曲线约6.4 kW，与正文184.98 kWh/24 h=7.71 kW量级也不一致。精确复现需要作者原始曲线/数据和在线策略。图2-23直流高柱可能是UPS单独损耗分母，而正文为总功率；此解释是推断。','small')

for num in range(15,27):
    info=S['figures'][str(num)]; page(f'图 2-{num} 对照 | {info["title"]}')
    img(ROOT/'comparison'/f'comparison_2-{num}.png')
    para(info['note'],'body')
    para('数据：results/中的Java实测CSV；复现原生矢量图：figures/reproduced_2-'+str(num)+'.svg。原图用于对照，未被修改。','small')

page('敏感性、统计口径与后续精确复现入口')
with (ROOT/'results/sensitivity.csv').open(encoding='utf-8') as f: sensitivity=list(csv.DictReader(f))
rows=[['参数变化','相对BFD总功率下降率范围','解读']]
for source in ['table2-6','figure2-5AC','figure2-5DC']:
    values=[float(r['reduction_pct']) for r in sensitivity if r['coefficient_source']==source]
    rows.append([source,f'{min(values):.3f}% - {max(values):.3f}%', '可用容量7/10/14 kW；冗余因子1/1.25/2；负载20/30/50%'])
table(rows,[150,220,376])
para('相同可用容量下，增加冗余装机容量会提高空载损耗、降低二次项的负载敏感性；服务器功率保持不变。对算法节能百分比影响显著，故主实验UPS容量和冗余方式不能省略。')
para('统计：静态功率为5种子均值，误差棒为标准差。动态曲线均值，区间为t(4)=2.776的均值95%区间。年成本为时间加权下降率×假设80亿美元基数，不代表当前美国统计。收敛最大规模为有限测试网格成功上限，不代表可解问题的理论上限。')
para('可替换入口：data/dynamic.csv（100×288）、data/static.csv（7×100）；PowerModels.java的UPS/主机常量；Placement.java的遗传参数；Simulation.java的MIPS/采样和增量迁移；Experiments.java的种子、工况和成功判据。config/parameters.json为来源清单，不是Java自动读取配置。')
para('需要补齐：原作者PlanetLab日期/编号及缩放、VM与主机资源参数、主实验UPS系数/容量/N、GA和GGA完整算子及参数、动态合并/迁移时延策略、成本基数与口径、图2-26成功/收敛判据，以及表2-6/图2-17和图2-23/正文的勘误。')

page('运行、审计与产物导航')
para('已有数据和依赖可离线重跑：在输出目录运行 powershell -ExecutionPolicy Bypass -File run.ps1。只更新图和报告：追加 -SkipExperiments。build.ps1使用本机Java8路径，缺失时回退到PATH。Python使用已定位Codex运行时。')
table([['路径','用途'],['src/repro/ + lib/ + build.ps1','完整Java源码、传统CloudSim及commons-math依赖、编译入口'],
 ['run.ps1 + requirements.txt','一键运行与Python依赖清单'],['data/ + config/parameters.json','原轨迹、固定版本及文件哈希、处理后输入、参数来源'],
 ['results/','静态/动态/收敛/敏感性CSV、逐主机/机架测量、VM放置、任务状态'],
 ['figures/ + comparison/','12张PNG/SVG复现图、12张左右对照、数值汇总'],
 ['evidence/ + 说明/','论文摘录与原图、公式和参数追溯'],['audit/','阶段审计记录及修复情况']], [260,486])
para('审计结论：五阶段均按九维度检查。已修复手算测试预期、零机架维度检查、在线Cloudlet负执行时间/零进度导出、逐机架UPS仿真证据输出。最终构建与运行断言通过，无未修复的代码审计问题。论文数据和定义缺口属于复现限制，不能用代码审计通过代替论文数值验证。')
para('外部来源：<link href="https://github.com/Cloudslab/cloudsim">CloudSim官方源码</link>；<link href="https://github.com/cloudsimplus/planetlab-workload-traces">PlanetLab公开数据仓库</link>；<link href="https://www.macs.hw.ac.uk/~dwcorne/Teaching/falkenauer96hybrid.pdf">Falkenauer分组遗传算法原始论文</link>。GGA实现采用分组原则，未声称完整复刻HGGA局部支配优化。','small')

def footer(canvas,doc):
    canvas.setFont('Chinese',8); canvas.setFillColor(colors.HexColor('#637684'))
    canvas.drawString(46,25,'第二章复现 | CloudSim 3.0.3 | 公开替代输入与假设均已标注')
    canvas.drawRightString(796,25,str(doc.page))
doc=SimpleDocTemplate(str(ROOT/'复现报告.pdf'),pagesize=landscape(A4),rightMargin=46,leftMargin=46,
                      topMargin=37,bottomMargin=43,title='第二章CloudSim复现与逐图评估',author='CloudSim reproduction')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
pdf=pymupdf.open(ROOT/'复现报告.pdf')
review=ROOT/'audit/report_render'; review.mkdir(exist_ok=True)
for i,p in enumerate(pdf): p.get_pixmap(matrix=pymupdf.Matrix(1.4,1.4)).save(review/f'page_{i+1:02d}.png')
print(f'PDF generated and rendered: {len(pdf)} pages')
# Browsable local index; all references stay inside the authorized output folder.
links=''.join(f'<article><h2>图2-{n} {html.escape(S["figures"][str(n)]["title"])}</h2><img src="comparison/comparison_2-{n}.png"><p>{html.escape(S["figures"][str(n)]["note"])}</p><a href="figures/reproduced_2-{n}.svg">原生SVG</a></article>' for n in range(15,27))
(ROOT/'comparison/index.html').write_text('<!doctype html><meta charset="utf-8"><title>第二章复现对照</title><style>body{max-width:1200px;margin:40px auto;font:16px/1.7 sans-serif;color:#173449;background:#f4f7fa}article{padding:24px;background:white;margin:25px 0;border-radius:12px}img{width:100%}a{color:#236a90}</style><h1>第二章 CloudSim 复现对照</h1><p>模型验证通过；公开替代数据未实现论文数值精确复现。<a href="../复现报告.pdf">打开报告</a></p>'+links.replace('src="comparison/','src="').replace('href="figures/','href="../figures/'),encoding='utf-8')
manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['src','data','config','lib','results','figures','comparison','说明','tools'] for p in (ROOT/folder).rglob('*') if p.is_file()}
for name in ['README.md','build.ps1','run.ps1','requirements.txt','复现报告.pdf']:
    manifest[name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
(ROOT/'audit/deliverable_hashes.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
