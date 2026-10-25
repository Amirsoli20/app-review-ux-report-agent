# App Review UX Report Agent: PRD

Oct 20, 2026 · @Amir Soltanzade

The App Review UX Report Agent turns the public App Store reviews of an iOS app into a descriptive, statistically grounded UX report. One run takes an app name or App Store link and returns the finished report, with no human steps in between.

## 1. Overview

**Problem.** App Store reviews hold detailed evidence about an app's UX problems and strengths, but they are long, unstructured, multilingual and spread across country stores. Star averages hide what reviewers actually describe, and manual reading does not scale or produce reliable numbers.

**Solution.** An agent that collects an app's reviews from its largest App Store markets, splits each review into statements, groups statements into specific recurring issues, and reports how often each issue occurs, how reviewers feel about it, and how certain each number is.

**Goals**

| ID | Goal | Measure of success |
| --- | --- | --- |
| G1 | Name the specific problems and strengths reviewers raise | Every recurring issue has a name, definition, category and example quotes |
| G2 | Quantify each issue with research-grade statistics | Every share has a count, denominator and 95% confidence interval |
| G3 | Run end to end with no human input | One input (app name or link) produces one finished report |
| G4 | Make every number traceable | Every figure links to statement IDs and review IDs |
| G5 | Report on reliability | Label agreement and quality gate results appear in every report |

**Non-goals**

- Recommending product changes, priorities or roadmap items.
- Estimating the opinion of users who do not write reviews.
- Google Play or any source other than the Apple App Store.
- Real-time monitoring or alerts.

## 2. Users and use cases

| User | Use case |
| --- | --- |
| Product designer | Find the specific UX problems and strengths of an app before a redesign or audit |
| Product manager | See which issues are most common and how they shift between app versions |
| UX researcher | Use a reproducible, quantified baseline to plan interviews or usability tests |
| Design consultant | Assess a prospect's or competitor's app from public evidence |

## 3. Scope and constraints

**In scope**

- iOS and iPadOS apps listed on the Apple App Store.
- The app's App Store listing: name, developer, category, price, in-app purchases, description, features named in the description, current version and version history with release notes.
- Written reviews (title and body) with their star rating, date, country and app version.
- Countries chosen automatically by rating count, or a single country named by the user.
- One report per run, in English, with quotes kept in their original language plus an English translation.

**Constraints**

| Constraint | Effect on the product |
| --- | --- |
| Apple's public review feed returns at most the 500 most recent reviews per app per country (10 pages of 50) | Multiple countries are needed for volume; each country covers a different time window |
| Apple's public lookup service allows about 20 calls per minute | Country selection takes about 3 minutes for 50 countries |
| Apple publishes no user or download counts per country | Rating count per country is used as the proxy for market size |
| AI labels are interpretations of text | Labeling reliability is measured and reported on every run |

## 4. Inputs and outputs

| Item | Type | Detail |
| --- | --- | --- |
| App | Input, required | App Store link, numeric app ID, or app name |
| Country | Input, optional | Two-letter country code. When set, only that country is used |
| Settings | Input, optional | Overrides for any value in Configuration (section 16) |
| report.html | Output | The finished report, one self-contained page |
| report.pdf | Output | The same report as PDF |
| data/ folder | Output | Raw reviews, statements, issue list, statistics and run log as JSON and CSV |

## 5. Pipeline

An orchestrator runs 15 steps in a fixed order. AI sub-agents read, label and name. Scripts collect, check, compute and render. The orchestrator never asks the user for input: a failed check triggers one automatic retry, then the run continues and the failure is recorded in the report.

&#91;embedded content: review pipeline · 15 steps, no human approval\]

| # | Step | Actor | Input | Output | Rules |
| --- | --- | --- | --- | --- | --- |
| 1 | Resolve app and read listing | Script | Link, ID or name | app.json | A link or ID is parsed directly. A name is searched; the match with the most ratings is chosen and the choice is logged. The listing (description, category, price, in-app purchases, version history and release notes) is saved |
| 2 | Select countries | Script | App ID | countries.json | See section 8 |
| 3 | Collect reviews | Script | App ID, countries | raw/\*.json | Up to 10 pages of 50 reviews per country; respect the rate limit |
| 4 | Clean | Script | Raw reviews | clean/reviews.jsonl | Remove exact duplicates by review ID and by identical author + text; detect language; record each country's date window |
| 5 | Extract statements | AI, fast model, parallel batches of 25 reviews | Clean reviews, app.json | labels/statements.jsonl | See section 6 |
| 6 | Check quotes | Script | Statements | checked statements | Each text span must occur verbatim in its review. Failures are retried once, then removed |
| 7 | Group phrases | Script | Issue phrases | groups.json | Multilingual embeddings, then clustering. See section 7 |
| 8 | Name issues and build the app's structure | AI, strong model | Groups, where-in-the-app phrases, app.json | issues.yaml, structure.yaml | Name, define, merge or split groups; build categories and journey stages (section 9.6); route each issue to a team (section 9.5). Frozen after this step |
| 9 | Assign labels | AI, fast model | Statements, frozen issues and structure | labels/final.jsonl | Each statement gets one issue ID or "other", and one journey stage or "Not tied to a stage" |
| 10 | Second pass | AI, different prompt | Random 10% of statements | validation.json | Labels issue, stage, type, sentiment and severity independently |
| 11 | Quality gate | Script | Labels, validation | gate.json | See section 13 |
| 12 | Compute statistics | Script | Reviews, labels, issues, structure, weights | stats.json | Every number in the report comes from this file. See section 11 |
| 13 | Write report text | AI, strong model | stats.json, app.json, sampled statements | text slots in report\_data.json | Fills only the text slots in section 12.4; selects nothing and formats nothing; numbers copied from stats.json |
| 14 | Audit report | Script + AI | Draft, stats.json | report\_data.json, audit.json | Every number matched to stats.json; prescriptive wording removed |
| 15 | Render | Script | Final text, stats.json, run record | report.html, report.pdf | render\_report.py validates report\_data.json and injects it into the fixed template (section 12); PDF printed from the HTML |

