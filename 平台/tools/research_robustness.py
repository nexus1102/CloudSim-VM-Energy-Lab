"""Frozen ten-date plan, auditable Single runs and paired date-level inference."""
import argparse,csv,json,subprocess,shutil,hashlib
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
from collections import defaultdict
import numpy as np
from research_platform_audit import verify,sha,module_loss,bfd,same_groups
from paper_audit import settings,rows,close
from research_statistics import paired_interval

ROOT=Path(__file__).resolve().parents[1]
METHODS=['FFD','BFD','GA','GGA','BFD-GA']
SEEDS=[101,202,303,404,505]

def write_csv(path,data):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)

def check_budget(path,config):
    c=settings(config);raw=np.loadtxt(c['trace.path'],delimiter=',',ndmin=2)
    d=raw[:,0]*np.resize([float(x) for x in c['vm.mips'].split(',')],len(raw))/float(c['host.mips'])
    hosts=int(c['hosts']);racks=int(c['racks']);population=int(c['population'])
    limit=min(int(c['host.ram.mb'])//int(c['vm.ram.mb']),int(c['host.bandwidth.kbps'])//1000,int(c['host.storage.mb'])//1000)
    data=list(rows(path));expected={(b,m,str(s)) for s in SEEDS for m in METHODS
          for b in (['generations'] if m in ['FFD','BFD'] else ['generations','evaluations','time'])}
    if len(data)!=55 or {(r['budget'],r['method'],r['seed']) for r in data}!=expected:
        raise AssertionError('Missing/duplicate budget cases')
    for r in data:
        plan=np.array([int(x) for x in r['host_plan'].split(';')]);assert len(plan)==len(d)
        assert np.all((plan>=0)&(plan<hosts))
        counts=np.bincount(plan,minlength=hosts);load=np.bincount(plan,weights=d,minlength=hosts)
        assert max(load)<=float(c['packing.cap'])+1e-8 and max(counts)<=limit
        watts=np.where(counts>0,float(c['host.idle.w'])+(float(c['host.max.w'])-float(c['host.idle.w']))*load,0)
        total=watts.sum()+sum(module_loss(x,c) for x in watts.reshape(racks,hosts//racks).sum(axis=1))
        close(float(r['total_w']),total,1e-6);close(float(r['server_w']),float(watts.sum()),1e-6)
        genetic=r['method'] not in ['FFD','BFD'];evals=int(r['evaluations']);gen=int(r['generations'])
        assert evals==population*(gen+1) if genetic else evals==1
        if r['budget']=='evaluations':assert evals<=4000 and evals+population>4000
        if r['budget']=='generations' and genetic:assert gen==60
        if r['budget']=='time':assert int(r['overrun_ns'])==max(0,int(r['solve_ns'])-100000000)
        if r['method']=='BFD-GA':same_groups(bfd(d,hosts,float(c['packing.cap']),limit),plan)
    return data

def prepare(out):
    if out.exists():raise FileExistsError('Choose a new robustness directory')
    sources=sorted((ROOT/'correction/inputs').glob('cohort25_*.csv'))
    if len(sources)!=10:raise AssertionError('Ten existing dates required')
    out.mkdir(parents=True);(out/'inputs').mkdir();(out/'configs').mkdir();(out/'runs').mkdir();(out/'budgets').mkdir()
    base=settings(ROOT/'research_platform/config/default.properties');plan=[];inputs=[]
    for source in sources:
        date=source.stem.split('_')[-1];raw=np.loadtxt(source,delimiter=',',ndmin=2)
        if raw.shape!=(100,288) or not np.isfinite(raw).all():raise AssertionError('Invalid date trace')
        mean=raw.mean(axis=1,keepdims=True)
        for profile,unclipped in [('observed',raw),('light',raw*.6),('bursty',mean+1.5*(raw-mean))]:
            data=np.clip(unclipped,0,1);trace=out/'inputs'/f'{date}_{profile}.csv'
            np.savetxt(trace,data,delimiter=',',fmt='%.12f')
            inputs.append(dict(date=date,profile=profile,source=source.relative_to(ROOT).as_posix(),source_sha256=sha(source),
                path=trace.relative_to(out).as_posix(),sha256=sha(trace),clipped_fraction=float(np.mean(unclipped!=data))))
            for seed in SEEDS:
                config=out/'configs'/f'{date}_{profile}_{seed}.properties';c=dict(base,**{'trace.path':trace.as_posix(),'experiment.seed':str(seed),'packing.cap':'1'})
                config.write_text(''.join(k+'='+v+'\n' for k,v in sorted(c.items())),encoding='utf-8')
                for method in METHODS:plan.append(dict(date=date,profile=profile,seed=seed,method=method,
                    config=config.relative_to(out).as_posix(),run=f'runs/{date}_{profile}_{method}_{seed}'))
    snapshot=out/'study_source';snapshot.mkdir()
    for name in ['src','tools','lib','build']:
        shutil.copytree(ROOT/name,snapshot/name,ignore=shutil.ignore_patterns('__pycache__'))
    source_hashes={p.relative_to(snapshot).as_posix():sha(p) for p in snapshot.rglob('*') if p.is_file()}
    metadata=dict(schema=1,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),config_hashes={f.relative_to(out).as_posix():sha(f) for f in (out/'configs').glob('*.properties')},inputs=inputs,cases=plan,seeds=SEEDS,source_hashes=source_hashes,
        interpretation='All study cases use packing.cap=1 (physical capacity), keeping CPU migration trigger .9. This differs from the original paper matrix cap .9. Ten selected-date cohorts, not a confirmed longitudinal same-VM panel. Light=.6*CPU; bursty=VM daily mean+1.5*deviation, clipped to [0,1]. Synthetic profiles are not additional independent dates.',
        budgets='All solvers assessed by total server+UPS power. 60 generations / 4000 scored candidates / 100ms soft checkpoints. Preprocessing counted in time; objective count excludes feasibility/power validation. BFD-GA retains fixed BFD groups; search spaces differ.')
    (out/'plan.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')

def execute_case(payload):
    out,item,java=payload
    run=out/item['run']
    if not run.exists():
        result=subprocess.run([java,'-Xmx1g','-cp','bin;lib/*','repro.ResearchExperiments','--mode','single','--config',str(out/item['config']),
            '--output',str(run),'--method',item['method']],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
        (run.parent/(run.name+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        if result.returncode:raise RuntimeError('Simulation failed: '+str(run))
    verify(run)
    r=list(rows(run/'summary.csv'))[0]
    return dict(item,**{k:r[k] for k in ['total_kwh','requested_mi','delivered_mi','finished']})

def execute(out,java):
    plan=json.loads((out/'plan.json').read_text(encoding='utf-8'))
    for rel,expected in plan['source_hashes'].items():
        if sha(ROOT/rel)!=expected:raise AssertionError('Current source changed since plan freeze: '+rel)
    for rel,expected in plan['config_hashes'].items():
        if sha(out/rel)!=expected:raise AssertionError('Frozen configuration changed')
    for item in plan['inputs']:
        if sha(out/item['path'])!=item['sha256']:raise AssertionError('Frozen input changed')
    collected=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        pending=[pool.submit(execute_case,(out,item,java)) for item in plan['cases']]
        try:
            for job in as_completed(pending):
                collected.append(job.result())
                if len(collected)%25==0:print(f'ROBUST {len(collected)}/{len(pending)}',flush=True)
        except BaseException:
            for job in pending:job.cancel()
            raise
    collected.sort(key=lambda r:(r['date'],r['profile'],r['method'],r['seed']));write_csv(out/'dynamic.csv',collected)
    budget_rows=[]
    for item in plan['inputs']:
        config=out/'configs'/f"{item['date']}_{item['profile']}_101.properties"
        target=out/'budgets'/f"{item['date']}_{item['profile']}.csv"
        if not target.exists():subprocess.run([java,'-Xmx1g','-cp','bin;lib/*','repro.ResearchBudgetBenchmark',str(config),str(target)],cwd=ROOT,check=True)
        for r in check_budget(target,config):budget_rows.append(dict(date=item['date'],profile=item['profile'],**r))
        print('BUDGET',item['date'],item['profile'],flush=True)
    write_csv(out/'budget_results.csv',budget_rows)
    for rel,expected in plan['source_hashes'].items():
        if sha(ROOT/rel)!=expected:raise AssertionError('Source changed during study: '+rel)
    summarize(out,collected,budget_rows)
    (out/'completed.json').write_text(json.dumps(dict(status='PASS',dynamic_cases=len(collected),budget_solves=len(budget_rows)),indent=2),encoding='utf-8')

def summarize(out,data,budget):
    grouped=defaultdict(dict)
    for r in data:grouped[r['profile'],r['date'],str(r['seed'])][r['method']]=r
    statistics=[]
    for profile in ['observed','light','bursty']:
        for comparator in METHODS[:-1]:
            for metric in ['total_kwh','unserved_pct','kwh_per_billion_mi']:
                dates=defaultdict(list)
                def value(r):
                    req=float(r['requested_mi']);done=float(r['delivered_mi']);e=float(r['total_kwh'])
                    return e if metric=='total_kwh' else 100*(1-done/req) if metric=='unserved_pct' else e/(done/1e9)
                for (p,date,seed),methods in grouped.items():
                    if p==profile:dates[date].append(value(methods['BFD-GA'])-value(methods[comparator]))
                statistics.append(dict(profile=profile,comparator=comparator,metric=metric,
                    **paired_interval([np.mean(dates[d]) for d in sorted(dates)])))
    write_csv(out/'paired_statistics.csv',statistics)
    lines=['# 跨日期与公平预算研究','', '750个动态案例逐例独立核验；1650次求解最终方案、功率、资源及预算计数独立重算。所有研究配置packing.cap=1，迁移触发阈值仍为.9；不与原矩阵cap=.9冒充同配置对比。',
        '', '统计单位为日期：先在同日期同负载下平均5个配对种子差值，再对10个日期进行10000次固定种子bootstrap。95%区间为探索性逐项区间，未作多重比较校正；相邻日期可能相关，不能视为随机抽取总体的证明。',
        '', '差值=BFD-GA−比较方法。能耗须与未交付率、每十亿MI能耗共同解释。人工低载/波动场景不是新增独立日期，也不等于作者原始工作负载。',
        '', '公平预算统一评价服务器+UPS总功率；BFD-GA仍有固定分组搜索空间差异。评估次数只计候选目标评分，最终校验/预处理另计耗时。时间限制是完整种群检查点软预算，初始化和预处理不可抢占，必须同时查看solve_ns与overrun_ns；不能宣称严格等运行时间。单次预热、固定随机方法顺序降低但不能消除JIT与顺序影响。',
        '', '结果见 paired_statistics.csv、dynamic.csv、budget_results.csv；原始输入和冻结代码见plan.json及study_source。']
    (out/'研究报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--java',default='java');p.add_argument('--prepare-only',action='store_true');a=p.parse_args()
    output=Path(a.output).resolve()
    if not output.exists():prepare(output)
    if not a.prepare_only:execute(output,a.java)
