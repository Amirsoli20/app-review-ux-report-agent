"""AC-3: statistics match reference values on fixed synthetic data."""
import itertools
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import stats as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import statlib  # noqa: E402


def test_wilson_matches_statsmodels_and_textbook():
    from statsmodels.stats.proportion import proportion_confint
    lo, hi = statlib.wilson(10, 100)
    rlo, rhi = proportion_confint(10, 100, method="wilson")
    assert lo == pytest.approx(rlo, abs=1e-9) and hi == pytest.approx(rhi, abs=1e-9)
    assert (round(lo, 4), round(hi, 4)) == (0.0552, 0.1744)
    assert statlib.wilson(0, 20)[0] == 0.0


def test_stratified_share_and_se():
    p, se, lo, hi = statlib.stratified({"a": 10, "b": 30}, {"a": 100, "b": 100}, {"a": 0.75, "b": 0.25})
    assert p == pytest.approx(0.15)
    assert se == pytest.approx(math.sqrt(0.75 ** 2 * 0.09 / 100 + 0.25 ** 2 * 0.21 / 100))
    assert lo == pytest.approx(0.15 - 1.959963984540054 * se)
    # a stratum with no reviews is left out and the weights renormalised
    p2, *_ = statlib.stratified({"a": 10, "b": 0}, {"a": 100, "b": 0}, {"a": 0.5, "b": 0.5})
    assert p2 == pytest.approx(0.10)
    # the lower bound is floored at 0
    assert statlib.stratified({"a": 1}, {"a": 10}, {"a": 1})[2] == 0.0


def test_welch_interval_matches_scipy():
    rng = np.random.default_rng(1)
    x, y = rng.integers(1, 6, 80), rng.integers(1, 6, 300)
    d, lo, hi, _ = statlib.welch(x, y)
    ci = st.ttest_ind(x, y, equal_var=False).confidence_interval(0.95)
    assert d == pytest.approx(x.mean() - y.mean())
    assert lo == pytest.approx(ci.low) and hi == pytest.approx(ci.high)


def test_cohen_d_and_star_description():
    assert statlib.cohen_d([1, 2, 3], [4, 5, 6]) == pytest.approx(-3.0)
    s = statlib.describe_stars([1, 1, 2, 5])
    assert s["mean"] == pytest.approx(2.25) and s["median"] == 1 and s["mode"] == 1
    assert s["sd"] == pytest.approx(np.std([1, 1, 2, 5], ddof=1))
    assert s["cv"] == pytest.approx(100 * s["sd"] / 2.25)
    assert statlib.describe_stars([4, 5, 5, 4])["mode"] == 4  # ties go to the lower star


def test_cv_percent():
    assert statlib.cv([10, 20, 30]) == pytest.approx(100 * np.std([10, 20, 30], ddof=1) / 20)


def test_chi_square_and_cramers_v():
    k, n = [30, 10, 20], [200, 200, 200]
    r = statlib.chi2_2xk(k, n)
    table = np.array([k, [a - b for a, b in zip(n, k)]])
    chi2, p, _, _ = st.chi2_contingency(table, correction=False)
    assert r["chi2"] == pytest.approx(chi2) and r["p"] == pytest.approx(p)
    assert r["cramer"] == pytest.approx(math.sqrt(chi2 / 600))
    assert r["method"] == "chi2"


def _exact_ffh(k, n):
    K = sum(k)
    obs = statlib._log_table_prob(k, n)
    total = 0.0
    tot_lp = math.lgamma(sum(n) + 1) - math.lgamma(K + 1) - math.lgamma(sum(n) - K + 1)
    p = 0.0
    for cells in itertools.product(*[range(c + 1) for c in n]):
        if sum(cells) != K:
            continue
        lp = statlib._log_table_prob(cells, n)
        pr = math.exp(lp - tot_lp)
        total += pr
        if lp <= obs + 1e-9:
            p += pr
    assert total == pytest.approx(1.0)
    return p


def test_fisher_freeman_halton_monte_carlo_close_to_exact():
    k, n = [4, 0, 1], [10, 9, 8]
    exact = _exact_ffh(k, n)
    mc = statlib.ffh_monte_carlo(k, n, iters=40000, seed=3)
    assert mc == pytest.approx(exact, abs=0.01)
    r = statlib.chi2_2xk(k, n)
    assert r["method"].startswith("fisher")


def test_holm():
    assert statlib.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert statlib.holm([0.5, 0.9]) == pytest.approx([1.0, 1.0])


def _cmh_manual(tables):
    num = var = 0.0
    for t in tables:
        (a, b), (c, d) = t
        n = a + b + c + d
        r1, c1 = a + b, a + c
        num += a - r1 * c1 / n
        var += r1 * (c + d) * c1 * (b + d) / (n * n * (n - 1))
    chi = (abs(num) - 0.5) ** 2 / var
    return st.chi2.sf(chi, 1)


def test_cmh_matches_formula():
    tables = [[[20, 180], [5, 195]], [[12, 88], [6, 94]], [[3, 47], [2, 48]]]
    assert statlib.cmh(tables) == pytest.approx(_cmh_manual(tables), rel=1e-9)
    assert statlib.cmh([[[0, 0], [5, 10]]]) is None


def test_kappa():
    assert statlib.kappa(["1", "1", "0", "0"], ["1", "0", "0", "0"]) == pytest.approx(0.5)
    assert statlib.kappa(["a", "a"], ["a", "a"]) == 1.0
    assert statlib.kappa_band(0.81) == "almost perfect" and statlib.kappa_band(0.7) == "substantial"


def test_net_sentiment_and_lift():
    assert statlib.net_sentiment(25, 290, 375) == pytest.approx(-70.67, abs=0.01)
    lift, cond = statlib.lift(30, 100, 150, 3000)
    assert lift == pytest.approx(6.0) and cond == pytest.approx(0.3)