## 6. Method: units of analysis and statement extraction

The method is aspect-based sentiment analysis: each review is split into statements, and each statement is labeled with the specific issue it is about and the feeling it expresses.

**Units of analysis**

| Unit | Definition | Used as denominator for |
| --- | --- | --- |
| Review | One submitted review: title, body, rating, date, version, country | Issue shares, rating gaps, country and version comparisons |
| Statement | One claim about one subject inside a review | Sentiment shares, severity mix, stage counts |
| Issue | A named, recurring subject shared by many statements | Rows of the issue board |

An issue's share always counts **reviews**: a review that mentions the same issue several times counts once. Statement counts are reported separately and labeled as statements.

**Extraction rules**

1. A new statement starts when the subject or the feeling changes. "Love the design but payment failed twice" is two statements.
2. Repeated mentions of the same subject in one review stay one statement.
3. Each statement carries an exact quote (text span) from the review, in the original language.
4. Each statement gets a free-text issue phrase in English: what happens and where, at most 8 words, no blame words. Example: "Apple Pay payment fails at checkout".
5. Each statement gets a free-text where-in-the-app phrase in English, at most 5 words, describing the screen or moment it refers to ("checkout screen", "after updating"), or "general". These phrases are used to build the journey stages in step 8.
6. Each statement gets one value from each fixed set: statement type (9.1), sentiment (9.2), severity for bugs and complaints (9.3) and UX dimension (9.4).
7. The app listing (app.json) is given to the extractor as context, so features named there are recognized in reviews.
8. The review title is read together with the body. A review with no meaningful text produces no statements and is counted as excluded.

## 7. Method: issue discovery and the repetition rule

Issues are discovered from the data on every run; no fixed issue list is used. Discovery has three passes.

1. **Open phrasing.** Step 5 writes a free-text issue phrase and a where-in-the-app phrase for every statement.
2. **Grouping.** Issue phrases are turned into vectors with a multilingual sentence embedding model. Similar phrases are grouped with HDBSCAN (minimum cluster size 3). Noise points form single-phrase groups.
3. **Naming and structure.** The issue-namer reads each group (its 20 most central phrases and 5 random quotes), writes one name and a one-sentence definition, merges groups that describe the same issue and splits groups that mix two issues. It then builds the derived categories and journey stages from the issues, the where-in-the-app phrases and the listing (section 9.6), and routes each issue to an owning team (section 9.5). The issue-assigner confirms or corrects each statement's issue and stage against the frozen structure.

**Repetition rule.** An issue is reported as its own row only when it is raised by at least max(5, 0.5% of reviews) distinct reviews. Issues below the threshold are reported together as the long tail, with their total count. Statements that fit no issue are labeled "other" and their share is reported.

## 8. Method: country selection and weighting

**Selection.** The rating count of the app is looked up in the 50 largest App Store countries. Countries are ranked by rating count and added until they cover 80% of all ratings found, with a minimum of 3 and a maximum of 10. A country named by the user replaces this step.

**Weighting.** Each country contributes at most 500 reviews regardless of its size, so plain pooled counts over-represent small countries. Shares are therefore computed as stratified estimates, with countries as strata and each country's weight equal to its share of ratings among the selected countries.

```latex
\hat{p}_w = \sum_{c} w_c \, \hat{p}_c, \qquad \mathrm{SE}(\hat{p}_w) = \sqrt{\sum_{c} w_c^2 \, \frac{\hat{p}_c (1 - \hat{p}_c)}{n_c}}
```

where p\_c is the issue's share of reviews in country c, n\_c the number of reviews from country c, and w\_c the country's weight. The plain collected count is shown beside every weighted share.

**Country display.** Countries are not a primary grouping in the report. Country detail appears in collapsed sections and in a country filter on the issue board. A country is shown on its own only when it has at least 50 reviews.

## 9. Label taxonomy

Label sets are of two kinds. **Fixed sets** (9.1 to 9.5) are the same for every app, so reports can be compared across apps. **Derived sets** (9.6) are built for each app from its reviews and its App Store listing; no list of categories or journey stages is supplied to the models in advance.

### 9.1 Statement type

