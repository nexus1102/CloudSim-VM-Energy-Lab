"""Real solver budgets, independent power recomputation and paired statistics boundaries."""
import tempfile,subprocess,sys,json
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from research_robustness import prepare,check_budget
from research_statistics import paired_interval
root=Path(tempfile.mkdtemp(prefix='study-tests-'))/'study'
prepare(root)
plan=json.loads((root/'plan.json').read_text(encoding='utf-8'))
assert all('packing.cap=1\n' in (root/r).read_text(encoding='utf-8') for r in plan['config_hashes'])
assert len(plan['cases'])==750 and len(plan['inputs'])==30
assert len({r['source_sha256'] for r in plan['inputs']})==10
for item in plan['inputs']:
    data=np.loadtxt(root/item['path'],delimiter=',')
    assert max(data[:,0]*np.resize([1,.8,.4,.2],len(data)))<=1
config=root/'configs/20110303_observed_101.properties'
output=root/'budget.csv'
subprocess.run([sys.argv[1] if len(sys.argv)>1 else 'java','-cp','bin;lib/*','repro.ResearchBudgetBenchmark',str(config),str(output)],check=True)
assert len(check_budget(output,config))==55
# A false score/evaluation report must be rejected by the independent reader.
text=output.read_text(encoding='utf-8');lines=text.splitlines();parts=lines[1].split(',');parts[7]='-100';lines[1]=','.join(parts)
output.write_text('\n'.join(lines)+'\n',encoding='utf-8')
try:check_budget(output,config)
except AssertionError:pass
else:raise AssertionError('Corrupted objective accepted')
a=paired_interval([2]*10);assert a['mean']==a['ci_low']==a['ci_high']==2
assert paired_interval([-1,1]*5)==paired_interval([-1,1]*5)
try:paired_interval([1])
except ValueError:pass
else:raise AssertionError('Single-date inference accepted')
print('PASS frozen 750-case plan, 55 real budgets, corrupt score rejection and date-bootstrap boundaries')
