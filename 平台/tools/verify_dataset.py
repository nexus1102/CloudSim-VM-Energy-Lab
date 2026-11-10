"""Independent verification of a restored study or matrix; requires Python, not Java."""
import argparse,json,tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
if (HERE/'verification/tools').exists():sys.path.insert(0,str(HERE/'verification/tools'))
from research_platform_audit import verify,sha
from research_figure_benchmark_audit_v10 import audit
from research_robustness import check_budget, summarize
from budget_statistics import summarize_budget
from paper_audit import rows

def force_case(run):
    verify(Path(run),force=True)
    return True

def verify_study(root):
    plan=json.loads((root/'plan.json').read_text(encoding='utf-8'))
    for rel,h in plan['source_hashes'].items():
        if sha(root/'study_source'/rel)!=h:raise AssertionError('Study frozen source mismatch')
    for rel,h in plan['config_hashes'].items():
        if sha(root/rel)!=h:raise AssertionError('Study configuration mismatch')
    if len(plan['cases'])!=750:raise AssertionError('Incomplete study plan')
    derived=[];budget=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for i,ok in enumerate(pool.map(force_case,[str(root/item['run']) for item in plan['cases']])):
            if i%50==0:print('STUDY_VERIFY',i+1,flush=True)
    for item in plan['cases']:
        row=list(rows(root/item['run']/'summary.csv'))[0]
        derived.append(dict(item,**{k:row[k] for k in ['total_kwh','requested_mi','delivered_mi','finished']}))
    scratch=Path(tempfile.mkdtemp(prefix='budget-relocation-'))
    solves=0
    for item in plan['inputs']:
        trace=root/item['path']
        if sha(trace)!=item['sha256']:raise AssertionError('Study input hash mismatch')
        original=root/'configs'/f"{item['date']}_{item['profile']}_101.properties"
        # Temporary analysis config only; original sealed absolute path remains untouched.
        text=original.read_text(encoding='utf-8');text='\n'.join('trace.path='+trace.as_posix() if s.startswith('trace.path=') else s for s in text.splitlines())
        config=scratch/original.name;config.write_text(text,encoding='utf-8')
        checked=check_budget(root/'budgets'/f"{item['date']}_{item['profile']}.csv",config)
        solves+=len(checked)
        budget.extend(dict(date=item['date'],profile=item['profile'],**r) for r in checked)
    if solves!=1650:raise AssertionError('Incomplete budget study')
    summarize(scratch,derived,budget)
    if list(rows(scratch/'paired_statistics.csv'))!=list(rows(root/'paired_statistics.csv')):
        raise AssertionError('Paired statistics do not reproduce')
    recorded=list(rows(root/'budget_statistics.csv'))
    recomputed=summarize_budget(budget)
    if len(recorded)!=len(recomputed) or any(any(str(x[k])!=str(y[k]) for k in x) for x,y in zip(recorded,recomputed)):
        raise AssertionError('Budget paired statistics do not reproduce')
    print('PASS independently verified 750 dynamic cases and 1650 budget solutions')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory');p.add_argument('--kind',choices=['matrix','study'],required=True);a=p.parse_args();root=Path(a.directory).resolve()
    if a.kind=='matrix':
        verify(root,force=True);audit(root/'report/figure_benchmark')
    else:verify_study(root)
