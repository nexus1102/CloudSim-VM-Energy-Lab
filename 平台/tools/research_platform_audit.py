"""Independent module-by-module, work, event, initial mapping and hardware energy audit."""
from pathlib import Path, PureWindowsPath
from collections import defaultdict
from bisect import bisect_right
import argparse,csv,hashlib,json,math,sys
import numpy as np
from paper_audit import audit,rows,settings,close

ROOT=Path(__file__).resolve().parents[1]
METHODS=['FFD','BFD','GA','GGA','BFD-GA'];SEEDS=['101','202','303']

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def module_loss(output,c):
    n=int(c['ups.required.modules']);top=c['ups.topology'];active=2*n if top=='two_n' else n+1 if top=='n_plus_1_shared' else n
    rated=float(c['ups.module.rated.w']);each=output/active
    if not -1e-8<=output<=float(c['ups.usable.w'])+1e-6 or each>rated+1e-6:raise AssertionError('Module/output capacity')
    return active*(float(c['ups.loss.quadratic'])*each**2/rated+float(c['ups.loss.linear'])*each+float(c['ups.loss.constant'])*rated)+float(c['ups.standby.loss.w'])

def bfd(demand,hosts,cap,limit):
    load=np.zeros(hosts);counts=np.zeros(hosts,dtype=int);mapping=[];result=np.zeros(len(demand),dtype=int)
    for i in sorted(range(len(demand)),key=lambda k:-demand[k]):
        candidate=[h for h in range(hosts) if load[h]+demand[i]<=cap+1e-8 and counts[h]<limit]
        if not candidate:raise AssertionError('Infeasible BFD reference')
        h=max(candidate,key=lambda j:load[j]);result[i]=h;load[h]+=demand[i];counts[h]+=1
    return result

def same_groups(a,b):
    forward=defaultdict(set);reverse=defaultdict(set)
    for x,y in zip(a,b):forward[int(x)].add(int(y));reverse[int(y)].add(int(x))
    if any(len(v)!=1 for v in list(forward.values())+list(reverse.values())):raise AssertionError('BFD-GA split or merged a first-step group')

