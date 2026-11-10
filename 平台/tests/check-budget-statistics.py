import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from budget_statistics import summarize_budget
data=[]
for date in range(10):
    for profile in ['observed','light','bursty']:
        for budget in ['generations','evaluations','time']:
            for seed in range(5):
                for method in ['GA','GGA','BFD-GA']:
                    data.append(dict(date=str(date),profile=profile,budget=budget,seed=seed,method=method,
                         total_w=100 if method=='BFD-GA' else 102,solve_ns=100000000,evaluations=2440))
r=summarize_budget(data);assert len(r)==54
assert all(x['mean']==x['ci_low']==x['ci_high']==-2 for x in r if x['metric']=='total_w')
assert all(x['mean']==0 for x in r if x['metric']!='total_w')
try:summarize_budget(data[:-1])
except AssertionError:pass
else:raise AssertionError('Incomplete pair accepted')
print('PASS 54 paired budget intervals and missing-pair rejection')
