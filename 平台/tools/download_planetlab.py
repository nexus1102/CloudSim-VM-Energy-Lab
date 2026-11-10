"""Complete author-published PlanetLab release, immutable archive and raw cohorts."""
from pathlib import Path, PurePosixPath
import urllib.request, json, hashlib, zipfile, argparse, shutil
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/'data/public/planetlab_complete'
COR=ROOT/'correction'
REPO='beloglazov/planetlab-workload-traces'
EXPECTED={'20110303':1052,'20110306':898,'20110309':1061,'20110322':1516,'20110325':1078,
          '20110403':1463,'20110409':1358,'20110411':1233,'20110412':1054,'20110420':1033}
TYPES=np.array([2500,2000,1000,500.])

def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'CloudSim-reproduction'}),timeout=90) as r:
        return r.read()

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def verify():
    manifest=json.loads((PUBLIC/'manifest.json').read_text(encoding='utf-8'))
    assert digest(PUBLIC/'release.zip')==manifest['archive_sha256'], 'Archive SHA256 mismatch'
    for entry in manifest['files']:
        path=PUBLIC/'raw'/entry['path']
        assert digest(path)==entry['sha256'], f'Raw trace SHA256 mismatch: {path}'
    assert manifest['counts']==EXPECTED and len(manifest['files'])==11746
    print('PASS full release: 11746 raw VM-day traces, 3382848 CPU measurements, 10 dates')

