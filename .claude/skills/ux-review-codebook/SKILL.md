---
name: ux-review-codebook
description: Codebook for labeling App Store review statements - splitting rules and the fixed label sets (statement type, sentiment, severity, UX dimension) with 20 worked examples in English, German, French and Spanish. Used by statement-extractor, issue-assigner, second-rater and issue-namer.
user-invocable: false
---

# UX review codebook

The method is aspect-based sentiment analysis. Each review is split into **statements**; each statement
is one claim about one subject, labeled with the feeling it expresses.

## Splitting rules
1. A new statement starts when the **subject** or the **feeling** changes.
   "Love the design but payment failed twice" is two statements (design, positive; payment, negative).
2. Repeated mentions of the same subject in one review stay **one** statement. Quote the clearest mention.
3. The title is read with the body. A title that repeats the body adds no statement; a title with its own
   claim ("Crashes constantly") is a statement, quoted from the title.
4. Each statement has an exact quote (text span) from the review, in the original language.
5. A review with no meaningful text ("ok", "👍", "5 stars", random letters) produces no statements.
6. Ratings, emojis and greetings alone are not statements. Generic overall praise ("Great app!") is one
   Praise statement about the app as a whole.

## Statement type (pick one)
| Type | Definition | Example |
| --- | --- | --- |
| Bug report | Something does not work as intended | "The app crashes when I open my cart" |
| Complaint | Works as built, but the reviewer dislikes how | "The delivery fee only appears on the last screen" |
| Feature request | Asks for something the app does not offer | "Please add dark mode" |
| Praise | Says something works well or is liked | "Checkout takes ten seconds" |
| Question | Asks how to do something or why something happens | "How do I change my address?" |
| Comparison | Compares the app with another app or an earlier version | "The old version was much faster" |
| Other | None of the above (greetings, off-topic text) | "First review!" |

Bug report or Complaint: if the reviewer says it *fails*, *errors*, *crashes*, *freezes*, *won't*, it is a
Bug report. If it works but they dislike the design, price, policy, wording or effort, it is a Complaint.
A Comparison that says the app got worse is still a Comparison (sentiment Negative).

## Sentiment (pick one)
| Value | Definition |
| --- | --- |
| Positive | The statement expresses approval or satisfaction |
| Negative | The statement expresses disapproval, frustration or harm |
| Neutral | The statement is factual or a request with no clear feeling |
| Mixed | One statement expresses both approval and disapproval of the same subject |

Feature requests are Neutral unless they carry frustration ("Still no dark mode after years!" is Negative).

## Severity (Bug report and Complaint only; null for every other type)
| Level | Definition |
| --- | --- |
| Blocker | The reviewer could not finish a task, lost money or data, or stopped using the app |
| Major | The task was finished only with significant effort or a workaround |
| Minor | Annoying, but the task was finished normally |
| Cosmetic | Appearance or wording only; no effect on the task |

Judge severity from what the reviewer reports, not from how angry they sound. "Deleted the app" or
"charged twice" is Blocker. A workaround mentioned ("had to use my card instead") is Major.

## UX dimension (pick one)
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

## Worked examples
Each example shows the review, then each statement as: quote → issue phrase · location phrase · type ·
sentiment · severity · dimension.

**1 (English, banking app, 1★)** "Face ID stopped working after the update. Now I type my password every time. Support never answered."
- "Face ID stopped working after the update" → Face ID sign in fails after update · sign in screen · Bug report · Negative · Major · Reliability
- "Support never answered" → Support does not answer messages · contacting support · Complaint · Negative · Minor · Support

**2 (English, game, 4★)** "Really fun levels and the art is gorgeous. Too many ads between rounds though."
- "Really fun levels" → Levels are fun to play · general · Praise · Positive · null · Functionality
- "the art is gorgeous" → Art style looks good · general · Praise · Positive · null · Visual design
- "Too many ads between rounds though" → Ads shown between every round · between rounds · Complaint · Negative · Minor · Value and pricing

**3 (English, notes app, 2★)** "Sync is broken. Sync is broken. I lost a whole week of notes!!"
- "I lost a whole week of notes!!" → Notes lost during sync · syncing notes · Bug report · Negative · Blocker · Reliability
(Repeated mentions of sync stay one statement; the clearest quote is chosen.)

**4 (English, food delivery, 5★)** "Please add a way to schedule orders for later."
- "Please add a way to schedule orders for later." → Cannot schedule orders for later · placing an order · Feature request · Neutral · null · Functionality

**5 (English, fitness app, 3★)** "How do I export my workouts? The old version had a button for it."
- "How do I export my workouts?" → Unclear how to export workouts · workout history · Question · Neutral · null · Usability
- "The old version had a button for it." → Export button removed in new version · workout history · Comparison · Negative · null · Functionality

