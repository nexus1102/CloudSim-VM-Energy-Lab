"""Lossless SHA-256 deduplication of raw runs; no results or provenance rewritten."""
import argparse,json,zipfile,hashlib
from pathlib import Path,PurePosixPath

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def package(output,sources):
    output=Path(output)
    if output.exists():raise FileExistsError(output)
    files=[];blobs={};names=set()
    for label,source in sources:
        source=Path(source)
        if not label or label.startswith('/') or '\\' in label or ':' in label or '..' in PurePosixPath(label).parts:
            raise ValueError('Unsafe source label')
        if source.is_symlink():raise ValueError('Symlink source unsupported')
        if not source.exists():raise FileNotFoundError(source)
        paths=sorted(source.rglob('*')) if source.is_dir() else [source]
        for p in paths:
            if p.is_symlink():raise ValueError('Symlink source unsupported')
            if not p.is_file() or '__pycache__' in p.parts:continue
            relative=label+'/'+p.relative_to(source).as_posix() if source.is_dir() else label
            if relative in names:raise ValueError('Duplicate package path')
            names.add(relative);digest=sha(p);blobs.setdefault(digest,p)
            files.append(dict(path=relative,sha256=digest,size=p.stat().st_size))
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        z.writestr('manifest.json',json.dumps(dict(schema=1,files=files),ensure_ascii=False))
        for digest,source in blobs.items():
            z.write(source,'blobs/'+digest)
            if sha(source)!=digest:raise AssertionError('Source changed during packaging')
    print('PASS package',len(files),'files,',len(blobs),'unique blobs, bytes:',output.stat().st_size)
    return dict(files=len(files),unique_blobs=len(blobs),sha256=sha(output),bytes=output.stat().st_size)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--source',action='append',required=True,help='label=directory_or_file');a=p.parse_args()
    package(a.output,[x.split('=',1) for x in a.source])