| Type | Definition | Example |
| --- | --- | --- |
| Bug report | Something does not work as intended | "The app crashes when I open my cart" |
| Complaint | Works as built, but the reviewer dislikes how | "The delivery fee only appears on the last screen" |
| Feature request | Asks for something the app does not offer | "Please add dark mode" |
| Praise | Says something works well or is liked | "Checkout takes ten seconds" |
| Question | Asks how to do something or why something happens | "How do I change my address?" |
| Comparison | Compares the app with another app or an earlier version | "The old version was much faster" |
| Other | None of the above (greetings, off-topic text) | "First review!" |

### 9.2 Sentiment

| Value | Definition |
| --- | --- |
| Positive | The statement expresses approval or satisfaction |
| Negative | The statement expresses disapproval, frustration or harm |
| Neutral | The statement is factual or a request with no clear feeling |
| Mixed | One statement expresses both approval and disapproval of the same subject |

### 9.3 Severity (bug reports and complaints only)

| Level | Definition |
| --- | --- |
| Blocker | The reviewer could not finish a task, lost money or data, or stopped using the app |
| Major | The task was finished only with significant effort or a workaround |
| Minor | Annoying, but the task was finished normally |
| Cosmetic | Appearance or wording only; no effect on the task |

### 9.4 UX dimension

| Dimension | Definition |
| --- | --- |
| Usability | Ease of finding, understanding and completing things |
| Reliability | Crashes, errors, data loss, failed actions |
| Performance | Speed, loading, battery, storage |
| Visual design | Layout, readability, look, themes |
| Content and copy | Wording, labels, messages, translation |
| Functionality | Presence or limits of features |
| Trust and safety | Privacy, security, permissions, scams |
| Value and pricing | Price, ads, subscriptions, paywalls |
| Support | Help, contact, response, refunds |
| Accessibility | Text size, contrast, screen readers, motor access |

### 9.5 Likely owning team

Each recurring issue is routed to one primary team and up to two secondary teams: the functions that usually own that kind of problem in a company that builds an app. The label is a routing aid for the reader. It is not a judgment of any team's work, and the report never says what a team should do.

| Team | Owns issues about |
| --- | --- |
| Mobile engineering | Crashes, freezes, sign-in sessions, device performance, behaviour of the app on the phone |
| Backend and platform engineering | Servers, sync, search results, data loading, outages, APIs |
| QA and release | Problems that appear after an update (regressions) or on specific devices and OS versions |
| UX design | Flows, steps, findability, confusing behaviour, information shown at the wrong moment |
| UI and visual design | Layout, readability, themes, visual consistency |
| Content and localization | Wording, error messages, translations, text that is cut off |
| Product management | Missing features, feature requests, scope and policy decisions |
| Payments and billing | Payment methods, failed charges, subscriptions, refunds |
| Marketing and CRM | Notifications, promo codes, campaigns, emails |
| Customer support | Help channels, response, resolution |
| Operations and fulfilment | Real-world service delivered through the app: delivery, stock, partners, bookings |
| Security and privacy | Permissions, data use, account security, fraud |
| Accessibility | Screen readers, text size, contrast, motor access |

**Routing rules**

1. The issue-namer chooses the primary team from the issue's definition, statement type and UX dimension.
2. A bug report whose statements mention an update or a version adds QA and release as a secondary team.
3. A feature request is routed to Product management unless it is purely visual (UI and visual design) or a text change (Content and localization).
4. Strengths are routed the same way, so the reader sees which team's area is praised.
5. A team appears in the report only when at least one recurring issue is routed to it.

### 9.6 Derived label sets: issue categories and journey stages

Categories and journey stages differ between apps. A game may have stages such as "First level", "Daily rewards" and "Multiplayer" and no checkout; a banking app may have "Card controls" and "Transfers" and no delivery. These sets are therefore built during each run, in step 8, from three inputs:

- the app's App Store listing: description, features named in it, category, in-app purchases and release notes (step 1);
- the recurring issues and their definitions (step 8);
- the where-in-the-app phrase written for every statement (step 5).

**Issue categories**

| Rule | Detail |
| --- | --- |
| What a category is | An area of the product the issues belong to, named in the app's own vocabulary (for example "Matchmaking" in a game, "Transfers" in a bank) |
| How it is formed | The issue-namer groups the issues by product area; every issue belongs to exactly one category |
| Size | 5 to 14 categories; a category needs at least 2 issues or 2% of reviews, otherwise it is merged |
| Naming | A noun phrase for the product area, never a feeling or a type (not "Complaints", not "Bugs") |
| Evidence | Each category lists the issues it contains; no category exists without reviews behind it |

**Journey stages**

| Rule | Detail |
| --- | --- |
| What a stage is | A step a person goes through when using this app, in the order they meet it |
| How it is formed | The issue-namer drafts an ordered journey from the listing, then adjusts it with the where-in-the-app phrases: stages that reviewers mention are added, stages nobody mentions are dropped |
| Size | 4 to 10 ordered stages, plus "Not tied to a stage" for general statements |
| Evidence | Each stage records whether it comes from the listing and reviews or from reviews only, and the listing words it matches |
| Assignment | Every statement gets one stage, or "Not tied to a stage", in step 9 |