**6 (German, banking app, 1★)** "Seit dem Update stürzt die App beim Öffnen ab. Überweisungen unmöglich."
- "Seit dem Update stürzt die App beim Öffnen ab." (translation: "Since the update the app crashes on opening.") → App crashes on launch after update · opening the app · Bug report · Negative · Blocker · Reliability
- "Überweisungen unmöglich." (translation: "Transfers impossible.") → Transfers cannot be made · making a transfer · Bug report · Negative · Blocker · Reliability

**7 (German, shopping app, 4★)** "Schnelle Lieferung, aber die Schrift ist viel zu klein."
- "Schnelle Lieferung" (translation: "Fast delivery") → Orders arrive quickly · delivery · Praise · Positive · null · Functionality
- "die Schrift ist viel zu klein" (translation: "the font is far too small") → Text too small to read · general · Complaint · Negative · Minor · Accessibility

**8 (German, streaming app, 2★)** "Das Abo ist teurer geworden und man kann nicht mehr offline schauen."
- "Das Abo ist teurer geworden" (translation: "The subscription has become more expensive") → Subscription price increased · subscription · Complaint · Negative · Minor · Value and pricing
- "man kann nicht mehr offline schauen" (translation: "you can no longer watch offline") → Offline viewing no longer available · downloads · Comparison · Negative · null · Functionality

**9 (German, game, 5★)** "Top!"
- "Top!" → App liked overall · general · Praise · Positive · null · Functionality

**10 (German, travel app, 3★)** "Warum werden meine Buchungen nicht angezeigt? Ansonsten gut."
- "Warum werden meine Buchungen nicht angezeigt?" (translation: "Why are my bookings not shown?") → Bookings missing from bookings list · my bookings · Question · Negative · null · Reliability
- "Ansonsten gut." (translation: "Otherwise good.") → App liked overall · general · Praise · Positive · null · Functionality

**11 (French, delivery app, 1★)** "Commande jamais arrivée et impossible d'être remboursé."
- "Commande jamais arrivée" (translation: "Order never arrived") → Order never delivered · delivery · Complaint · Negative · Blocker · Functionality
- "impossible d'être remboursé" (translation: "impossible to get a refund") → Refund cannot be obtained · refund request · Complaint · Negative · Blocker · Support

**12 (French, photo app, 4★)** "Les filtres sont superbes mais l'export est un peu lent."
- "Les filtres sont superbes" (translation: "The filters are superb") → Filters look good · editing a photo · Praise · Positive · null · Visual design
- "l'export est un peu lent" (translation: "exporting is a bit slow") → Photo export is slow · exporting a photo · Complaint · Negative · Minor · Performance

**13 (French, banking app, 2★)** "L'application demande l'accès à mes contacts, pourquoi ?"
- "L'application demande l'accès à mes contacts, pourquoi ?" (translation: "The app asks for access to my contacts, why?") → Contacts permission requested without reason · permission prompt · Question · Negative · null · Trust and safety

**14 (French, language app, 5★)** "Bien mieux que les autres applis que j'ai essayées."
- "Bien mieux que les autres applis que j'ai essayées." (translation: "Much better than the other apps I tried.") → Better than other apps tried · general · Comparison · Positive · null · Functionality

**15 (French, social app, 3★)** "Le mode sombre est joli, mais certains textes deviennent illisibles."
- "Le mode sombre est joli, mais certains textes deviennent illisibles." (translation: "Dark mode is nice, but some text becomes unreadable.") → Some text unreadable in dark mode · dark mode · Complaint · Mixed · Cosmetic · Visual design
(One subject, both feelings: one Mixed statement.)

**16 (Spanish, ride app, 1★)** "Me cobraron dos veces el mismo viaje."
- "Me cobraron dos veces el mismo viaje." (translation: "They charged me twice for the same ride.") → Ride charged twice · payment after ride · Bug report · Negative · Blocker · Value and pricing

**17 (Spanish, music app, 5★)** "Las listas recomendadas son increíbles, siempre descubro música nueva."
- "Las listas recomendadas son increíbles" (translation: "The recommended playlists are amazing") → Recommended playlists match taste · recommendations · Praise · Positive · null · Functionality

**18 (Spanish, banking app, 2★)** "El chat de ayuda es un bot que no entiende nada."
- "El chat de ayuda es un bot que no entiende nada." (translation: "The help chat is a bot that understands nothing.") → Help chat bot does not understand · help chat · Complaint · Negative · Major · Support

**19 (Spanish, game, 4★)** "Me encanta, pero ojalá hubiera modo multijugador."
- "Me encanta" (translation: "I love it") → App liked overall · general · Praise · Positive · null · Functionality
- "ojalá hubiera modo multijugador" (translation: "I wish there were a multiplayer mode") → No multiplayer mode available · general · Feature request · Neutral · null · Functionality

**20 (Spanish, shopping app, 3★)** "Los botones se superponen en mi iPhone SE y no puedo pagar."
- "Los botones se superponen en mi iPhone SE y no puedo pagar." (translation: "The buttons overlap on my iPhone SE and I can't pay.") → Overlapping buttons block payment on small screens · payment screen · Bug report · Negative · Blocker · Visual design
