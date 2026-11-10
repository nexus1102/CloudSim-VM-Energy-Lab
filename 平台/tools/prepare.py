"""Traceable inputs; no thesis-result fitting. Python 3, numpy, PyMuPDF."""
from pathlib import Path
import urllib.request, json, hashlib, random, concurrent.futures
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for folder in ('config', 'data/raw', 'src/repro', 'bin', 'lib', 'results', 'figures', 'comparison', '说明', 'audit'):
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'CloudSim-thesis-reproduction'})
    with urllib.request.urlopen(req, timeout=90) as response:
        return response.read()

tree_url = 'https://api.github.com/repos/cloudsimplus/planetlab-workload-traces/git/trees/master?recursive=1'
tree = json.loads(fetch(tree_url))
files = sorted(x['path'] for x in tree['tree'] if x['type'] == 'blob' and '20110303/' in x['path'])
if len(files) < 100:
    raise RuntimeError('PlanetLab 20110303 does not contain 100 traces')
selected = sorted(random.Random(42).sample(files, 100))
commit = tree['sha']

def download(name):
    dest = ROOT / 'data/raw' / Path(name).name
    url = f'https://raw.githubusercontent.com/cloudsimplus/planetlab-workload-traces/{commit}/{name}'
    if not dest.exists():
        dest.write_bytes(fetch(url))
    raw = dest.read_bytes()
    lines = raw.decode().strip().splitlines()
    values = np.array([float(x.strip()) for x in lines if x.strip()])
    # Official trace format has a non-utilization first line (sample count).
    if len(values) == 289:
        values = values[1:]
    if len(values) != 288 or not np.isfinite(values).all() or (values < 0).any() or (values > 100).any():
        raise ValueError(f'Unexpected PlanetLab trace: {name}, {len(values)} samples')
    return values / 100, {'path': name, 'url': url, 'sha256': hashlib.sha256(raw).hexdigest()}

with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    downloaded = list(pool.map(download, selected))
raw = np.array([x[0] for x in downloaded])
# Monotone odds scaling preserves [0,1], zeros and relative activity; cap <= .85.
def normalize(target):
    lo, hi = 0., 1e6
    for _ in range(80):
        k = (lo + hi) / 2
        transformed = .85 * (k * raw) / (1 - raw + k * raw + 1e-15)
        if transformed.mean() < target:
            lo = k
        else:
            hi = k
    if abs(transformed.mean() - target) > 1e-10:
        raise ValueError('Requested mean unattainable for selected traces')
    return transformed

dynamic = normalize(.25)
np.savetxt(ROOT / 'data/dynamic.csv', dynamic, delimiter=',', fmt='%.12f')
np.savetxt(ROOT / 'data/raw_matrix.csv', raw, delimiter=',', fmt='%.12f')
# Static experiments: 100 VMs, heterogeneous CPU samples with an exact mean.
# Use one deterministic time slice and odds normalization separately by target.
static = []
for target in np.arange(.1, .8, .1):
    base = raw[:, 0] + .01
    lo, hi = 0., 1e6
    for _ in range(80):
        k = (lo + hi) / 2
        row = k * base / (1 + k * base)
        if row.mean() < target: lo = k
        else: hi = k
    static.append(row)
np.savetxt(ROOT / 'data/static.csv', static, delimiter=',', fmt='%.12f')
params = {
    'source_pdf_sha256': '3394a090d7bd26b40d6fc32b1303d432ed07c28a95e4a2375223b32d428f058e',
    'cloudsim': '3.0.3', 'java': '8', 'hosts': 100, 'racks': 5, 'hosts_per_rack': 20,
    'vm_count': 100, 'idle_w': 218.3, 'max_w': 350., 'host_mips': 2500,
    'sample_interval_s': 300, 'duration_s': 86400, 'dynamic_mean': float(dynamic.mean()),
    'static_vm_count_status': 'assumption; not specified in static experiment',
    'rack_rated_w': 7000, 'rack_rated_status': 'assumption: 20 x 350 W',
    'n_plus_1_n': 4, 'redundancy_status': 'assumed equal load-sharing; N+1 factor 1.25; 2N factor 2',
    'table_2_6': {'a0': .0241, 'a1': .0353, 'a2': .0617, 'rated_w': 2000},
    'ac_curve': {'a0': .0376, 'a1': .0069, 'a2': .0319},
    'dc_curve': {'a0': .0549, 'a1': .0077, 'a2': .0207},
    'curve_status': 'approximate quadratic reconstruction from figure 2-5; not author parameters',
    'population': 40, 'generations': 60, 'crossover': .8, 'mutation': .05,
    'seeds': [101, 202, 303, 404, 505], 'ga_parameter_status': 'assumptions; not numerically specified',
    'weights': [.01, .22, .38, .26, .10, .02, .01],
    'national_bill_usd': 8e9, 'bill_status': 'assumption approximately inferred from 138M / 1.72%',
    'planetlab_repository': 'https://github.com/cloudsimplus/planetlab-workload-traces',
    'planetlab_tree_sha': commit, 'trace_selection_seed': 42, 'trace_date': '20110303',
    'workload_status': 'public substitute; thesis trace date, IDs and transformations unspecified'
}
(ROOT / 'config/parameters.json').write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding='utf-8')
(ROOT / 'data/manifest.json').write_text(json.dumps([x[1] for x in downloaded], indent=2), encoding='utf-8')
print(json.dumps({'traces': len(downloaded), 'raw_mean': float(raw.mean()), 'dynamic_mean': float(dynamic.mean()), 'commit': commit}))
