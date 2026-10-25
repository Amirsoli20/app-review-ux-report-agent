---
name: team-routing
description: The fixed list of likely owning teams and the routing rules (PRD section 9.5) for assigning each recurring issue one primary and up to two secondary teams.
user-invocable: false
---

# Likely owning team

Each issue is routed to one primary team and up to two secondary teams: the functions that usually own
that kind of problem in a company that builds an app. The label is a routing aid for the reader. It is
not a judgment of any team's work, and the report never says what a team should do.

Use these names exactly:

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

## Routing rules
1. Choose the primary team from the issue's definition, statement type and UX dimension.
2. A bug report whose statements mention an update or a version adds QA and release as a secondary team.
   (Code also applies this rule.)
3. A feature request goes to Product management, unless it is purely visual (UI and visual design) or a
   text change (Content and localization).
4. Strengths are routed the same way, so the reader sees which team's area is praised.
5. Secondary teams are teams that share the cause or the fix surface, at most two, never the primary team again.
   Leave `team_secondary` empty when no other team plausibly shares the issue.
