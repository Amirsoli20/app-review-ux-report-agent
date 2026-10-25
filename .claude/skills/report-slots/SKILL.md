---
name: report-slots
description: The text slots the report-writer may fill (PRD 12.4), their limits and order, the writing rules (12.7), and finished examples in the style of templates/report_data.sample.json. The writer fills only these slots.
user-invocable: false
---

# Report text slots

The report is rendered from one fixed template; all layout, charts and fixed copy are already done. You
fill **only** these slots. You select nothing (which issues appear is decided by code) and format nothing.
The complete finished example of a data file is `templates/report_data.sample.json` (a made-up app);
the examples below follow its style.

| Slot | Limit | Rule |
| --- | --- | --- |
| summary | 4 to 6 items, at most 45 words and 330 characters each | One finding per item with its number and CI or test result. Order: top problem, largest significant change over time, top strength, rating and text mismatch, journey, country exception. Bold (`**text**`) only issue or stage names |
| patterns.problems_title | At most 14 words, 90 characters | Names the one or two problems with the most reviews, as a finding |
| patterns.strengths_title | At most 14 words, 90 characters | Names the one or two strengths with the most reviews, as a finding |
| patterns.caption | At most 70 words, 480 characters | Opens with exactly "One review can mention several problems, so the bars add up to more than the number of reviews." Then names which problems come mostly from 1 and 2 star reviews and which do not, with counts |
| glossary_examples.<key> | At most 25 words, 180 characters each | One short, plain example per measure in `required_glossary_keys`, using this report's numbers: one fact, no second comparison |

## Summary order and what each item needs
1. **Top problem**: name, weighted share with 95% CI; optionally its rating gap.
2. **Largest significant change over time** (only when `facts.over_time` exists and a test has adjusted p
   below 0.05): earlier vs recent share and the adjusted p. When no test is significant, say that the most
   raised problems did not change significantly. When there is no over-time section, skip this item.
3. **Top strength**: name and weighted share.
4. **Rating and text mismatch**: the share of 4 and 5 star reviews that report a problem, with its CI.
5. **Journey**: the most negative and the most positive stage with their net sentiment.
6. **Country exception** (only with more than one country): the problem with the largest Cramér's V among
   those with adjusted p below 0.05 and V of at least 0.1, or that no problem differs meaningfully.

## Number formats
- Shares: one decimal and %: "8.0%". Intervals: "95% CI 6.7 to 9.4%".
- Counts: thousands separators: "2,978".
- Stars: two decimals: "1.31★"; rating gaps with sign: "−2.08★".
- Net sentiment: whole number with sign: "−71", "+30".
- p-values: "p < 0.001" below 0.001, otherwise two or three decimals: "p = 0.17".
- Differences between shares: percentage points: "+7.1 points".
- κ and Cramér's V: two decimals.

## Examples (style only; the numbers and names here are not from your app)
summary:
- "The most raised problem is **Sync fails after editing offline**: 9.4% of reviews (95% CI 8.1 to 10.8%). Reviews that raise it average 1.92 fewer stars than reviews that don't."
- "**Logged out after app update** rose from 1.8% of reviews in earlier weeks to 9.0% in the last four (compared within countries, adjusted p < 0.001). The other top problems did not change significantly."
- "The most raised strength is **Clean, simple note editor** (12.3%)."
- "13.9% of 4 and 5 star reviews still report at least one problem (95% CI 12.3 to 15.7%)."
- "Along the journey, **<stage A>** is the most negative stage (net sentiment −64); **<stage B>** is the most positive (+41)."
- "Country differences are negligible for every problem (Cramér's V under 0.1) except **German text cut off in menus**, raised mostly in Germany, by 8.2% of its reviews."

patterns:
- problems_title: "Offline sync failures and logouts after the update are the most raised problems"
- strengths_title: "The simple editor and fast search are the most praised"
- caption: "One review can mention several problems, so the bars add up to more than the number of reviews. Sync failures and support loops come almost entirely from 1 and 2 star reviews. Requests for a widget are different: 35 of 39 come from reviews with 3 to 5 stars."

glossary_examples (one fact each, at most 25 words):
- stratified_share: "Sync fails offline: 9.4% of reviews, weighted by country; 7.9% (236 of 2,978) without weights."
- ci: "Sync fails offline: 9.4% of reviews, likely between 8.1% and 10.8%."
- mean_median_mode: "Reviews raising sync failures: mean 1.31★, median 1, mode 1."
- sd: "Stars on sync failure reviews: SD 0.62, tightly grouped."
- cv: "German text cut off: CV 245%, concentrated in one country."
- rating_gap: "Sync fails offline: 1.31★ against 3.39★ for other reviews, a gap of −2.08★."
- cohens_d: "Sync fails offline: d = −1.60, a very large gap."
- net_sentiment: "<stage A>: net sentiment −64, mostly negative."
- blocker_share: "<stage A>: 45% of problem statements describe a blocker."
- cmh: "Logged out after update: 1.8% of reviews before, 9.0% in the last four weeks (p < 0.001)."
- holm: "5 over-time and 12 country tests, corrected together; below 0.05 counts as a real difference."
- chi_square: "German text: V = 0.26, p < 0.001, a clear country difference."
- kappa: "Overall κ = 0.81. Widget requests have κ = 0.62 and are flagged."

## Writing rules (12.7)
- Describe, never advise: no "should", "recommend", "priority", "fix", "must", "need to".
- Say "reviews" or "reviewers", never "users" or "customers".
- Every number matches the facts and shows its unit.
- Trends, gaps and co-occurrence are patterns, not causes: "reviews that raise it average fewer stars",
  never "it lowers ratings".
