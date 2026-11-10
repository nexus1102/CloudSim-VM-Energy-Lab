"""Independent algebra/event verification of the separate public-destination experiments."""
from pathlib import Path
import csv,json,hashlib
import paper_audit
ROOT=Path(__file__).resolve().parents[1];R=ROOT/'paper_alignment/public_migration'
def main():
    data=list(paper_audit.rows(R/'results/summary.csv'))
    methods=['FFD','BFD','GA','GGA','BFD-GA'];controllers=['threshold','framework_underload'];destinations=['cloudsim_min_power','ups_min_power']
    expected={(day,c,d,m,str(101+101*k)) for day in ['20110303','20110306','20110309'] for c in controllers for d in destinations for m in methods for k in range(5 if day=='20110303' else 1)}
    found={(v['day'],v['controller'],v['destination'],v['method'],v['seed']) for v in data}
    if len(data)!=140 or found!=expected or len({v['prefix'] for v in data})!=140:raise AssertionError('Missing/duplicate public destination cases')
    checks=[];native_calls=0
    for row in data:
        prefix=R/'results'/row['prefix'];s=paper_audit.settings(Path(str(prefix)+'_settings.properties'))
        if s['migration.destination']!=row['destination'] or s['controller']!=row['controller']:raise AssertionError('Destination/controller labels differ from execution')
        if int(row['started'])!=int(row['finished']):raise AssertionError('Unfinished migration')
        calls=int(row['native_calls']);native_calls+=calls
        if calls<0 or row['destination']=='ups_min_power' and calls!=0:raise AssertionError('Invalid original-finder call count')
        check=paper_audit.audit(prefix,row)
        if check['duration_s']!=86400:raise AssertionError('Not 24 hours')
        checks.append(check)
    if native_calls<=0:raise AssertionError('CloudSim original finder was not executed')
    (R/'audit/independent_checks.json').write_text(json.dumps({'status':'PASS','runs':len(checks),'detailed_runs':sum(v['states']>0 for v in checks),'native_finder_calls':native_calls,'checks':checks},ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS 140 independent public-destination runs; original-finder calls',native_calls)
if __name__=='__main__':main()
