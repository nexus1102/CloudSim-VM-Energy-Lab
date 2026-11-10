"""Primary-source retrieval only; no login, paywall bypass, or author contact."""
from pathlib import Path
import urllib.request,urllib.parse,json,hashlib,re,shutil,difflib
import pymupdf
ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'paper_alignment/public_migration'
E=R/'evidence'
def fetch(url,path):
    if path.exists():data=path.read_bytes()
    else:
        req=urllib.request.Request(url,headers={'User-Agent':'Research-reproduction/1.0'})
        with urllib.request.urlopen(req,timeout=30) as response:data=response.read()
        path.write_bytes(data)
    return {'url':url,'file':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
def method(text,name):
    declaration=re.search(r'(?:public|protected)\s+[^{};=]*\b'+re.escape(name),text)
    if not declaration:raise ValueError('Missing method declaration '+name)
    start=declaration.start();begin=text.index('{',declaration.end());depth=0
    for end in range(begin,len(text)):
        depth+=text[end]=='{';depth-=text[end]=='}'
        if depth==0:return text[start:end+1]
    raise ValueError('Unterminated method '+name)
def main():
    E.mkdir(parents=True,exist_ok=True);backup=R/'audit/before_source';backup.mkdir(parents=True,exist_ok=True)
    for name in ['PaperSettings.java','PowerEfficiencyAwarePolicy.java']:
        target=backup/name
        if not target.exists():shutil.copy2(ROOT/'src/repro'/name,target)
    manifest={'retrieved':'2026-10-12','sources':[],'access_failures':[]}
    classes=['PowerVmAllocationPolicyMigrationAbstract','PowerVmAllocationPolicyMigrationStaticThreshold','PowerVmSelectionPolicyRandomSelection']
    for version in ['3.0.3','4.0']:
        for name in classes:
            url=f'https://raw.githubusercontent.com/Cloudslab/cloudsim/cloudsim-{version}/modules/cloudsim/src/main/java/org/cloudbus/cloudsim/power/{name}.java'
            manifest['sources'].append(fetch(url,E/f'cloudsim_{version}_{name}.java'))
    a=(E/'cloudsim_3.0.3_PowerVmAllocationPolicyMigrationAbstract.java').read_text(encoding='utf-8')
    b=(E/'cloudsim_4.0_PowerVmAllocationPolicyMigrationAbstract.java').read_text(encoding='utf-8')
    differences={}
    for name in ['findHostForVm(Vm vm, Set','getPowerAfterAllocation(PowerHost host, Vm vm)','getMaxUtilizationAfterAllocation(PowerHost host, Vm vm)','getVmsToMigrateFromHosts(List','getMigrationMapFromUnderUtilizedHosts(']:
        ma,mb=method(a,name),method(b,name)
        differences[name]={'same_after_whitespace':re.sub(r'\s+','',ma)==re.sub(r'\s+','',mb),
                          'diff':'\n'.join(difflib.unified_diff(ma.splitlines(),mb.splitlines(),fromfile='3.0.3',tofile='4.0'))}
    (E/'version_comparison.json').write_text(json.dumps(differences,ensure_ascii=False,indent=2),encoding='utf-8')
    pdf=E/'Beloglazov_Buyya_2012_CCPE.pdf'
    manifest['sources'].append(fetch('https://beloglazov.info/papers/2012-optimal-algorithms-ccpe.pdf',pdf))
    doc=pymupdf.open(pdf)
    algorithm=[]
    for i,page in enumerate(doc):
        text=page.get_text()
        if any(v in text for v in ['Algorithm 1','Algorithm 2','PABFD']) and ('placement' in text.lower() or 'power' in text.lower()):
            algorithm.append({'pdf_page':i+1,'text':text})
            page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).save(E/f'Beloglazov_algorithm_page_{i+1}.png')
    (E/'public_algorithm_evidence.json').write_text(json.dumps(algorithm,ensure_ascii=False,indent=2),encoding='utf-8')
    query=urllib.parse.urlencode({'query.title':'Power Supply Cloudsim An Extension of CloudSim for Modeling and Simulation of Power Supply Devices in Cloud Data Centers','rows':2})
    for name,url in [('author_platform_crossref','https://api.crossref.org/works?'+query),
                     ('author_two_step_crossref','https://api.crossref.org/works/10.1016/j.apenergy.2022.119467'),
                     ('author_two_step_openalex','https://api.openalex.org/works/https://doi.org/10.1016/j.apenergy.2022.119467')]:
        try:manifest['sources'].append(fetch(url,E/(name+'.json')))
        except Exception as exc:manifest['access_failures'].append({'url':url,'error':str(exc)})
    (E/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS official 3.0.3/4.0 source retrieval, public paper and version comparison')
    print('Algorithm pages',','.join(str(v['pdf_page']) for v in algorithm))
    print('Metadata access failures',len(manifest['access_failures']))
if __name__=='__main__':main()
