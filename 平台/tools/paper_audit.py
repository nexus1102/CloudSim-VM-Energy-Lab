"""Independent formula and event audit; never imports Java power functions."""
from pathlib import Path
import csv,json,math,hashlib
from bisect import bisect_right
from collections import defaultdict
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'paper_alignment'
def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        yield from csv.DictReader(f)
def settings(path):
    result={}
    for line in path.read_text(encoding='utf-8').splitlines():
        if line and not line.startswith('#') and '=' in line:
            k,v=line.split('=',1);result[k]=v
    return result
def close(a,b,tol=1e-5):
    if not math.isfinite(a+b) or abs(a-b)>tol:
        raise AssertionError(f'{a} != {b}; error {abs(a-b)}')
def loss(p,s):
    installed=float(s['ups.usable.w'])*float(s['ups.factor'])
    if not -1e-8<=p<=float(s['ups.usable.w'])+1e-6:raise AssertionError('UPS capacity')
    return float(s['ups.a0'])*p*p/installed+float(s['ups.a1'])*p+float(s['ups.a2'])*installed
def audit(prefix,summary=None):
    s=settings(Path(str(prefix)+'_settings.properties'))
    hosts=int(s['hosts']);racks=int(s['racks']);duration=len(list(rows(Path(str(prefix)+'_times.csv'))))*int(s['step.seconds'])
    idle=float(s['host.idle.w']);maximum=float(s['host.max.w']);mips=float(s['host.mips'])
    server_j=ups_j=requested=delivered=0.;last=0.;segments=0
    for row in rows(Path(str(prefix)+'_segments.csv')):
        begin,end=float(row['begin_s']),float(row['end_s']);close(begin,last,1e-7)
        if end<=begin:raise AssertionError('Nonpositive interval')
        dt=end-begin;server=float(row['server_w']);ups=float(row['ups_loss_w'])
        output=[float(row[f'rack{r}_output_w']) for r in range(racks)]
        close(server,sum(output))
        calculated=[loss(p,s) for p in output]
        for r in range(racks):close(calculated[r],float(row[f'rack{r}_loss_w']))
        close(ups,sum(calculated))
        server_j+=server*dt;ups_j+=ups*dt;requested+=float(row['requested_mips'])*dt;delivered+=float(row['delivered_mips'])*dt
        if float(row['delivered_mips'])>float(row['requested_mips'])+1e-6:raise AssertionError('Duplicate processing')
        last=end;segments+=1
    close(last,duration,1e-7)
    raw=None
    if summary:
        case=summary['case']
        if case in ['main','framework_underload','server_objective','uniform_vm','bandwidth10G','periodic_extension']:
            raw_path=ROOT/'correction/inputs/cohort25_20110303.csv'
        else:
            normalized=case.removeprefix('framework_');raw_path=ROOT/'correction/inputs'/f'{normalized}.csv'
        raw=np.loadtxt(raw_path,delimiter=',')
    elif prefix.name.startswith('platform_'):raw=np.loadtxt(R/'inputs/platform_raw.csv',delimiter=',')
    types=np.array([float(v) for v in s['vm.mips'].split(',')])
    if raw is not None:
        nominal=np.resize(types,raw.shape[0]);close(requested,float(np.sum(raw*nominal[:,None])*int(s['step.seconds'])),.05)
    active={};seen_source={};event_count=0
    for row in rows(Path(str(prefix)+'_events.csv')):
        t=float(row['time_s']);vm=int(row['vm_id']);source=int(row['source_host']);target=int(row['target_host']);event=row['event']
        if event=='START':
            if vm in active:raise AssertionError('Duplicate migration')
            if source==target or not (0<=source<hosts and 0<=target<hosts):raise AssertionError('Invalid migration endpoints')
            if not 0<=t<duration:raise AssertionError('Migration outside observation window')
            for other in active.values():
                if {source,target}&{int(other['source_host']),int(other['target_host'])}:
                    raise AssertionError('Concurrent migrations share reserved endpoint')
            if row['reason']=='over90_random_one':
                if float(row['source_cpu'])<=float(s['cpu.trigger'])+1e-8:raise AssertionError('Untriggered migration')
                key=(round(t,7),source)
                if key in seen_source:raise AssertionError('More than one selected VM/source/sample')
                seen_source[key]=vm
            active[vm]=row;event_count+=1
        elif event=='FINISH':
            start=active.pop(vm);expected=float(start['ram_mb'])*16000/float(start['bandwidth_kbps'])
            close(t-float(start['time_s']),expected,1e-6)
            if t>duration or any(start[k]!=row[k] for k in ['source_host','target_host','ram_mb','bandwidth_kbps','reason']):
                raise AssertionError('Migration completion does not match reservation')
        else:raise AssertionError('Unknown migration event')
    if active:raise AssertionError('Incomplete migration')
    if s['controller']=='none' and event_count:raise AssertionError('Static platform migrated')
    cloud=list(rows(Path(str(prefix)+'_cloudlets.csv')))
    actual=sum(int(c['completed_mi']) for c in cloud)
    # ResCloudlet rounds remaining MI; one MI per VM at each window endpoint is allowed.
    close(actual,delivered,2*len(cloud)+1)
    if summary:
        close(server_j/3600000,float(summary['server_kwh']),1e-7)
        close(ups_j/3600000,float(summary['ups_kwh']),1e-7)
        close(requested,float(summary['requested_mi']),.01);close(delivered,float(summary['delivered_mi']),.01)
        if event_count!=int(summary['started']):raise AssertionError('Migration count')
    hp=Path(str(prefix)+'_hosts.csv');ap=Path(str(prefix)+'_assignments.csv');cpu_error=0;states=0
    if hp.exists() and ap.exists():
        host_rows=iter(rows(hp));assignment_rows=iter(rows(ap));nv=len(cloud)
        moves=list(rows(Path(str(prefix)+'_events.csv')))
        history=defaultdict(list)
        for e in moves:
            if e['event']=='START':history[int(e['vm_id'])].append((float(e['time_s']),int(e['target_host'])))
        starts_by_vm={vm:[v[0] for v in history[vm]] for vm in history}
        for first in host_rows:
            block=[first]+[next(host_rows) for _ in range(hosts-1)]
            assignments=[next(assignment_rows) for _ in range(nv)]
            t=float(first['time_s']);u=np.zeros(hosts)
            for a in assignments:
                close(float(a['time_s']),t);h=int(a['host_id']);allocation=float(a['allocated_mips']);migration=a['in_migration']=='true'
                vm=int(a['vm_id']);close(float(a['requested_mips']),float(a['raw_cpu'])*types[vm%len(types)],1e-6)
                if raw is not None:close(float(a['raw_cpu']),raw[vm,min(int((t+1e-7)//int(s['step.seconds'])),raw.shape[1]-1)],1e-8)
                u[h]+=allocation/(.9 if migration else 1)/mips
                if migration:
                    vm=int(a['vm_id']);index=bisect_right(starts_by_vm[vm],t+1e-8)-1
                    if index<0:raise AssertionError('Migration state without START')
                    target=history[vm][index][1];u[target]+=.1*float(a['requested_mips'])/mips
            for h in block:
                hid=int(h['host_id']);cpu=float(h['cpu']);err=abs(cpu-min(1,u[hid]));cpu_error=max(cpu_error,err)
                close(cpu,min(1,u[hid]),1e-7)
                expected_power=idle+(maximum-idle)*cpu if int(h['vm_entries']) else 0
                close(float(h['power_w']),expected_power)
            states+=1
        try:next(assignment_rows);raise AssertionError('Trailing assignment rows')
        except StopIteration:pass
    return {'prefix':prefix.name,'segments':segments,'duration_s':duration,'migrations':event_count,'states':states,
            'cpu_error':cpu_error,'energy_kwh':(server_j+ups_j)/3600000,'shortage_fraction':(requested-delivered)/requested if requested else 0}
def main():
    checks=[]
    for name in ['platform_fixed','platform_peaff','test_nomigration','test_migration']:
        prefix=R/'results'/name
        if Path(str(prefix)+'_settings.properties').exists():checks.append(audit(prefix))
    dynamic=list(rows(R/'results/dynamic_summary.csv'))
    if len(dynamic)!=540 or len({(v['case'],v['method'],v['seed']) for v in dynamic})!=540:
        raise AssertionError('Incomplete or duplicate dynamic cases')
    for row in dynamic:
        checks.append(audit(R/'results'/f"{row['case']}_{row['method']}_{row['seed']}",row))
    fixed=list(rows(R/'results/platform_fixed_assignments.csv'))[:20]
    expected=[5,5,5,5,0,0,0,0,1,1,1,0,1,6,5,6,6,6,6,7]
    if [int(x['host_id']) for x in fixed]!=expected:raise AssertionError('Figure 2-14')
    static=list(rows(R/'results/static_summary.csv'))
    if len(static)!=1400 or len({tuple(v[k] for k in ['family','architecture','target','method','seed']) for v in static})!=1400:
        raise AssertionError(f'Incomplete or duplicate static cases {len(static)}')
    for v in static:
        server=float(v['server_w']);ups=float(v['ups_w']);total=float(v['total_w'])
        expected_server=int(v['hosts'])*float(v['idle_w'])+(float(v['max_w'])-float(v['idle_w']))*float(v['actual_host_demand'])*100
        close(server,expected_server,1e-4)
        outputs=[float(v[f'rack{r}_output_w']) for r in range(5)]
        close(server,sum(outputs))
        config={'ups.usable.w':v['ups_usable_w'],'ups.factor':v['ups_factor'],'ups.a0':v['ups_a0'],'ups.a1':v['ups_a1'],'ups.a2':v['ups_a2']}
        close(ups,sum(loss(x,config) for x in outputs));close(total,server+ups)
    performance=list(rows(R/'results/performance.csv'))
    if len(performance)!=540 or len({tuple(v[k] for k in ['vm_count','budget','method','seed']) for v in performance})!=540:
        raise AssertionError('Incomplete or duplicate solver benchmarks')
    for v in performance:
        power,reference,elapsed=float(v['total_w']),float(v['reference_w']),float(v['solve_ms'])
        if not all(math.isfinite(x) and x>0 for x in [power,reference]) or not math.isfinite(elapsed) or elapsed<0:
            raise AssertionError('Invalid solver benchmark measurement')
        expected=power<=reference*1.01+1e-8
        if (v['within_1pct']=='true')!=expected:raise AssertionError('Incorrect benchmark success flag')
    result={'status':'PASS','dynamic_runs':len(checks)-4,'static_runs':len(static),'performance_runs':len(performance),'checks':checks,
            'scope':'Independent UPS algebra, interval coverage, host CPU/owner allocation, VM mapping, migration lifecycle, actual completed work and resource execution'}
    (R/'audit/independent_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for pattern in ['src/repro/*.java','paper_alignment/config/*','paper_alignment/inputs/*','correction/inputs/*.csv'] for p in ROOT.glob(pattern) if p.is_file()}
    (R/'audit/source_input_hashes.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS independent audit',len(checks),'trace runs,',len(static),'static runs')
if __name__=='__main__':main()