The derived sets are frozen after step 8, saved in the run record, and shown in the report section "How this report was made".

## 10. Data model

All records are JSON with a JSON Schema in `schemas/`. Every write is validated against its schema.

**App record**

| Field | Type | Example |
| --- | --- | --- |
| app\_id, name, developer | string | 1690042117, ShopNest: Shop & Delivery, ShopNest Ltd. |
| category, price, in\_app\_purchases | string, number, list | Shopping, 0, \[\] |
| description | string | Groceries and household essentials delivered in under an hour… |
| listed\_features | list of strings, extracted from the description | One-tap sign in, Apple Pay, Live driver tracking |
| store\_rating, store\_rating\_count | number per country | 4.2, 412,000 (US) |
| versions | list of version, date, release notes | 8.5, 2026-10-03, "A new, faster sign-in…" |

**Review record**

| Field | Type | Example |
| --- | --- | --- |
| review\_id | string | US-48211 |
| country | ISO 3166 code | US |
| rating | integer 1 to 5 | 1 |
| title, body | string | "Apple Pay broken", "Spins forever then fails…" |
| language | ISO 639 code | en |
| app\_version | string | 8.5 |
| date | ISO date | 2026-10-14 |
| author\_hash | string | hash of the reviewer name; the name itself is never stored in outputs |

**Statement record**

| Field | Type | Example |
| --- | --- | --- |
| statement\_id | string | US-48211\_s2 |
| review\_id | string | US-48211 |
| text\_span | string, verbatim | "spins forever then says payment failed" |
| issue\_phrase | string, English, at most 8 words | Apple Pay payment fails at checkout |
| location\_phrase | string, English, at most 5 words | checkout screen |
| issue\_id | string or "other" | pay-applepay |
| stage\_id | derived set 9.6 or "none" | checkout |
| statement\_type | set 9.1 | Bug report |
| sentiment | set 9.2 | Negative |
| severity | set 9.3 or null | Blocker |
| ux\_dimension | set 9.4 | Reliability |
| confidence | number 0 to 1 | 0.92 |
| second\_pass | object or null | labels from step 10, when sampled |

**Issue record**

| Field | Type | Example |
| --- | --- | --- |
| issue\_id | string | pay-applepay |
| name | string | Apple Pay payment fails at checkout |
| definition | one sentence | Payment with Apple Pay fails, freezes or is declined inside the app |
| category\_id | derived set 9.6 | payments |
| dominant\_type | set 9.1 | Bug report |
| stage\_id, ux\_dimension | derived set 9.6, set 9.4 | checkout, Reliability |
| team\_primary, team\_secondary | set 9.5 | Payments and billing; Mobile engineering |
| source\_groups | list | cluster IDs merged into this issue |
| recurring | boolean | true when it meets the repetition rule |

**Structure record** (structure.yaml) holds the derived categories (id, name, issue IDs) and journey stages (id, order, name, short description, source: listing and reviews or reviews only, matched listing words).

**Run record** stores the input, chosen app, countries and weights, settings, model names, prompt versions, step timings, counts in and out of every step, and quality gate results. It feeds the "How this report was made" section.

## 11. Statistical methods

All statistics are computed by `stats.py` with pandas, SciPy, statsmodels and scikit-learn. A measure is shown only where its assumptions hold.

| Measure | Definition | Applied to | Report location | Conditions |
| --- | --- | --- | --- | --- |
| Count and share | k reviews of n; k ÷ n | Issues, sentiment, types | Everywhere | Denominator always shown |
| Stratified share | Σ w\_c × p\_c (section 8) | Issue and team shares across countries; weekly shares | Issue board, teams, time chart, summary | Default view; collected count shown beside it |
| 95% CI, stratified | p\_w ± 1.96 × SE(p\_w) | Weighted shares | Issue board, teams, time chart | Lower bound floored at 0 |
| 95% CI, Wilson | Wilson score interval | Single-country shares, sentiment shares, review-mix shares | Issue board (country filter), sentiment, data overview | Preferred over the normal interval for small k |
| Review mix | Share of reviews with problems only, both, praise only, neither, per star rating | All reviews | Data overview | Wilson CI on the share of 4 and 5 star reviews with a problem |
| Mean, median, mode | Average, middle value, most common value | Stars of reviews per issue | In reviewers' words, issue board tooltip | Stars are ordinal: median and mode always shown beside the mean |
| Variance, standard deviation | Mean squared deviation; its square root (n − 1) | Stars per issue | In reviewers' words, issue board tooltip | Reported with the mean |
| Coefficient of variation (CV) | SD ÷ mean | An issue's share across countries | Issue board | Ratio-scale data only; never applied to star ratings |
| Rating gap | Mean stars with issue − mean stars without; Welch 95% CI | Every issue | Issue board, frequency chart | Described as a difference, never a cause |
| Cohen's d | Rating gap ÷ pooled SD | Every issue | Issue board tooltip | 0.2 small, 0.5 medium, 0.8 large |
| Net sentiment | (positive − negative) ÷ all statements × 100 | Categories, journey stages | Sentiment section, journey map | Range −100 to +100 |
| Blocker share | Blocker statements ÷ problem statements | Journey stages | Journey map | Stages with at least 30 problem statements |
| Lift and conditional share | lift = k\_AB × N ÷ (k\_A × k\_B); P(B given A) = k\_AB ÷ k\_A | Pairs among the 6 most frequent problems | Run record only (not shown in v1 report) | Shown when lift ≥ 2 and k\_AB ≥ 3 |
| Cochran–Mantel–Haenszel test | Change in an issue's share between the last 4 weeks and earlier weeks, tested within each country | 5 most frequent problems | Time chart table | Countries without data in both periods are left out; Holm adjustment across the 5 tests |
| Chi-square test of independence | Issue mention × country | Every problem | Country differences | Holm adjustment across issues; expected counts ≥ 5, else Fisher-Freeman-Halton exact test |
| Cramér's V | √(χ² ÷ N) for a 2 × k table | Every problem | Country differences | Under 0.1 negligible, 0.1 to 0.3 small to moderate, over 0.3 strong |
| Cohen's kappa (κ) | Agreement between main and second labeling pass, corrected for chance | Issue, stage, type, sentiment, severity | Reliability, issue board | Landis and Koch bands; κ below 0.70 flags the issue |

