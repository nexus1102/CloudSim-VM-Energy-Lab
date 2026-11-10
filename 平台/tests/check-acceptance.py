"""Portable acceptance tests; no external historical data or previous runs required."""
from pathlib import Path
import sys, tempfile, subprocess, os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from research_platform_audit import require_matrix_artifacts, verify_trajectories

def main():
    root=Path(tempfile.mkdtemp(prefix='matrix-acceptance-'))
    (root/'completed.txt').write_text('PASS: matrix',encoding='utf-8')
    names=['summary.csv','provenance.csv','run_config.properties','histories.csv',
           'solver_placements.csv','benchmark_config.properties','inputs/static_30.csv']
    for name in names:
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.touch()
    for name in names:
        p=root/name;p.unlink()
        try: require_matrix_artifacts(root)
        except AssertionError as error: assert name in str(error)
        else: raise AssertionError('Missing artifact accepted: '+name)
        p.touch()
    bench=root/'real-benchmark'
    java=Path(os.environ.get('RESEARCH_JAVA_HOME',os.environ.get('JAVA_HOME','')))/'bin/java.exe'
    subprocess.run([str(java) if java.is_file() else 'java','-cp','bin;lib/*','repro.MatrixAcceptance',str(bench)],check=True)
    assert verify_trajectories(bench)==27
    (bench/'histories.csv').write_text('n,method,seed,generation,objective_w\n',encoding='utf-8')
    try: verify_trajectories(bench)
    except AssertionError: pass
    else: raise AssertionError('Truncated trajectories accepted')
    print('PASS required artifacts, 27 real trajectories and truncation rejection')

if __name__=='__main__': main()
