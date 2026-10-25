---
name: issue-naming
description: Rules to name, define, merge and split phrase groups into specific recurring issues, and to write each issue's id, short name and dominant type.
user-invocable: false
---

# Issue naming

An **issue** is a named, recurring subject shared by many statements. Issues are discovered from the
data on every run; no predefined list exists. You receive groups of similar issue phrases and turn them
into issues.

## Read each group
Use its 20 most central phrases (with counts), its sample quotes, and its mix of types, sentiments and UX
dimensions. The phrases with the highest counts say what most statements in the group are about.

## Merge, split, keep
- **Merge** groups that describe the same issue in different words ("logged out after update" and
  "have to sign in again every time"): one issue lists both groups in `source_groups`.
- **Split** a group that mixes two issues ("payment fails" and "promo code rejected"): create both issues
  and list the group under both; the assigner sorts its statements.
- **Keep apart** praise and problems about the same feature: "Checkout is fast" and "Checkout fails" are
  two issues. Keep apart bugs and requests about the same feature when both recur.
- **Leave out** groups that are noise (greetings, off-topic, unclear). Their statements become "other".
- Every group with at least `repetition_threshold` reviews must belong to an issue.

## Name (at most 8 words)
1. State **what happens and where**: "Apple Pay payment fails at checkout", "Logged out after app update",
   "Delivery fee shown only at payment", "Fast, simple checkout".
2. Specific enough that a designer knows which screen or behaviour it is. Not "Payment problems", not
   "Bugs", not "UX issues".
3. Neutral wording: no blame, no feelings, no advice. Never "users" or "customers".
4. Problems name the failure or the friction; strengths name what works; requests name what is missing
   ("Cannot change address after ordering", "No dark mode").
5. Sentence case, no final period.

## Definition (one sentence)
Says which statements belong to the issue, so another person could apply it: "Payment with Apple Pay
fails, freezes or is declined inside the app." Include the boundary when two issues are close.

## short_name (2 to 4 words, at most 26 characters)
A chart label: "Apple Pay fails", "Logged out", "Late fee display", "Fast checkout".

## issue_id
Lowercase slug, unique, stable and readable: a short area prefix plus the subject, for example
"pay-applepay", "acct-logout", "s-checkout" for a strength. Letters, digits and hyphens only.

## dominant_type and ux_dimension
`dominant_type` is the statement type most of the group's statements have (codebook values: Bug report,
Complaint, Feature request, Praise, Question, Comparison, Other). `ux_dimension` is the one dimension that
fits most of its statements.

## Coverage and size
Aim for issues that are as specific as the phrases allow while still recurring. A good list for a few
thousand reviews has roughly 30 to 120 issues; small groups that fit an existing issue are merged into it
rather than made into tiny issues.