def near_mean(means,initial,target=.25):
    selected=np.array(initial,dtype=int)
    for _ in range(500):
        error=target*len(selected)-means[selected].sum()
        if abs(error/len(selected))<=.0001: break
        outside=np.setdiff1d(np.arange(len(means)),selected)
        delta=means[outside][None,:]-means[selected][:,None]
        a,b=np.unravel_index(np.argmin(abs(error-delta)),delta.shape)
        if abs(error-delta[a,b])>=abs(error)-1e-12: break
        selected[a]=outside[b]
    assert abs(means[selected].mean()-target)<=.001, 'Cannot construct cohort within predeclared 25% ±0.1pp'
    return np.sort(selected)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    if args.verify: verify();return
    for folder in [PUBLIC,COR/'inputs',COR/'results',COR/'config',COR/'figures',COR/'comparison',COR/'audit/v1_source']:
        folder.mkdir(parents=True,exist_ok=True)
    # Preserve previous source before correcting it. Previous CSV/PDF/figures stay in place.
    backup=COR/'audit/v1_source'
    for path in list((ROOT/'src/repro').glob('*.java'))+[ROOT/'tools/prepare.py',ROOT/'tools/plot_results.py',ROOT/'run.ps1']:
        dest=backup/path.name
        if not dest.exists(): shutil.copy2(path,dest)
    if (PUBLIC/'manifest.json').exists():
        verify();manifest=json.loads((PUBLIC/'manifest.json').read_text(encoding='utf-8'))
    else:
        commit=json.loads(fetch(f'https://api.github.com/repos/{REPO}/commits/master'))['sha']
        tree=json.loads(fetch(f'https://api.github.com/repos/{REPO}/git/trees/{commit}?recursive=1'))
        assert not tree.get('truncated',False), 'Git tree truncated'
        paths={x['path']:x['sha'] for x in tree['tree'] if x['type']=='blob' and x['path'].split('/')[0] in EXPECTED}
        assert len(paths)==11746, f'Unexpected release file count: {len(paths)}'
        url=f'https://codeload.github.com/{REPO}/zip/{commit}'
        archive=PUBLIC/'release.zip';archive.write_bytes(fetch(url))
        entries=[];counts={k:0 for k in EXPECTED};found=set()
        with zipfile.ZipFile(archive) as z:
            for item in z.infolist():
                parts=PurePosixPath(item.filename).parts
                if item.is_dir() or len(parts)!=3 or parts[1] not in EXPECTED: continue
                rel='/'.join(parts[1:]);assert rel in paths and '..' not in parts
                data=z.read(item)
                blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
                assert blob==paths[rel], f'Git blob hash mismatch: {rel}'
                values=np.array([int(x) for x in data.decode('ascii').splitlines()])
                assert len(values)==288 and ((values>=0)&(values<=100)).all(), f'Invalid raw trace: {rel}'
                dest=PUBLIC/'raw'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
                entries.append({'path':rel,'sha256':hashlib.sha256(data).hexdigest(),'git_blob_sha':blob})
                found.add(rel);counts[parts[1]]+=1
        assert found==set(paths) and counts==EXPECTED, 'Incomplete archive'
        manifest={'repository':f'https://github.com/{REPO}','commit':commit,'archive_url':url,
                  'archive_sha256':digest(archive),'counts':counts,'interval_s':300,'samples_per_day':288,
                  'total_traces':11746,'total_measurements':11746*288,'raw_units':'CPU percent of VM capacity',
                  'scope':'complete published 10-day release, not the entire historical PlanetLab archive',
                  'files':sorted(entries,key=lambda x:x['path'])}
        (PUBLIC/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        (PUBLIC/'git_tree.json').write_text(json.dumps(tree,indent=2),encoding='utf-8')
        verify()
    selections=[];daily=[];matrices={}
    for day,count in EXPECTED.items():
        files=sorted((PUBLIC/'raw'/day).iterdir())
        matrix=np.array([[int(v)/100 for v in p.read_text(encoding='ascii').splitlines()] for p in files])
        matrices[day]=(files,matrix)
        rng=np.random.default_rng(42); initial=rng.choice(count,100,replace=False)
        cohorts={'random':np.sort(initial),'cohort25':near_mean(matrix.mean(axis=1),initial)}
        daily.append({'date':day,'traces':count,'mean_cpu':float(matrix.mean()),'peak_cpu':float(matrix.max()),
                      'p50_vm_mean':float(np.median(matrix.mean(axis=1)))})
        for kind,ids in cohorts.items():
            path=COR/'inputs'/f'{kind}_{day}.csv';np.savetxt(path,matrix[ids],delimiter=',',fmt='%.2f')
            selections.append({'date':day,'kind':kind,'csv':str(path.relative_to(ROOT)),
                'mean_vm_cpu':float(matrix[ids].mean()),'sha256':digest(path),
                'selection':'seed42 NumPy random 100; mean-only swaps for cohort25, tolerance0.1pp; no power/algorithm results used',
                'trace_files':[str(files[i].relative_to(PUBLIC/'raw')) for i in ids]})
    # Static snapshots preserve raw utilization. Offered-load levels are controlled by VM count.
    files,matrix=matrices['20110303'];perm=np.random.default_rng(42).permutation(len(files))
    ratios=TYPES[np.arange(len(files))%4]/2500
    available=(matrix[perm]*ratios[:,None]).sum(axis=0)
    eligible=np.flatnonzero(available>=70)
    assert len(eligible), '20110303 has no snapshot supporting 70 host equivalents with declared VM types'
    instant=int(eligible[0]);snapshot=matrix[perm,instant];static=[]
    for target in range(10,71,10):
        demand=snapshot*ratios;prefix=int(np.searchsorted(np.cumsum(demand),target))+1
        chosen=list(range(prefix))
        if prefix>1 and abs(demand[:prefix-1].sum()-target)<abs(demand[:prefix].sum()-target):chosen.pop()
        path=COR/'inputs'/f'static_{target}.csv';np.savetxt(path,snapshot[chosen,None],delimiter=',',fmt='%.2f')
        static.append({'target_host_load':target/100,'actual_host_load':float(demand[chosen].sum()/100),
                       'vm_count':len(chosen),'date':'20110303','sample_index':instant,'time_s':instant*300,
                       'csv':str(path.relative_to(ROOT)),'sha256':digest(path),
                       'trace_files':[str(files[perm[i]].relative_to(PUBLIC/'raw')) for i in chosen]})
    config={'data_source':manifest['repository'],'commit':manifest['commit'],'daily_statistics':daily,
            'selections':selections,'static_snapshots':static,'host_mips':2500,'vm_mips_types':TYPES.tolist(),
            'resource_status':'VM type MIPS from CloudSim3.0.3 examples; one-PE2500 host retained as explicit thesis-unknown baseline',
            'normalization':'none: raw percentage divided by100 only','control_interval_s':300,
            'controller_modes':['overload_only','periodic_full_algorithms'],
            'periodic_status':'explicit common-controller extension, not an established author implementation'}
    (COR/'config/data_manifest.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'daily_traces':EXPECTED,'cohort25_means':[(x['date'],x['mean_vm_cpu']) for x in selections if x['kind']=='cohort25'],
                      'static':[(x['vm_count'],x['actual_host_load']) for x in static],'commit':manifest['commit']}))

if __name__=='__main__': main()
