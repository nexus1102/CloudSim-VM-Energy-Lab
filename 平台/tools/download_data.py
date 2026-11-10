"""Download or join verified release parts into the original content-addressed ZIP."""
import argparse,hashlib,json,re,urllib.request
from pathlib import Path

BASE='https://github.com/nexus1102/CloudSim-VM-Energy-Lab/releases/download/data-2026-11-10/'
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def join(manifest,output,download=False):
    manifest=Path(manifest);output=Path(output)
    if output.exists():raise FileExistsError('Choose a new output ZIP')
    data=json.loads(manifest.read_text(encoding='utf-8'));parts=data['parts'];names=set()
    if not parts or len(parts)>1000 or not re.fullmatch('[0-9a-f]{64}',data['sha256']):raise ValueError('Invalid manifest')
    for item in parts:
        name=item['name']
        if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]*',name) or name in names:raise ValueError('Invalid/duplicate part name')
        if not 0<item['size']<=64*1024*1024 or not re.fullmatch('[0-9a-f]{64}',item['sha256']):raise ValueError('Invalid part size/hash')
        names.add(name);p=manifest.parent/name
        if not p.exists() and download:
            with urllib.request.urlopen(urllib.request.Request(BASE+name,headers={'User-Agent':'CloudSim-data-download'}),timeout=120) as response:
                content=response.read(item['size']+1)
            if len(content)!=item['size'] or hashlib.sha256(content).hexdigest()!=item['sha256']:raise ValueError('Downloaded part failed integrity: '+name)
            with p.open('xb') as f:f.write(content)
            print('Downloaded and verified',name,flush=True)
        if p.stat().st_size!=item['size'] or digest(p)!=item['sha256']:raise ValueError('Part integrity failure: '+name)
    h=hashlib.sha256()
    with output.open('xb') as out:
        for item in parts:
            with (manifest.parent/item['name']).open('rb') as f:
                for block in iter(lambda:f.read(1024*1024),b''):h.update(block);out.write(block)
    if h.hexdigest()!=data['sha256']:raise ValueError('Combined ZIP hash mismatch')
    print('PASS reconstructed ZIP:',output,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('manifest');p.add_argument('output');p.add_argument('--download',action='store_true');a=p.parse_args();join(a.manifest,a.output,a.download)
