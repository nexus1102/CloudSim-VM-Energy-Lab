import json,tempfile,zipfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from data_package import package
from restore_data import restore
r=Path(tempfile.mkdtemp(prefix='data-package-test-'));source=r/'source';source.mkdir()
(source/'a.csv').write_bytes(b'abc\n');(source/'b.csv').write_bytes(b'abc\n')
info=package(r/'data.zip',[('dataset',source)])
assert info['unique_blobs']==1 and info['files']==2
dest=restore(r/'data.zip',r/'restored');assert (dest/'dataset/a.csv').read_bytes()==b'abc\n'
with zipfile.ZipFile(r/'bad.zip','w') as z:
    z.writestr('manifest.json',json.dumps({'schema':1,'files':[{'path':'../escape','sha256':'0'*64,'size':0}]}))
try:restore(r/'bad.zip',r/'bad-output')
except ValueError:pass
else:raise AssertionError('Traversal accepted')
with zipfile.ZipFile(r/'corrupt.zip','w') as z:
    z.writestr('manifest.json',json.dumps({'schema':1,'files':[{'path':'data','sha256':'0'*64,'size':1}]}));z.writestr('blobs/'+'0'*64,b'x')
try:restore(r/'corrupt.zip',r/'corrupt-output')
except ValueError:pass
else:raise AssertionError('Corrupted blob accepted')
print('PASS lossless dedup, traversal and corruption rejection')
