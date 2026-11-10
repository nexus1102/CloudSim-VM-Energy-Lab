"""Fractional synthetic CPU must survive CSV without relaxing audit tolerance."""
import subprocess,tempfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from paper_audit import settings,rows
from research_platform_audit import verify
r=Path(tempfile.mkdtemp(prefix='cpu-precision-'))
trace=r/'fractional.csv';trace.write_text('.557899305556,.2\n.1,.3\n',encoding='utf-8')
c=settings(Path('research_platform/config/default.properties'));c.update({'trace.path':trace.as_posix(),'research.controller':'none','packing.cap':'1'})
config=r/'config.properties';config.write_text(''.join(k+'='+v+'\n' for k,v in c.items()),encoding='utf-8')
subprocess.run([sys.argv[1] if len(sys.argv)>1 else 'java','-cp','bin;lib/*','repro.ResearchExperiments',
               '--mode','single','--config',str(config),'--output',str(r/'run'),'--method','BFD'],check=True)
verify(r/'run')
a=list(rows(r/'run/cases/single_BFD_assignments.csv'))[0]
assert abs(float(a['raw_cpu'])-.557899305556)<1e-14
print('PASS fractional CPU roundtrip and unchanged strict audit tolerances')
