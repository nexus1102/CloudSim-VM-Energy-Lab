"""Independent fixed-budget verification; common feasible reference, never an optimum claim."""
import argparse,csv,json,math,sys
from pathlib import Path
from collections import defaultdict
import numpy as np
from paper_audit import rows,settings,close
from research_platform_audit import sha,module_loss,bfd,same_groups

SIZES=[5,10,12,30,40,80,150,230,288];BUDGETS=[3,6,12,28,45,48,59];METHODS=['GA','GGA','BFD-GA'];SEEDS=[101,202,303]
def write(path,items):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(items[0]));w.writeheader();w.writerows(items)
def audit(run):
    root=Path(run).resolve()/'report/figure_benchmark'
    if not (root/'completed.txt').is_file():raise AssertionError('Benchmark incomplete')
    for item in rows(root/'provenance.csv'):
        p=(root/item['path']).resolve()
        if not p.is_relative_to(root) or sha(p)!=item['sha256']:raise AssertionError('Benchmark source/input hash mismatch')
    c=settings(root/'config.properties');raw=np.loadtxt(root/'input.csv',delimiter=',',ndmin=2);types=list(map(float,c['vm.mips'].split(',')))
    placements=defaultdict(list);histories=defaultdict(list)
    def key(r):return int(r['n']),int(r['budget']),r['method'],int(r['seed'])
    for r in rows(root/'placements.csv'):placements[key(r)].append(r)
    for r in rows(root/'histories.csv'):histories[key(r)].append(r)
    summary=list(rows(root/'summary.csv'));expected={(n,b,m,s) for n in SIZES for b in BUDGETS for m in METHODS for s in SEEDS}|{(n,0,'BFD',0) for n in SIZES}
    actual=[key(r) for r in summary]
    if len(actual)!=576 or len(set(actual))!=576 or set(actual)!=expected or set(placements)!=expected:raise AssertionError('Incomplete or duplicate grid')
    if set(histories)!={k for k in expected if k[2]!='BFD'}:raise AssertionError('History keys')
    for r in summary:
        k=key(r);n,b,method,seed=k;p=placements[k]
        if len(p)!=n or [int(x['vm']) for x in p]!=list(range(n)):raise AssertionError('VM cardinality/order')
        d=np.array([raw[i,0]*types[i%len(types)]/float(c['host.mips']) for i in range(n)])
        np.testing.assert_allclose([float(x['demand']) for x in p],d,rtol=0,atol=1e-12)
        plan=np.array([int(x['host']) for x in p]);counts=np.zeros(100,dtype=int);load=np.zeros(100)
        if np.any(plan<0) or np.any(plan>=100):raise AssertionError('Host index')
        np.add.at(counts,plan,1);np.add.at(load,plan,d)
        if max(load)>.9+1e-8 or max(counts)>128:raise AssertionError('CPU/resource infeasibility')
        host=np.where(counts>0,float(c['host.idle.w'])+(float(c['host.max.w'])-float(c['host.idle.w']))*load,0)
        total=float(host.sum()+sum(module_loss(x,c) for x in host.reshape(5,20).sum(axis=1)))
        close(float(r['total_w']),total)
        if not math.isfinite(float(r['solve_ms'])) or float(r['solve_ms'])<0:raise AssertionError('Wall time')
        base=bfd(d,100,.9,128)
        if method=='BFD':np.testing.assert_array_equal(plan,base)
        else:
            hs=histories[k]
            if len(hs)!=b+1 or [int(x['generation']) for x in hs]!=list(range(b+1)):raise AssertionError('Generation grid')
            values=np.array([float(x['objective_w']) for x in hs])
            if not np.isfinite(values).all() or np.any(np.diff(values)>1e-7):raise AssertionError('Elite monotonicity')
            objective=total if method=='BFD-GA' or c['genetic.objective']=='total' else float(host.sum())
            close(values[-1],objective);close(float(r['objective_w']),objective)
            if method=='BFD-GA':same_groups(base,plan)
    reference={n:min(float(r['total_w']) for r in summary if int(r['n'])==n) for n in SIZES}
    checks=[];frontier=[]
    for r in summary:
        n,b,m,s=key(r);checks.append(dict(n=n,budget=b,method=m,seed=s,total_w=float(r['total_w']),reference_w=reference[n],
            gap_pct=100*(float(r['total_w'])/reference[n]-1),within_1pct=float(r['total_w'])<=1.01*reference[n]+1e-7,solve_ms=float(r['solve_ms'])))
    for method in METHODS:
        for budget in BUDGETS:
            valid=[]
            for n in SIZES:
                items=[r for r in checks if r['n']==n and r['budget']==budget and r['method']==method]
                if sum(r['within_1pct'] for r in items)/3>=.8:valid.append(n)
            frontier.append(dict(method=method,budget=budget,max_tested_passing_n=max(valid) if valid else 0,passing_sizes=';'.join(map(str,valid))))
    write(root/'checks.csv',checks);write(root/'frontier.csv',frontier)
    result=dict(status='PASS',genetic_solves=567,bfd_references=9,criterion='Within 1% of common best-known feasible full power, >=80% of 3 seeds (all 3 required); finite tested grid only, not author rule or global optimum',source='Frozen public static_30 first n VMs, unmodified')
    (root/'independent_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS Figure 2-26 independent audit: 567 actual solves + 9 references');return result
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');p=argparse.ArgumentParser();p.add_argument('--run',required=True);audit(p.parse_args().run)