**Explaining every measure.** Every measure used in a report appears in the "Reading the statistics" section with three parts: its name, what it means in plain words, and one worked example taken from that report's own numbers. A measure that is not used in the report is not listed.

**Not used**

- Composite "UX scores" that combine frequency, sentiment and severity.
- Unweighted averages of country percentages.
- Causal language for trends, gaps or co-occurrence.
- Tests on groups with fewer than 30 reviews; such groups are shown greyed and labeled "low data".

## 12. Report specification and template contract

Every report is rendered from one fixed template, so all reports share the same layout, styles, charts and section order. No agent writes or edits HTML, CSS or chart code. The pipeline produces one data file, `report_data.json`, and `render_report.py` injects it into the template. Numbers, issues, categories, journey stages and quotes change from app to app; the page around them does not.

### 12.1 Template files

| File | Role | Changed by |
| --- | --- | --- |
| templates/report-template.html | The fixed page: Notion-style layout, light and dark themes, fixed copy, all chart code. Two placeholders only: {{TITLE}} and \_\_REPORT\_DATA\_\_ | Developers, as a new template version |
| schemas/report-data.schema.json | JSON Schema for report\_data.json, including length limits on every text slot | Developers, with the template |
| scripts/render\_report.py | Validates the data (schema, cross-references, word limits, banned wording), then injects it. Any error stops the render | Developers |
| templates/report\_data.sample.json | Complete sample data (ShopNest). Used in tests and given to report-writer as the example of a finished data file | Developers |
| runs/\<app-id>\_\<date>/report/report\_data.json | This run's data | Generated each run |

The template version (currently 1.0) is recorded in the run record. A change to the design is a new template version, never an edit made during a run.

### 12.2 Section order and visual form

The header shows the app name, App Store ID, run date, countries, reviews and statements, overall κ with its Landis and Koch band, and the period covered, followed by a fixed note that the report describes reviews and does not recommend changes.

| # | Section | Content | Visual form |
| --- | --- | --- | --- |
| 1 | Summary | 4 to 6 findings, each with its number and interval or test result | Bulleted list |
| 2 | About the app | Listing description, developer, category, price, current version, store rating, features named in the listing, version history with release notes; written-review average vs store rating | Quote block, property list, feature pills, version timeline |
| 3 | Data overview | Reviews, statements, share of reviews with a problem and with praise, period, languages; what each review contains by star rating. Country coverage in a closed toggle | Stat strip; 100% stacked bars per star rating |
| 4 | What reviewers feel | Sentiment share of all statements with CIs; sentiment per derived category with net sentiment | 100% stacked bar; diverging stacked bars |
| 5 | Problem and strength patterns | Every recurring problem and strength with its review count, split by star rating (problems: 1 and 2 stars vs 3 to 5; strengths: 4 and 5 vs 1 to 3) | Two horizontal stacked bar charts, sorted by count, labeled "total (part)", each with a one-line finding as title |
| 6 | In reviewers' words | One representative quote for each of the top 6 problems and top 4 strengths, with count, share and CI, review ID, stars, version, country, and the star mean (SD), median and mode of the issue's reviews | Two-column quote cards, red edge for problems, green for strengths |
| 7 | Issue board | Every recurring issue: category, type, share with CI, count, rating gap with CI, severity mix, CV across countries, κ. View tabs and country filter | Database table with inline forest plot, gap bar, severity bar, pills |
| 8 | Frequency and rating gap | Problems by share and rating gap, sized by count, medians marked | Bubble scatter with automatic, non-overlapping labels |
| 9 | Likely owning team | Per team: share of reviews raising a problem routed to it, with CI; primary and secondary issues | Rows with forest bar and issue pills |
| 10 | The journey in reviews | Derived stages in order: net sentiment, statements, most raised problem and strength, blocker share | Journey map with net sentiment curve |
| 11 | Issues over time | Weekly stratified share of the 5 most frequent problems; releases; last 4 weeks vs earlier (CMH, Holm) | One multi-line chart with release markers, recent shading, weekly counts, hover CI band; comparison table |
| 12 | Country differences | Share per country per problem; chi-square p and Cramér's V. Closed toggle | Heatmap with test column |
| 13 | Reliability | κ per issue, quality gates, limits | Dot plot with Landis and Koch bands; pass and flag table |
| 14 | Reading the statistics | Every measure used: name, plain meaning (fixed in template), worked example from this report | Table |
| 15 | How this report was made | This run's steps with counts; derived journey stages with their source; derived categories | Step ledger, log-scale funnel, stage table, category pills |

