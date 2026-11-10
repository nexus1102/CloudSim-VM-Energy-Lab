import hashlib,json,tempfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from download_data import join
r=Path(tempfile.mkdtemp(prefix='release-parts-'));parts=[]
for i,b in enumerate([b'abc',b'def']):
    p=r/f'data.part{i}';p.write_bytes(b);parts.append(dict(name=p.name,size=len(b),sha256=hashlib.sha256(b).hexdigest()))
m=r/'manifest.json';m.write_text(json.dumps(dict(parts=parts,sha256=hashlib.sha256(b'abcdef').hexdigest())),encoding='utf-8')
join(m,r/'data.zip');assert (r/'data.zip').read_bytes()==b'abcdef'
(r/'data.part1').write_bytes(b'bad')
try:join(m,r/'wrong.zip')
except ValueError:pass
else:raise AssertionError('Corrupt part accepted')
assert not (r/'wrong.zip').exists()
print('PASS ordered split join, full hash and corrupt part rejection')
