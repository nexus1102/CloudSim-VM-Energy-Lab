"""Paired date-level bootstrap; seeds within a date are not independent dates."""
import numpy as np

def paired_interval(differences, seed=20261110, draws=10000):
    values=np.asarray(differences,dtype=float)
    if len(values)<2 or not np.isfinite(values).all():
        raise ValueError('At least two finite independent date summaries required')
    rng=np.random.default_rng(seed)
    means=values[rng.integers(0,len(values),size=(draws,len(values)))].mean(axis=1)
    return dict(mean=float(values.mean()),ci_low=float(np.quantile(means,.025)),
                ci_high=float(np.quantile(means,.975)),dates=len(values))