### 12.3 Data contract

| Key in report\_data.json | Filled by | Feeds |
| --- | --- | --- |
| meta | Code, from run.json | Header and every number in fixed copy |
| summary | report-writer | Section 1 |
| about | Code, from app.json | Section 2 |
| countries, country\_selection | Code | Country toggle, board filter, section 12 |
| mix | Code | Section 3 |
| sentiment | Code; category names from step 8 | Section 4 |
| issues | Code; names, definitions and short names from step 8 | Sections 5 to 8, 12, 13 |
| patterns | report-writer (titles and caption) | Section 5 |
| quotes | Code (rule 12.5) | Section 6 |
| board, teams | Code | Sections 7 and 9 |
| journey | Code; stage names, descriptions and sources from step 8 | Sections 10 and 15 |
| time | Code (optional) | Section 11 |
| reliability | Code, from gate.json | Section 13 |
| glossary\_examples | report-writer | Section 14 |
| workflow | Code, from run.json | Section 15 |

### 12.4 Text slots

These are the only places where AI-written text enters the report. All other text is fixed in the template or composed by template code from numbers (for example the review-mix caption, the rating note and the country toggle label).

| Slot | Limit | Rule |
| --- | --- | --- |
| summary | 4 to 6 items, at most 45 words each | One finding per item with its number and CI or test result. Order: top problem, largest significant change over time, top strength, rating and text mismatch, journey, country exception. Bold (**text**) only for issue or stage names |
| patterns.problems\_title, patterns.strengths\_title | At most 14 words | Names the one or two items with the most reviews, as a finding |
| patterns.caption | At most 70 words | Opens with "One review can mention several problems, so the bars add up to more than the number of reviews." Then names which issues come mostly from low-star reviews and which do not, with counts |
| issues\[\].short\_name | 2 to 4 words | Chart label for the scatter |
| journey.stages\[\].desc | 3 to 6 words | What the stage covers |
| glossary\_examples.\<measure> | At most 50 words | One worked example using numbers from stats.json |

### 12.5 Representative quotes

For each of the 6 problems and 4 strengths with the most reviews, one quote is selected by code:

1. Candidates are the issue's statements under 40 words that passed the quote check and contain no personal data (names, emails, phone numbers, order numbers).
2. The candidate whose issue-phrase embedding is closest to the centre of the issue's group (cosine similarity) is chosen; ties go to higher confidence.
3. The quote is shown exactly as written, in its original language, with an English translation when it is not English. It is never shortened or edited.

### 12.6 Display rules (built into the template)

- Sorting: pattern charts and board by review count or share, descending; categories by net sentiment; κ ascending; teams by share.
- Colours come only from the template's theme tokens; time series colours are assigned by order.
- Hidden when not applicable: Issues over time (fewer than 6 weeks with at least 50 reviews); country filter, coverage toggle and country differences (one country only).
- Formats: shares with one decimal and %, counts with thousands separators, stars with two decimals, p below 0.001 as "< 0.001", differences between shares in percentage points.
- Low-data marks: weeks under 50 reviews drawn hollow; issues with κ below 0.70 flagged "less reliable".

### 12.7 Writing rules

- Describe, never advise: no "should", "recommend", "priority" or "fix".
- Say "reviews" or "reviewers", never "users" or "customers".
- Every number in a text slot matches stats.json and shows its unit.
- Trends, gaps and co-occurrence are described as patterns, not causes.

### 12.8 Conformance checks

| Check | Pass condition |
| --- | --- |
| Data | report\_data.json passes the schema and the renderer's cross-reference, word-limit and wording checks |
| Template | The template file's hash matches the released version |
| Render | The page opens with no script errors and no horizontal scroll at 400 px and 1,200 px, in light and dark themes |
| Layout | Section headings and order match section 12.2 exactly |

## 13. Quality gates

Gates run automatically in step 11 and again in step 14. No gate stops the run; each either retries once or records a flag that appears in the report.