def detailed_racks(prefix,c,s,events):
    hp=Path(str(prefix)+'_hosts.csv');ap=Path(str(prefix)+'_assignments.csv')
    if not hp.exists():return {}
    source=defaultdict(list);start_times={};endpoint=float(c['migration.incremental.w.per.endpoint'])
    for e in events:
        if e['event']=='START':source[int(e['vm_id'])].append((float(e['time_s']),int(e['source_host']),int(e['target_host'])))
    for vm,history in source.items():start_times[vm]=[z[0] for z in history]
    owner=iter(rows(ap)) if endpoint else None;host_rows=iter(rows(hp));result={};hosts=int(s['hosts']);racks=int(s['racks'])
    nv=len(list(rows(Path(str(prefix)+'_initial.csv'))))
    for first in host_rows:
        block=[first]+[next(host_rows) for _ in range(hosts-1)];t=float(first['time_s']);extra=np.zeros(hosts)
        if endpoint:
            assignments=[next(owner) for _ in range(nv)]
            for a in assignments:
                if a['in_migration']=='true':
                    vm=int(a['vm_id']);idx=bisect_right(start_times[vm],t+1e-7)-1
                    _,src,dst=source[vm][idx]
                    if int(a['host_id'])!=src:raise AssertionError('Migration hardware charged to wrong source')
                    extra[src]+=endpoint;extra[dst]+=endpoint
        outputs=np.zeros(racks)
        for h in block:
            hid=int(h['host_id']);close(float(h['time_s']),t);close(float(h['incremental_w']),extra[hid])
            outputs[hid//(hosts//racks)]+=float(h['power_w'])+extra[hid]
        result[t]=outputs
    return result

def confined(run, relative):
    relative = relative.replace('\\', '/')
    if Path(relative).is_absolute() or PureWindowsPath(relative).is_absolute():
        raise AssertionError('Archive path must be relative')
    target = (run/relative).resolve()
    if not target.is_relative_to(run.resolve()):
        raise AssertionError('Archive path escapes run')
    return target


def resolve_trace(run, raw):
    # Legacy absolute paths are provenance records, never rewritten in the archive.
    if not Path(raw).is_absolute() and not PureWindowsPath(raw).is_absolute():
        target = confined(run, raw)
    else:
        name = PureWindowsPath(raw).name if '\\' in raw else Path(raw).name
        candidates = {confined(run, item['archive_path']) for item in rows(run/'provenance.csv')
                      if item.get('archive_path') and
                      item['archive_path'].replace('\\','/').startswith('inputs/') and
                      Path(item['archive_path'].replace('\\','/')).name == name}
        if len(candidates) != 1:
            raise AssertionError('Legacy trace has no unique frozen provenance mapping: '+name)
        target = candidates.pop()
    if not target.is_relative_to((run/'inputs').resolve()) or target.suffix.lower() != '.csv':
        raise AssertionError('Trace must be frozen CSV under run inputs')
    return target


def check_case(run,row):
    prefix=run/'cases'/row['prefix'];c=settings(Path(str(prefix)+'_research.properties'));s=settings(Path(str(prefix)+'_settings.properties'))
    schema=settings(run/'run_config.properties').get('experiment.schema','1')
    if schema=='2' and row['kind']=='dynamic':
        expected_init='random_hosts' if row['prefix'].startswith('random_init_') else 'feasible_packing'
        if c.get('research.initialization')!=expected_init:raise AssertionError('Initialization control mismatch')
    raw_path=resolve_trace(run,row['raw_path'])
    if not raw_path.is_relative_to((run/'inputs').resolve()) or raw_path.suffix.lower()!='.csv':raise AssertionError('Trace must be frozen CSV under run inputs')
    raw=np.loadtxt(raw_path,delimiter=',',ndmin=2);types=np.resize([float(x) for x in s['vm.mips'].split(',')],raw.shape[0])
    if raw.shape[0]!=int(row['vm_count']):raise AssertionError('VM count')
    close(float(row['requested_mi']),float(np.sum(raw*types[:,None])*int(s['step.seconds'])),.05)
    # Legacy event audit resolves an absolute case path to that exact frozen CSV.
    legacy=dict(row,case=str(raw_path.with_suffix('')));check=audit(prefix,legacy if raw.shape[1]>1 else None)
    events=list(rows(Path(str(prefix)+'_events.csv')));timeline=[];pending=[];count=0
    rack_states=detailed_racks(prefix,c,s,events)
    for e in events:
        count+=1 if e['event']=='START' else -1;timeline.append(float(e['time_s']));pending.append(count)
    host_j=hardware_j=ups_j=delivered=0.;endpoint=float(c['migration.incremental.w.per.endpoint']);racks=int(s['racks'])
    for seg in rows(Path(str(prefix)+'_segments.csv')):
        begin=float(seg['begin_s']);dt=float(seg['end_s'])-begin;index=bisect_right(timeline,begin+1e-7)-1
        actual_pending=pending[index] if index>=0 else 0
        if actual_pending!=int(seg['pending']):raise AssertionError('Segment pending count != event lifecycle')
        hw=float(seg['hardware_w']);close(hw,2*endpoint*actual_pending)
        close(float(seg['server_w']),float(seg['host_model_w'])+hw)
        outputs=[float(seg[f'rack{r}_output_w']) for r in range(racks)]
        if rack_states:
            for expected,actual in zip(rack_states[begin],outputs):close(float(expected),actual,1e-5)
        losses=[module_loss(p,c) for p in outputs]
        for r in range(racks):close(losses[r],float(seg[f'rack{r}_loss_w']))
        close(sum(losses),float(seg['ups_loss_w']))
        host_j+=float(seg['host_model_w'])*dt;hardware_j+=hw*dt;ups_j+=sum(losses)*dt
        delivered+=float(seg['delivered_mips'])*dt
    for field,value in [('host_model_kwh',host_j),('hardware_kwh',hardware_j),('ups_kwh',ups_j)]:close(value/3600000,float(row[field]),1e-7)
    close((host_j+hardware_j)/3600000,float(row['server_kwh']),1e-7)
    close((host_j+hardware_j+ups_j)/3600000,float(row['total_kwh']),1e-7)
    close(delivered,float(row['delivered_mi']),.01)
    close(hardware_j,2*endpoint*float(row['migration_seconds']),1e-6)
    if int(row['started'])!=int(row['finished']):raise AssertionError('Unfinished migration')
    initial=list(rows(Path(str(prefix)+'_initial.csv')))
    if [int(z['vm_id']) for z in initial]!=list(range(raw.shape[0])):raise AssertionError('Initial VM ownership incomplete')
    plan=np.array([int(z['host_id']) for z in initial]);demand=raw[:,0]*types/float(s['host.mips']);hosts=int(s['hosts'])
    if np.any(plan<0) or np.any(plan>=hosts):raise AssertionError('Invalid initial Host')
    for i,z in enumerate(initial):close(float(z['raw_cpu']),raw[i,0],1e-9);close(float(z['normalized_demand']),demand[i],1e-9)
    load=np.bincount(plan,weights=demand,minlength=hosts);counts=np.bincount(plan,minlength=hosts)
    limit=min(int(s['host.ram.mb'])//int(s['vm.ram.mb']),int(s['host.bandwidth.kbps'])//1000,int(s['host.storage.mb'])//1000)
    if max(load)>float(s['packing.cap'])+1e-8 or max(counts)>limit:raise AssertionError('Initial resource/CPU limit')
    if row['method']=='BFD-GA':same_groups(bfd(demand,hosts,float(s['packing.cap']),limit),plan)
    if row['kind']=='static':
        allocated=delivered/int(s['step.seconds'])/float(s['host.mips'])
        close(host_j/int(s['step.seconds']),float(s['host.idle.w'])*np.count_nonzero(counts)+(float(s['host.max.w'])-float(s['host.idle.w']))*allocated,1e-4)
    return dict(check,hardware_kwh=hardware_j/3600000,host_model_kwh=host_j/3600000)

def verify_trajectories(run):
    trajectory_count=0
    if (run/'histories.csv').exists():
        history=defaultdict(list);placements=defaultdict(list)
        for z in rows(run/'histories.csv'):history[(z['n'],z['method'],z['seed'])].append(z)
        for z in rows(run/'solver_placements.csv'):placements[(z['n'],z['method'],z['seed'])].append(z)
        expected={(str(n),m,seed) for n in [40,150,288] for m in ['GA','GGA','BFD-GA'] for seed in SEEDS}
        if set(history)!=expected or set(placements)!=expected:raise AssertionError('Missing solver trajectories')
        c=settings(run/'benchmark_config.properties');snapshot=np.loadtxt(run/'inputs/static_30.csv',delimiter=',',ndmin=2)
        for key,hs in history.items():
            hs=sorted(hs,key=lambda z:int(z['generation']));ps=sorted(placements[key],key=lambda z:int(z['vm']));n=int(key[0])
            if [int(z['generation']) for z in hs]!=list(range(61)) or [int(z['vm']) for z in ps]!=list(range(n)):raise AssertionError('Incomplete solver history/mapping')
            score=np.array([float(z['objective_w']) for z in hs])
            if not np.isfinite(score).all() or np.any(np.diff(score)>1e-7):raise AssertionError('Nonmonotonic or invalid elite objective')
            demand=np.array([float(z['demand']) for z in ps]);plan=np.array([int(z['host']) for z in ps])
            types=np.resize([float(x) for x in c['vm.mips'].split(',')],n)
            if np.max(abs(demand-snapshot[:n,0]*types/float(c['host.mips'])))>1e-10:raise AssertionError('Solver uses different public snapshot')
            if np.any(plan<0) or np.any(plan>=100):raise AssertionError('Solver Host range')
            load=np.bincount(plan,weights=demand,minlength=100);count=np.bincount(plan,minlength=100)
            if max(load)>.9+1e-8 or max(count)>128:raise AssertionError('Solver resource limit')
            watts=np.where(count>0,218.3+131.7*load,0);outputs=watts.reshape(5,20).sum(axis=1)
            total=float(watts.sum()+sum(module_loss(p,c) for p in outputs))
            for z in ps:close(float(z['total_w']),total)
            close(score[-1],total if key[1]=='BFD-GA' or c['genetic.objective']=='total' else float(watts.sum()))
            if key[1]=='BFD-GA':same_groups(bfd(demand,100,.9,128),plan)
            trajectory_count+=1
    return trajectory_count


def require_matrix_artifacts(run):
    marker = (run/'completed.txt').read_text(encoding='utf-8-sig')
    if 'matrix' in marker:
        required = ['summary.csv', 'provenance.csv', 'run_config.properties',
                    'histories.csv', 'solver_placements.csv', 'benchmark_config.properties',
                    'inputs/static_30.csv']
        missing = [name for name in required if not (run/name).is_file()]
        if missing:
            raise AssertionError('Incomplete Matrix artifacts: ' + ', '.join(missing))


def verify(run,force=False):
    run=Path(run).resolve();report=run/'report';report.mkdir(exist_ok=True)
    if not (run/'completed.txt').exists():raise AssertionError('Incomplete execution marker')
    require_matrix_artifacts(run)
    for item in rows(run/'provenance.csv'):
        original=Path(item['path']);archive=item.get('archive_path')
        if archive:target=confined(run,archive)
        elif original.is_relative_to(run/'inputs'):target=original
        else:target=run/'source_snapshot'/original.relative_to(ROOT)
        if not target.resolve().is_relative_to(run) or sha(target)!=item['sha256']:raise AssertionError('Archived source/input hash mismatch: '+str(target))
    data=[p for p in run.rglob('*') if p.is_file() and not p.is_relative_to(report)]
    fingerprint={str(p.relative_to(run)):sha(p) for p in data};code_hash=sha(Path(__file__));parent_hash=sha(ROOT/'tools/paper_audit.py')
    cache=report/'independent_checks.json';manifest=report/'audit_manifest.json'
    if not force and cache.exists() and manifest.exists():
        old=json.loads(manifest.read_text(encoding='utf-8'))
        if old==dict(files=fingerprint,audit_code=code_hash,parent_audit=parent_hash):
            result=json.loads(cache.read_text(encoding='utf-8'))
            if result['status']=='PASS':print('PASS unchanged run fingerprints; independently audited results reused',flush=True);return result
    summary=list(rows(run/'summary.csv'));by_kind=defaultdict(list)
    for row in summary:by_kind[row['kind']].append(row)
    if 'dynamic' in by_kind:
        require_matrix_artifacts_from_summary = ['histories.csv','solver_placements.csv','benchmark_config.properties']
        for name in require_matrix_artifacts_from_summary:
            if not (run/name).is_file():raise AssertionError('Incomplete Matrix artifacts: '+name)
        schema=settings(run/'run_config.properties').get('experiment.schema','1')
        init_extension='random_init' if schema=='2' else 'feasible_init'
        expected={f'{t}_cap{cap}_{ctrl}_{m}_{seed}' for t in ['n_plus_1_standby','n_plus_1_shared','two_n'] for cap in ['0.9','1.0']
                  for ctrl in ['threshold','consolidation'] for m in METHODS for seed in SEEDS}
        expected|={f'{ext}_{m}_{seed}' for ext in [init_extension,'total_goal','ups_destination','hardware20','standby20'] for m in METHODS for seed in SEEDS}
        expected|={f'static_cap{cap}_{arch}_{level}_{m}_{seed}' for cap in ['0.9','1.0'] for arch in ['N+1AC','N+1DC','2NAC','2NDC']
                   for level in range(10,71,10) for m in METHODS for seed in SEEDS};expected.add('platform_literal')
        if len(summary)!=1096 or {z['prefix'] for z in summary}!=expected:raise AssertionError('Incomplete/duplicate matrix')
    elif len(summary)!=1 or not summary[0]['kind']=='single':raise AssertionError('Unknown single/matrix structure')
    checks=[]
    for i,row in enumerate(summary):
        checks.append(check_case(run,row))
        if i%50==0:print(f'independent {i+1}/{len(summary)} {row["prefix"]}',flush=True)
    trajectory_count=verify_trajectories(run)
    result={'status':'PASS','cases':len(summary),'counts':{k:len(v) for k,v in by_kind.items()},'solver_trajectories':trajectory_count,
            'coverage':{'simulation':'PASS','trajectories':'PASS' if trajectory_count else 'NOT_APPLICABLE','figures':'NOT_CHECKED'},
            'scope':'Independent module loss, real event lifecycle, hardware/UPS feedback, actual completed work, CPU/ownership/resource and initial BFD group checks','checks':checks}
    cache.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    manifest.write_text(json.dumps(dict(files=fingerprint,audit_code=code_hash,parent_audit=parent_hash),ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS independent research platform audit',len(summary),trajectory_count,flush=True);return result

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');p=argparse.ArgumentParser();p.add_argument('--run',required=True);args=p.parse_args();verify(args.run)
