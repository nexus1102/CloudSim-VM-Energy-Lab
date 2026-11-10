"""Date-level paired intervals for solver quality, elapsed time and evaluation count."""
from collections import defaultdict
from research_statistics import paired_interval

def summarize_budget(data):
    groups=defaultdict(dict)
    for r in data:
        if r['method'] not in ['GA','GGA','BFD-GA']:continue
        key=(r['profile'],r['budget'],r['date'],str(r['seed']))
        if r['method'] in groups[key]:raise AssertionError('Duplicate budget pair')
        groups[key][r['method']]=r
    if len(groups)!=450 or any(set(g)!=set(['GA','GGA','BFD-GA']) for g in groups.values()):
        raise AssertionError('Expected 10 dates x 3 profiles x 3 budgets x 5 seeds with all genetic methods')
    result=[]
    for profile in ['observed','light','bursty']:
        for budget in ['generations','evaluations','time']:
            for comparator in ['GA','GGA']:
                for metric in ['total_w','solve_ns','evaluations']:
                    dates=defaultdict(list)
                    for (p,b,date,seed),methods in groups.items():
                        if (p,b)==(profile,budget):
                            dates[date].append(float(methods['BFD-GA'][metric])-float(methods[comparator][metric]))
                    if len(dates)!=10 or any(len(v)!=5 for v in dates.values()):raise AssertionError('Unbalanced date/seed pairs')
                    result.append(dict(profile=profile,budget=budget,comparator=comparator,metric=metric,
                        **paired_interval([sum(dates[d])/5 for d in sorted(dates)])))
    return result
