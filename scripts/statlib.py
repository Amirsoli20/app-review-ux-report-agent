"""Statistical measures used by the report (PRD section 11). Pure functions, unit-tested in tests/.

Shares are fractions (0 to 1) here; stats.py converts to percent for the report.
"""
import math
import statistics
from collections import Counter

import numpy as np
from scipy import stats as st

Z95 = 1.959963984540054


def wilson(k, n, z=Z95):
    """Wilson score interval for k successes of n."""
    if n <= 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - h) / d), min(1.0, (c + h) / d)


def stratified(k, n, w, z=Z95):
    """Stratified share across strata (countries).

    k, n, w: dicts keyed by stratum: successes, sample size, population weight. Strata with n == 0 are left
    out and the remaining weights renormalised. Returns (p_w, se, lo, hi) with lo floored at 0.
    """
    keys = [c for c in n if n[c] > 0]
    tw = sum(w[c] for c in keys)
    if not keys or tw <= 0:
        return 0.0, 0.0, 0.0, 0.0
    p = se2 = 0.0
    for c in keys:
        wc = w[c] / tw
        pc = k.get(c, 0) / n[c]
        p += wc * pc
        se2 += wc * wc * pc * (1 - pc) / n[c]
    se = math.sqrt(se2)
    return p, se, max(0.0, p - z * se), min(1.0, p + z * se)


def describe_stars(x):
    """Mean, SD (n - 1), median, mode and CV of star ratings. Stars are ordinal, so median and mode are shown too.
    The median of an even count is the lower middle value, so it stays a star value; ties for mode go to the lower star."""
    x = list(x)
    if not x:
        return {"mean": 0.0, "sd": 0.0, "median": 0, "mode": 0, "cv": 0.0, "var": 0.0, "n": 0}
    mean = float(np.mean(x))
    sd = float(np.std(x, ddof=1)) if len(x) > 1 else 0.0
    cnt = Counter(x)
    top = max(cnt.values())
    return {"mean": mean, "sd": sd, "var": sd * sd, "median": int(statistics.median_low(x)),
            "mode": int(min(v for v, c in cnt.items() if c == top)), "cv": 100 * sd / mean if mean else 0.0, "n": len(x)}


def cv(values):
    """Coefficient of variation in percent (SD with n - 1, divided by the mean). Ratio-scale data only."""
    v = [float(a) for a in values]
    if len(v) < 2:
        return 0.0
    m = float(np.mean(v))
    return 100 * float(np.std(v, ddof=1)) / m if m > 0 else 0.0


def welch(x, y, z=None):
    """Difference in means x - y with a Welch 95% interval. Returns (diff, lo, hi, df)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 2 or len(y) < 2:
        d = (x.mean() if len(x) else 0) - (y.mean() if len(y) else 0)
        return float(d), float(d), float(d), 0.0
    d = x.mean() - y.mean()
    vx, vy = x.var(ddof=1) / len(x), y.var(ddof=1) / len(y)
    se = math.sqrt(vx + vy)
    if se == 0:
        return float(d), float(d), float(d), float(len(x) + len(y) - 2)
    df = (vx + vy) ** 2 / (vx ** 2 / (len(x) - 1) + vy ** 2 / (len(y) - 1))
    t = st.t.ppf(0.975, df)
    return float(d), float(d - t * se), float(d + t * se), float(df)


def cohen_d(x, y):
    """Mean difference x - y divided by the pooled SD."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 2 or len(y) < 2:
        return 0.0
    sp = math.sqrt(((len(x) - 1) * x.var(ddof=1) + (len(y) - 1) * y.var(ddof=1)) / (len(x) + len(y) - 2))
    return float((x.mean() - y.mean()) / sp) if sp > 0 else 0.0


def _log_table_prob(col_k, col_n):
    return sum(math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) for k, n in zip(col_k, col_n))


def ffh_monte_carlo(k, n, iters=20000, seed=0):
    """Fisher-Freeman-Halton exact test for a 2 x c table (mention yes/no by country), by Monte Carlo
    sampling of tables with the observed margins. Returns the p-value."""
    k, n = [int(a) for a in k], [int(a) for a in n]
    K = sum(k)
    rng = np.random.default_rng(seed)
    obs = _log_table_prob(k, n)
    sims = rng.multivariate_hypergeometric(n, K, size=iters)
    lp = np.array([_log_table_prob(row, n) for row in sims])
    return float((np.sum(lp <= obs + 1e-9) + 1) / (iters + 1))


def chi2_2xk(k, n, seed=0):
    """Chi-square test of independence for issue mention x stratum, with Cramér's V = sqrt(chi2 / N).

    Uses the Fisher-Freeman-Halton exact test for p when any expected count is below 5.
    Returns dict(chi2, p, cramer, method)."""
    k, n = np.asarray(k, float), np.asarray(n, float)
    keep = n > 0
    k, n = k[keep], n[keep]
    if len(n) < 2 or k.sum() == 0 or k.sum() == n.sum():
        return {"chi2": 0.0, "p": 1.0, "cramer": 0.0, "method": "none"}
    table = np.vstack([k, n - k])
    chi2, p, _, exp = st.chi2_contingency(table, correction=False)
    method = "chi2"
    if (exp < 5).any():
        p = ffh_monte_carlo(k, n, seed=seed)
        method = "fisher-freeman-halton (Monte Carlo)"
    return {"chi2": float(chi2), "p": float(p), "cramer": float(math.sqrt(chi2 / n.sum())), "method": method}


def holm(pvals):
    """Holm step-down adjusted p-values, in the input order."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj, run = [0.0] * m, 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (m - rank) * pvals[i]))
        adj[i] = run
    return adj


def cmh(tables):
    """Cochran-Mantel-Haenszel test of no association in a set of 2 x 2 tables [[a, b], [c, d]], with
    continuity correction. Strata without both periods or with no events are skipped. Returns p or None."""
    from statsmodels.stats.contingency_tables import StratifiedTable
    use = [np.asarray(t, float) for t in tables if np.asarray(t).sum(1).min() > 0 and np.asarray(t).sum(0).min() > 0]
    if not use:
        return None
    if len(use) == 1:  # a single stratum: CMH equals the continuity-corrected chi-square test
        return float(st.chi2_contingency(use[0], correction=True)[1])
    return float(StratifiedTable(use).test_null_odds(correction=True).pvalue)


def kappa(a, b):
    """Cohen's kappa between two label lists; 1.0 when both raters agree and use one label only."""
    from sklearn.metrics import cohen_kappa_score
    if not a:
        return None
    if len(set(a) | set(b)) == 1:
        return 1.0
    k = cohen_kappa_score(a, b)
    return 0.0 if k != k else float(k)


def kappa_band(k):
    """Landis and Koch band names, matching the template."""
    return "almost perfect" if k > 0.8 else "substantial" if k > 0.6 else "moderate" if k > 0.4 else "fair" if k > 0.2 else "slight"


def net_sentiment(pos, neg, total):
    return 100.0 * (pos - neg) / total if total else 0.0


def lift(k_ab, k_a, k_b, N):
    """Co-occurrence lift and conditional share P(B | A)."""
    if not (k_a and k_b and N):
        return 0.0, 0.0
    return k_ab * N / (k_a * k_b), k_ab / k_a
