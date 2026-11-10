"""Native objectives and distinct feasible search spaces; all actual generation plans verified."""
import argparse,json,math
from pathlib import Path
from collections import defaultdict
import numpy as np
from paper_audit import rows,settings,close
from research_platform_audit import sha,module_loss,bfd,same_groups
from research_figure_report_v09 import write

SIZES=[5,10,12,30,40,80,150,230,288];BUDGETS=[3,6,12,28,45,48,59,300]
METHODS=['GA','GGA','BFD-GA'];SEEDS=[101,202,303];PROFILES=['current128','example4']
EPS=1e-7

def audit(directory):
    root=Path(directory).resolve()
    if not (root/'completed.txt').is_file():raise AssertionError('v10 benchmark incomplete')
    for r in rows(root/'provenance.csv'):
        p=(root/r['path']).resolve()
        if not p.is_relative_to(root) or sha(p)!=r['sha256']:raise AssertionError('Source/input/config hash mismatch')
    raw=np.loadtxt(root/'input.csv',delimiter=',',ndmin=2)
    configs={p:settings(root/f'{p}.properties') for p in PROFILES}
    for p,c in configs.items():
        if c['genetic.objective']!='server_only' or c['research.initialization']!='random_hosts' or c['research.bfd.ga.seed']!='false' or c['research.bfd.seed']!='false':raise AssertionError('Invalid native study config')
        if int(c['hosts'])!=100 or int(c['racks'])!=5 or float(c['packing.cap'])!=.9:raise AssertionError('Fixed geometry mismatch')
        if int(c['host.ram.mb'])//int(c['vm.ram.mb'])!=(4 if p=='example4' else 128):raise AssertionError('Resource profile')
    def key(r):return r['profile'],int(r['n']),int(r['budget']),r['method'],int(r['seed'])
    summary=list(rows(root/'summary.csv'));expected={(p,n,b,m,s) for p in PROFILES for n in SIZES for b in BUDGETS for m in METHODS for s in SEEDS}
    if len(summary)!=1296 or {key(r) for r in summary}!=expected:raise AssertionError('Grid missing/duplicate')
    histories=defaultdict(list)
    for r in rows(root/'histories.csv'):histories[key(r)].append(r)
    if set(histories)!=expected:raise AssertionError('History keys')
    count=0;initial=[];bfd_power={}
    for r in summary:
        p,n,b,m,s=key(r);c=configs[p];hs=histories[key(r)]
        if len(hs)!=b+1 or [int(x['generation']) for x in hs]!=list(range(b+1)):raise AssertionError('Iteration cardinality')
        types=np.resize([float(x) for x in c['vm.mips'].split(',')],n);d=raw[:n,0]*types/float(c['host.mips'])
        limit=min(int(c['host.ram.mb'])//int(c['vm.ram.mb']),int(c['host.bandwidth.kbps'])//1000,int(c['host.storage.mb'])//1000)
        base=bfd(d,100,.9,limit);previous=float('inf')
        base_load=np.bincount(base,weights=d,minlength=100);base_count=np.bincount(base,minlength=100)
        base_watts=np.where(base_count>0,float(c['host.idle.w'])+(float(c['host.max.w'])-float(c['host.idle.w']))*base_load,0)
        bfd_power[p,n]=float(base_watts.sum()+sum(module_loss(x,c) for x in base_watts.reshape(5,20).sum(axis=1)))
        for g in hs:
            plan=np.array([int(x) for x in g['host_plan'].split(';')])
            if len(plan)!=n or np.any(plan<0) or np.any(plan>=100):raise AssertionError('Plan completeness')
            load=np.bincount(plan,weights=d,minlength=100);occupancy=np.bincount(plan,minlength=100)
            if load.max()>.9+1e-8 or occupancy.max()>limit:raise AssertionError('Plan CPU/RAM/BW/storage infeasible')
            watts=np.where(occupancy>0,float(c['host.idle.w'])+(float(c['host.max.w'])-float(c['host.idle.w']))*load,0)
            server=float(watts.sum());total=server+sum(module_loss(x,c) for x in watts.reshape(5,20).sum(axis=1))
            objective=total if m=='BFD-GA' else server
            close(float(g['objective_w']),objective)
            if objective>previous+EPS:raise AssertionError('Elite objective increased')
            previous=objective;count+=1
            if m=='BFD-GA':same_groups(base,plan)
        close(float(r['objective_w']),objective);close(float(r['server_w']),server);close(float(r['total_w']),total)
        if int(r['hosts'])!=sum(occupancy>0) or not math.isfinite(float(r['solve_ms'])) or float(r['solve_ms'])<0:raise AssertionError('Final metric')
        if b==300:initial.append(dict(profile=p,n=n,method=m,seed=s,initial_hosts=len(set(map(int,hs[0]['host_plan'].split(';')))),final_hosts=int(r['hosts'])))
        else:
            long=histories[(p,n,300,m,s)]
            if any(a['host_plan']!=z['host_plan'] or a['objective_w']!=z['objective_w'] for a,z in zip(hs,long[:b+1])):raise AssertionError('Short solve not deterministic prefix')
    if count!=82458:raise AssertionError('History plan count')
    references={}
    for p in PROFILES:
        for n in SIZES:
            for goal in ['server','bfd_groups_total']:
                selected=[r for r in summary if r['profile']==p and int(r['n'])==n and int(r['budget'])==300 and ((r['method']=='BFD-GA')==(goal=='bfd_groups_total'))]
                references[p,n,goal]=min(float(r['objective_w']) for r in selected)
    checks=[]
    for r in summary:
        p,n,b,m,s=key(r);goal='bfd_groups_total' if m=='BFD-GA' else 'server';ref=references[p,n,goal]
        hs=histories[key(r)];hit=next((int(x['generation']) for x in hs if float(x['objective_w'])<=ref+EPS),None)
        opportunity=max(0,bfd_power[p,n]-ref) if m=='BFD-GA' else 0
        target=ref+.01*opportunity+EPS
        quality_hit=next((int(x['generation']) for x in hs if float(x['objective_w'])<=target),None)
        checks.append(dict(profile=p,n=n,budget=b,method=m,seed=s,feasible=True,objective=goal,objective_w=float(r['objective_w']),reference_w=ref,
            gap_w=float(r['objective_w'])-ref,precision_pass=float(r['objective_w'])<=ref+EPS,first_hit_gen=hit if hit is not None else '',
            concentrated_bfd_w=bfd_power[p,n],avoidable_power_w=opportunity,quality_target_w=target,quality_pass=float(r['objective_w'])<=target,
            quality_first_hit_gen=quality_hit if quality_hit is not None else '',solve_ms=float(r['solve_ms'])))
    frontier=[]
    for p in PROFILES:
        for m in METHODS:
            for b in BUDGETS[:-1]:
                selected=lambda n:[r for r in checks if r['profile']==p and r['method']==m and r['n']==n and r['budget']==b]
                sizes=[n for n in SIZES if all(r['quality_pass'] for r in selected(n))]
                strict=[n for n in SIZES if all(r['precision_pass'] for r in selected(n))]
                frontier.append(dict(profile=p,method=m,budget=b,max_tested_quality_n=max(sizes) if sizes else 0,passing_sizes=';'.join(map(str,sizes)),
                    max_tested_precision_n=max(strict) if strict else 0,strict_passing_sizes=';'.join(map(str,strict))))
    write(root/'checks.csv',checks);write(root/'frontier.csv',frontier);write(root/'initial_final_hosts.csv',initial)
    result=dict(status='PASS',solves=1296,independently_recomputed_plans=count,feasible_solves=1296,epsilon_w=EPS,
        criterion='Native objectives, same feasible search-space 300-generation reference; GA/GGA server target, BFD-GA reference+1% of concentrated BFD avoidable power; strict 1e-7W guard also reported; 3/3 seeds; no author stopping rule or optimum certificate',
        profiles='current128 vs paper illustrative4 (not proved actual experimental RAM)')
    (root/'independent_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS native benchmark 1296 solves and 82458 generation plans');return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);audit(p.parse_args().root)
