---
name: issue-phrasing
description: Rules and good and bad examples for writing issue phrases (what happens and where, at most 8 words) and where-in-the-app phrases (at most 5 words) for review statements.
user-invocable: false
---

# Issue phrasing

Every statement gets two free-text English phrases. Code groups statements by the similarity of their
issue phrases, so phrases for the same issue must look alike, whatever language the review is in.

## Issue phrase (at most 8 words)
Say **what happens** and, when the review says it, **where**. Write it as a plain description of the
experience, so two reviewers describing the same thing get the same phrase.

Rules
1. At most 8 words. English, whatever the review's language.
2. Subject first, then what happens: "Apple Pay payment fails at checkout", not "Checkout: failing".
3. Be specific: name the feature, screen, action or object the reviewer names.
4. No blame words and no feelings: not "terrible", "lazy developers", "greedy", "stupid", "annoying".
5. No advice and no solutions: describe the problem, not the fix ("Cannot export notes", not "Add export").
6. Praise phrases say what works: "Checkout is fast and simple", "Driver tracking is accurate".
7. Requests say what is missing: "No dark mode available", "Cannot schedule orders for later".
8. Use the same wording for the same thing. Prefer common words: "crashes", "fails", "slow", "missing",
   "logged out", "charged twice", "cannot find", "not shown".
9. Write the phrase for the statement only, not for the whole review.

| Good | Bad | Why bad |
| --- | --- | --- |
| App crashes when opening cart | App is garbage | No subject, a feeling |
| Logged out after every update | Developers broke login again | Blame |
| Delivery fee shown only at payment | Hidden fees scam | Feeling, vague |
| Search filters reset after scrolling | Search | Too short to say what happens |
| Cannot change address after ordering | Please let me change my address after I order | A request in the reviewer's words, too long |
| Video playback stutters on cellular | Bad | Says nothing |
| Ads shown between every level | Add ad-free option | Advice |
| Font too small to read | Make font bigger | Advice |

## Where-in-the-app phrase (at most 5 words)
Name the screen, step or moment the statement refers to, in plain words: "checkout screen", "sign in
screen", "after updating", "opening the app", "search results", "notifications", "subscription page".

Rules
1. At most 5 words, lower case, English.
2. Use the reviewer's moment, not a guess. If the review names no screen or moment, write `general`.
3. Statements about the whole app (overall praise, value, stability in general) are `general`.
4. Prefer the step a person goes through ("paying for an order") or the screen ("payment screen") over
   technical terms ("PaymentViewController").
