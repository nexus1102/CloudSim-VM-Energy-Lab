"""Independent verification of a restored study or matrix; requires Python, not Java."""
import argparse,json,tempfile
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
if (HERE/'verification/tools').exists():sys.path.insert(0,str(HERE/'verification/tools'))
from research_platform_audit import verify,sha
from research_figure_benchmark_audit_v10 import audit
from research_robustness import check_budget, summarize
from paper_audit import rows

def verify_study(root):
    plan=json.loads((root/'plan.json').read_text(encoding='utf-8'))
    for rel,h in plan['source_hashes'].items():
        if sha(root/'study_source'/rel)!=h:raise AssertionError('Study frozen source mismatch')
    for rel,h in plan['config_hashes'].items():
        if sha(root/rel)!=h:raise AssertionError('Study configuration mismatch')
    if len(plan['cases'])!=750:raise AssertionError('Incomplete study plan')
    derived=[];budget=[]
    for i,item in enumerate(plan['cases']):
        verify(root/item['run'])
        row=list(rows(root/item['run']/'summary.csv'))[0]
        derived.append(dict(item,**{k:row[k] for k in ['total_kwh','requested_mi','delivered_mi','finished']}))
        if i%50==0:print('STUDY_VERIFY',i+1,flush=True)
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
    print('PASS independently verified 750 dynamic cases and 1650 budget solutions')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory');p.add_argument('--kind',choices=['matrix','study'],required=True);a=p.parse_args();root=Path(a.directory).resolve()
    if a.kind=='matrix':
        verify(root);audit(root/'report/figure_benchmark')
    else:verify_study(root)
