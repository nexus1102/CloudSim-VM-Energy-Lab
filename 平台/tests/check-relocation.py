"""Real relocated new/legacy runs; Verify must not resolve a JDK."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from research_platform_audit import confined, resolve_trace

root = Path(tempfile.mkdtemp(prefix='relocated-data-'))
for name, source in [('new',Path(sys.argv[1])),
                     ('legacy',Path('research_platform/runs/smoke_ga_v10'))]:
    target = root/name
    shutil.copytree(source, target)
    before = {p.relative_to(target): p.read_bytes() for p in target.rglob('*.csv')
              if 'report' not in p.relative_to(target).parts}
    env = dict(os.environ, RESEARCH_JAVA_HOME='Z:/no-jdk', RESEARCH_PYTHON=sys.executable)
    subprocess.run(['powershell','-ExecutionPolicy','Bypass','-File',
                    str(Path('run_research_platform.ps1').resolve()),'-Mode','Verify',
                    '-Output',str(target)],env=env,check=True)
    assert all((target/p).read_bytes()==data for p,data in before.items())
for value in ['../outside.csv','inputs/../../escape.csv','C:/outside.csv']:
    try: confined(root,value)
    except AssertionError: pass
    else: raise AssertionError('Unsafe path accepted: '+value)
print('PASS relocated legacy/new runs, original bytes, traversal rejection and Verify without JDK')
