"""Exercise every real date/profile through CloudSim and strict independent audit."""
import sys,json,tempfile
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from research_robustness import prepare,execute_case

def main():
    root=Path(tempfile.mkdtemp(prefix='all-study-inputs-'))/'study';prepare(root)
    plan=json.loads((root/'plan.json').read_text(encoding='utf-8'))
    cases=[item for item in plan['cases'] if item['seed']==101 and item['method']=='FFD']
    assert len(cases)==30
    java=sys.argv[1] if len(sys.argv)>1 else 'java'
    with ProcessPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(execute_case,[(root,item,java) for item in cases]))
    assert len(results)==30
    print('PASS all 30 date/profile inputs through actual FFD simulation and independent audit')

if __name__=='__main__':main()
