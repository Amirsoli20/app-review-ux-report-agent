---
name: stats-definitions
description: Every statistical measure used in the App Review UX report (PRD section 11) with its formula, unit, conditions and how to phrase it in a worked example.
user-invocable: false
---

# Statistics definitions

All statistics are computed by code (`scripts/statlib.py`, `scripts/stats.py`). Text never computes new
numbers; it copies them from the facts. A measure is shown only where its assumptions hold.

| Key | Measure | Definition | Phrase it as |
| --- | --- | --- | --- |
| stratified_share | Stratified share | Σ w_c × p_c over countries, w_c = the country's share of App Store ratings among the selected countries, p_c = share of that country's reviews raising the issue. Default share everywhere | "8.0% of reviews (weighted by country)"; the plain count is k of n reviews |
| ci | 95% confidence interval | Stratified: p_w ± 1.96 × SE, SE = √(Σ w_c² p_c(1−p_c)/n_c), lower bound floored at 0. Single-country and sentiment shares use the Wilson interval | "95% CI 6.7 to 9.4%". Overlapping intervals mean the data cannot say which is larger |
| mean_median_mode | Mean, median, mode | Average, middle value, most common value of the stars of reviews raising the issue. Stars are ordinal, so median and mode are always shown with the mean | "mean 1.31★, median 1, mode 1" |
| sd | Standard deviation | √(Σ(x − mean)² / (n − 1)); variance is SD² | "SD 0.62, tightly grouped" / "SD 1.21, spread from 1 to 5" |
| cv | Coefficient of variation | SD ÷ mean × 100 of an issue's share across countries. Ratio data only; never applied to stars | "CV 24% (raised evenly)" / "CV 245% (concentrated in one country)" |
| rating_gap | Rating gap | Mean stars of reviews raising the issue minus mean stars of the other reviews, Welch 95% CI | "−2.08★: 1.31★ against 3.39★". A difference, never a cause |
| cohens_d | Cohen's d | Rating gap ÷ pooled SD. 0.2 small, 0.5 medium, 0.8 large | "d = −1.6 (very large)" |
| net_sentiment | Net sentiment | (positive − negative statements) ÷ all statements × 100, from −100 to +100 | "net sentiment −71" |
| blocker_share | Blocker share | Blocker statements ÷ problem statements (bug reports and complaints) in a stage, in % | "45% of problem statements describe a blocker" |
| cmh | Cochran–Mantel–Haenszel test | Change in an issue's share between the last 4 weeks and earlier weeks, tested within each country (countries without data in both periods are left out) | "1.8% in earlier weeks vs 9.0% in the last four, adjusted p < 0.001" |
| holm | Holm adjustment | Step-down correction of p-values within a family of tests (the over-time tests; the country tests) | "Below 0.05 after adjustment counts as a significant difference" |
| chi_square | Chi-square test, Cramér's V | Issue mention × country; Fisher-Freeman-Halton exact test when an expected count is below 5; V = √(χ² ÷ N): under 0.1 negligible, 0.1 to 0.3 small to moderate, over 0.3 strong | "V = 0.26, p < 0.001, a real country difference" |
| kappa | Cohen's κ | Agreement between the main and the second labeling pass, corrected for chance. Landis and Koch: over 0.80 almost perfect, 0.61 to 0.80 substantial, 0.41 to 0.60 moderate. Below 0.70 an issue is flagged "less reliable" | "Overall κ = 0.81" |

## Units and denominators
- An issue's share counts **reviews**: a review that mentions an issue several times counts once.
- Sentiment shares, severity mixes and stage counts count **statements**, and say so.
- Differences between shares are in **percentage points** ("pp" or "points").
- "Problem" means a bug report, complaint, or a negative comparison. "Praise" means praise or a positive comparison.

## Not used
- Composite "UX scores" combining frequency, sentiment and severity.
- Unweighted averages of country percentages.
- Causal language for trends, gaps or co-occurrence.
- Tests on groups with fewer than 30 reviews.
