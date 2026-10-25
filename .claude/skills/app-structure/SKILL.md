---
name: app-structure
description: Rules (PRD section 9.6) for deriving an app's issue categories and ordered journey stages from its App Store listing, its recurring issues and the where-in-the-app phrases. Rules only; no list of categories or stages.
user-invocable: false
---

# App structure: categories and journey stages

Categories and journey stages differ between apps, so they are built on every run from three inputs:
the App Store listing (description, features named in it, category, in-app purchases, release notes),
the issues you named, and the where-in-the-app phrases written for every statement. No list of
categories or stages is given in advance, and none should be assumed from other apps.

## Issue categories
| Rule | Detail |
| --- | --- |
| What a category is | An area of the product the issues belong to, named in the app's own vocabulary |
| How it is formed | Group the issues by product area; every issue belongs to exactly one category |
| Size | Between the `limits.categories` bounds (5 to 14). A category needs at least 2 issues or 2% of reviews; otherwise merge it into the closest area |
| Naming | A noun phrase for the product area, in the words the listing and reviewers use. Never a feeling or a statement type: not "Complaints", "Bugs", "Praise", "Requests", "Other", "General" |
| Evidence | Each category lists the issues it contains; no category exists without reviews behind it |

How to form them
1. Read the listing: which areas does the app itself say it has?
2. Place each issue in the area its subject belongs to. Strengths and problems about the same area share
   a category.
3. Issues about the app as a whole (overall stability, value, speed everywhere) form areas of their own
   when they recur, named for the subject (for example the app's pricing or its overall performance), not
   for the feeling.
4. Check the size rule and merge small areas.

`id` is a lowercase slug; `name` is the display name; `issue_ids` lists its issues.

## Journey stages
| Rule | Detail |
| --- | --- |
| What a stage is | A step a person goes through when using this app, in the order they meet it |
| How it is formed | Draft an ordered journey from the listing, then adjust it with the where-in-the-app phrases: add stages that reviewers mention, drop stages nobody mentions |
| Size | Between the `limits.stages` bounds (4 to 10) ordered stages. "Not tied to a stage" (`none`) exists separately for general statements and is not one of the stages |
| Evidence | Each stage records `source`: `listing_and_reviews` when the listing names it and reviewers mention it, `reviews_only` when only reviewers mention it; `listing_words` holds the listing words it matches (empty for reviews only) |
| Order | `order` 1, 2, 3 ... in the sequence a person meets the stages in a typical use of the app |

How to form them
1. From the description and features, write the path a person takes through this app, start to finish.
2. Compare it with the location phrases and their counts. Keep stages reviewers mention; add frequently
   mentioned moments missing from the draft; drop stages with no mentions.
3. Moments that happen at any time (for example notifications or updating the app) are stages only when
   reviewers mention them often; place them where they usually occur.
4. Each stage gets `name` (2 to 4 words, a step or screen) and `desc` (3 to 6 words, at most 40
   characters, what the stage covers).
5. Give each issue the `stage_id` where most of its statements happen, or `null` when it is not tied to a stage.

The categories and stages are frozen after this step and shown throughout the report (sentiment by
category, the journey map), so they must be understandable to a reader who has never used the app.