| Gate | Check | Threshold | Automatic action |
| --- | --- | --- | --- |
| Schema | Every record matches its JSON Schema | 100% | Resend the batch once; drop records that still fail and count them |
| Quote | Text span found verbatim in its review | 100% | Retry the statement once; remove it if it still fails |
| Coverage | Share of statements labeled "other" | ≤ 15% | Re-run grouping once with smaller minimum cluster size; flag if still above |
| Agreement, overall | κ on issue between main and second pass | ≥ 0.70 | Flag in report header and reliability section |
| Agreement, per issue | κ per recurring issue | ≥ 0.70 | Mark the issue "less reliable" on the board and its card |
| Sample size | Reviews per country and per version | ≥ 50 country, ≥ 100 version | Exclude from separate display and tests |
| Number audit | Every number in the text matches stats.json | 0 mismatches | Rewrite the sentence from stats.json; flag if unresolved |
| Voice audit | No prescriptive wording | 0 matches | Rewrite the sentence |

## 14. Functional requirements

| ID | Requirement |
| --- | --- |
| FR-1 | Accept an App Store link, numeric app ID or app name as the only required input |
| FR-2 | Resolve a name to one app automatically and record the choice and alternatives in the run record |
| FR-3 | Read and store the app's listing: description, features named in it, category, price, in-app purchases, store rating, version history and release notes |
| FR-4 | Select countries by rating count as defined in section 8, or use the single country given |
| FR-5 | Collect up to 500 reviews per selected country with rating, title, body, date, version and country |
| FR-6 | Remove duplicates, detect language and record each country's date window |
| FR-7 | Split every review into statements and label them with the fields in section 10 |
| FR-8 | Reject any statement whose quote is not found verbatim in its review |
| FR-9 | Discover issues from the data with the three-pass method in section 7; use no predefined issue list |
| FR-10 | Build issue categories and journey stages for each app from its reviews and listing (section 9.6); supply no predefined categories or stages to any model |
| FR-11 | Route every recurring issue to a primary owning team and up to two secondary teams (section 9.5) |
| FR-12 | Report an issue on its own only when it meets the repetition rule |
| FR-13 | Label an independent 10% sample a second time and compute κ |
| FR-14 | Compute every statistic in section 11 with code; no AI-generated numbers |
| FR-15 | Produce the report only by filling report\_data.json and rendering it with the fixed template (section 12); never generate or edit HTML, CSS or chart code during a run |
| FR-16 | Keep country detail in a filter and toggles, not as a primary grouping |
| FR-17 | Explain every statistic used, with a worked example from the same report |
| FR-18 | Describe the specific run, including the derived stages and categories, in the last section of the report |
| FR-19 | Link every quote and every issue to its statement and review IDs |
| FR-20 | Run every quality gate in section 13 and show results in the report |
| FR-21 | Complete without any human approval or question |
| FR-22 | Save all intermediate data and the run record in the run folder |

## 15. Non-functional requirements

| ID | Area | Requirement |
| --- | --- | --- |
| NFR-1 | Run time | Under 30 minutes for 5,000 reviews |
| NFR-2 | Rate limits | No more than 20 calls per minute to Apple's lookup and search services; back off and retry on errors |
| NFR-3 | Reproducibility | Same input, settings, models and prompt versions give the same counts within ±2% per issue; random seeds fixed |
| NFR-4 | Traceability | Every number in the report can be traced to rows in stats.json and to statement IDs |
| NFR-5 | Privacy | Reviewer names are hashed and never shown; only public review data is collected |
| NFR-6 | Languages | Labels work on any review language; issue names and report text are English |
| NFR-7 | Cost | Fast model for extraction, assignment and second pass; strong model only for issue naming and report text |
| NFR-8 | Report | Self-contained HTML under 5 MB, light and dark themes, readable at 400 px width, PDF export |
| NFR-9 | Robustness | A failure in one country or batch does not stop the run; it is retried once and logged |

## 16. Configuration defaults

Stored in `config/settings.yaml`. Every value can be overridden per run.

