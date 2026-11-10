"""Restore a content-addressed data ZIP, checking every blob and safe output path."""
import argparse,hashlib,json,re,shutil,zipfile
from pathlib import Path,PurePosixPath

def restore(archive,output):
    output=Path(output).resolve()
    if output.exists():raise FileExistsError('Choose a new restoration directory')
    with zipfile.ZipFile(archive) as z:
        manifest=json.loads(z.read('manifest.json'))
        if manifest.get('schema')!=1:raise ValueError('Unsupported data format')
        records=manifest['files'];names=set();blobs={}
        for r in records:
            name=r['path'];parts=PurePosixPath(name).parts
            if not parts or name.startswith('/') or '\\' in name or ':' in name or '..' in parts or name in names or parts[0] in {'.restore-blobs','dataset_manifest.json'}:
                raise ValueError('Unsafe/duplicate output path: '+name)
            if not re.fullmatch('[0-9a-f]{64}',r['sha256']) or r['size']<0:raise ValueError('Invalid hash/size')
            names.add(name)
            if r['sha256'] in blobs and blobs[r['sha256']]!=r['size']:raise ValueError('Conflicting blob sizes')
            blobs[r['sha256']]=r['size']
        if len(z.namelist())!=len(set(z.namelist())):raise ValueError('Duplicate ZIP members')
        output.mkdir(parents=True)
        # Validate all unique blobs before reconstructing the data tree.
        cache=output/'.restore-blobs';cache.mkdir()
        for digest,size in blobs.items():
            h=hashlib.sha256();count=0
            with z.open('blobs/'+digest) as src,(cache/digest).open('wb') as dst:
                for block in iter(lambda:src.read(1024*1024),b''):
                    count+=len(block)
                    if count>size:raise ValueError('Blob exceeds declared size')
                    h.update(block);dst.write(block)
            if count!=size or h.hexdigest()!=digest:raise ValueError('Blob integrity failure: '+digest)
        for r in records:
            target=output/r['path']
            if not target.resolve().is_relative_to(output):raise ValueError('Output escapes destination')
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(cache/r['sha256'],target)
        (output/'dataset_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS restored',len(records),'files; verified',len(blobs),'unique blobs:',output)
    return output

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive');p.add_argument('output');a=p.parse_args();restore(a.archive,a.output)