| Setting | Default |
| --- | --- |
| Candidate countries checked | 50 largest App Store countries |
| Rating coverage target | 80% |
| Countries, minimum and maximum | 3 and 10 |
| Reviews per country | 500 (Apple's maximum) |
| Extraction batch size | 25 reviews |
| Minimum cluster size | 3 phrases |
| Repetition threshold | max(5 reviews, 0.5% of reviews) |
| Categories, minimum and maximum | 5 and 14 |
| Journey stages, minimum and maximum | 4 and 10 |
| Secondary teams per issue, maximum | 2 |
| Second-pass sample | 10% of statements, stratified by issue |
| κ flag threshold | 0.70 |
| "Other" limit | 15% of statements |
| Time chart | Weekly bins; 5 most frequent problems; recent period = last 4 weeks |
| Minimum reviews to show a country, a week as solid | 50 and 50 |
| Minimum group size for tests | 30 reviews |
| Confidence level | 95% |
| Quotes per issue card | 3 |

## 17. Architecture in Claude Code

**Sub-agents** (`.claude/agents/`)

| Agent | Model | Pipeline steps | Skills loaded |
| --- | --- | --- | --- |
| orchestrator | strong | runs 1 to 15 | all |
| statement-extractor | fast | 5 | ux-review-codebook, issue-phrasing |
| issue-namer | strong | 8 | issue-naming, app-structure, team-routing, ux-review-codebook |
| issue-assigner | fast | 9 | ux-review-codebook |
| second-rater | fast, different prompt | 10 | ux-review-codebook |
| report-writer | strong | 13 | report-slots, descriptive-voice, stats-definitions |
| report-auditor | fast | 14 | descriptive-voice |

**Skills** (`.claude/skills/<name>/SKILL.md`)

| Skill | Content |
| --- | --- |
| ux-review-codebook | Statement splitting rules and the fixed label sets 9.1 to 9.4, with 20 worked examples in English, German, French and Spanish |
| issue-phrasing | Rules and good and bad examples for issue phrases and where-in-the-app phrases |
| issue-naming | Rules to name, define, merge and split groups, and to write each issue's short name |
| app-structure | Rules in section 9.6 for building categories and journey stages from the listing, issues and location phrases. Contains rules only, never a list of categories or stages |
| team-routing | The teams and routing rules in section 9.5 |
| stats-definitions | Every measure in section 11 with its formula and conditions |
| report-slots | The text slot rules in section 12.4, the writing rules in 12.7, and the sample report\_data.json as a finished example. Tells report-writer it may only fill text slots |
| descriptive-voice | Allowed and banned wording, number formatting |

**MCP server** (`.mcp.json`): `app-store`, a small custom server with four tools: `search_apps(term, country)`, `lookup_app(id, country)` returning rating count and average, and `get_reviews(id, country, page)`, and get\_listing(id, country) returning the description, price, in-app purchases and version history with release notes from the app's App Store page. It wraps Apple's public search, lookup and customer review feeds and the public app page, and enforces the rate limit.

**Scripts** (`scripts/`, Python): resolve\_app, select\_countries, collect, clean, check\_quotes, group\_phrases, quality\_gate, stats, check\_numbers, render. Libraries: pandas, NumPy, SciPy, statsmodels, scikit-learn, sentence-transformers (multilingual model), hdbscan, langdetect, Jinja2, and a headless browser for PDF export.

**Folder structure**

```
app-review-ux/
  CLAUDE.md
  .mcp.json
  .claude/agents/        orchestrator, statement-extractor, issue-namer,
                         issue-assigner, second-rater, report-writer, report-auditor
  .claude/skills/        ux-review-codebook, issue-phrasing, issue-naming, app-structure,
                         team-routing, stats-definitions, report-slots, descriptive-voice
  config/settings.yaml
  schemas/               review, statement, issue, structure, run,
                         report-data.schema.json
  scripts/               ... , render_report.py
  templates/             report-template.html (fixed, versioned)
                         report_data.sample.json
  runs/<app-id>_<date>/
    raw/ clean/ labels/ issues/ validation/ stats/ run.json
    report/report_data.json, report.html, report.pdf
```

## 18. Acceptance criteria

| ID | Criterion | How it is verified |
| --- | --- | --- |
| AC-1 | One command with an app name produces report.html and report.pdf with no prompts | End-to-end run on 3 test apps: a game, a banking app, a shopping app |
| AC-2 | Every number in the report equals the matching value in stats.json | Number audit reports 0 mismatches |
| AC-3 | Statistics match reference values | Unit tests on a fixed synthetic dataset with known shares, CIs, κ, chi-square and CMH results |
| AC-4 | Issue labels are reliable | On a 200-statement hand-labeled benchmark per test app, issue assignment macro-F1 ≥ 0.75 and overall κ ≥ 0.70 |
| AC-5 | Issues are specific | At least 90% of recurring issue names state what happens and where, checked on the 3 test apps |
| AC-6 | Categories and stages are app-specific | The 3 test apps produce different category and stage sets; every category and stage has reviews behind it; no stage or category name appears in any prompt or skill |
| AC-7 | Team routing is sensible | On the 3 test apps, at least 85% of primary team assignments are judged correct by a reviewer |
| AC-8 | Every quote is verbatim | 100% of quotes in the report found in their source review |
| AC-9 | The report contains no advice | Voice audit finds 0 prescriptive phrases |
| AC-10 | Every statistic is explained | Each measure shown in the report has a row with a worked example from the same report |
| AC-11 | Run time and stability | 5,000 reviews in under 30 minutes; a forced failure in one country does not stop the run |
| AC-12 | Layout | Report passes the conformance checks in section 12.8; reports for the 3 test apps have identical section order, headings and styles |

## 19. Delivery phases

| Phase | Scope | Exit criterion |
| --- | --- | --- |
| 1. Data | Schemas, app-store MCP, resolve, country selection, collection, cleaning | Clean reviews for 3 test apps with correct country windows |
| 2. Labeling | Codebook and phrasing skills, statement extraction, quote check | Extraction passes schema and quote gates on all test apps |
| 3. Issues | Grouping, issue naming, assignment, second pass, quality gate | AC-4 and AC-5 met |
| 4. Statistics | stats.py with unit tests | AC-3 met |
| 5. Report | Report writer, auditor, Notion-style template, PDF export | AC-2, AC-7 and AC-9 met |
| 6. Hardening | End-to-end runs, failure handling, run-time tuning | AC-1, AC-6 and AC-8 met |
| 7. Later | Comparison of two apps, re-runs on new reviews only with a stable issue list, change-point detection | Not part of the first release |
