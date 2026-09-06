# MASTER WORD INTELLIGENCE 2 — AUTHORITATIVE WORK SPECIFICATION

> Repository-local authoritative specification for the Word Intelligence 2
> engineering batch. Appended in sequential parts as provided.
>
> **implementation constraints (from the carrier message):**
> - The current Word Intelligence system must be **EXTENDED, not replaced**.
> - Primary objective: a huge curated master vocabulary with extremely
>   selective, topic-tight puzzle generation.
> - Precision > raw database size. Topic coherence > random variety.
>   Human decisions > classifier decisions. Curated data > dictionary noise.
>   Safe dry run > automatic rewrite.
> - Do not commit or push. Do not modify production themes. Do not modify
>   data/books.db. Keep all repair operations dry-run only.

---
============================================================
MASTER WORD INTELLIGENCE 2.0
============================================================

MULTI-ANCHOR SEMANTIC ENGINE
+ MASTER WORD BASE EXPANSION
+ LIBRARY QUALITY SYSTEM
+ FULL STABILIZATION

Repository:

C:\Users\jorda\Desktop\Word Search Creator\kdp-puzzle-engine

This is intended to be a LARGE, SUBSTANTIAL engineering and data-quality batch.

Take the time necessary to inspect the repository, understand the current Word Intelligence architecture, analyze the actual data, implement carefully, run extensive tests, and validate results against the real word-bank/theme library.

Do NOT rush this.

The goal is not to maximize lines of code.

The goal is to materially improve the intelligence, precision, breadth, usefulness, and long-term maintainability of the application's word database.

============================================================
PRIMARY OBJECTIVE
============================================================

Turn the existing Word Intelligence system into an exceptionally strong foundation for generating tightly themed, commercially useful word-search books.

The system should become much better at answering:

1. What does this book/theme actually mean?
2. What subtopics legitimately belong inside that theme?
3. Which words strong belong?
4. Which words weakly belong?
5. Which words are ambiguous?
6. Which words are genuinely off-topic?
7. Which words are technically related but poor word-search choices?
8. Which words are useful enough to add to the curated master database?
9. Which existing word-bank entries should be classified, reviewed, replaced, or rejected?
10. Can we generate hundreds of clean puzzles from a topic without producing random dictionary noise or excessive repetition?

The intended pipeline:

TOPIC
→ SUBTOPICS
→ CURATED WORD POOL
→ INTELLIGENT SELECTION
→ TIGHTLY RELATED PUZZLES

NOT:

TOPIC
→ grab anything vaguely related
→ fill puzzle slots

The master database may become extremely large.

Individual puzzles must remain selective and intentional.

============================================================
NON-NEGOTIABLE SAFETY RULE
============================================================

DO NOT MASS-REWRITE THE EXISTING THEME LIBRARY DURING THIS BATCH.

The current repair system exposed an important weakness:

single-anchor topic judgment is too narrow for many broad books.

The previous inventory reported approximately:

236 themes
171 FAIL
15 PASS_WITH_NOTES
53 PASS

and tens of thousands of "off_topic" findings.

Many of these may be false positives caused by an overly narrow interpretation of multi-dimensional themes.

For example, a broad Arizona book can legitimately contain concepts such as desert, cactus, saguaro, canyon, copper, rodeo, Phoenix, Tucson, Grand Canyon, Sonoran, ranching, sunsets, monsoons, Route 66, appropriate Southwestern cultural terminology, Southwestern food, wildlife, landmarks, history, outdoor recreation, and state geography.

These do not all need to be synonyms of "Arizona."

Likewise, broad subjects such as Christmas, 1990s, BBQ, National Parks, Gardening, Ocean Life, American Nostalgia, Home Cooking, Weather, and History are multi-dimensional.

Improve the intelligence BEFORE trusting repair recommendations.

All repair operations must remain dry-run by default.

DO NOT invoke a write/apply operation against production themes during this batch.
============================================================
REPOSITORY SAFETY / BASELINE
============================================================

Before substantive implementation:

1. Read AGENTS.md completely.
2. Inspect git status.
3. Confirm current branch and HEAD.
4. Confirm generated Word Intelligence artifacts are properly ignored.
5. Do not modify:
   - .venv/
   - production generated books
   - credentials
   - unrelated publishing/integration code
6. Record SHA-256 of data/books.db.
7. Record the current full pytest count.
8. Inspect all current word_intelligence modules before designing implementations.
9. Inspect:
   - word_intelligence/
   - cleanup_theme_library.py
   - build_master_word_bank.py
   - relevant GUI integration
   - tests/test_word_intelligence*
   - taxonomy/config/curated data
   - approved_topic_links
   - decision logs
   - repair plan architecture
10. Preserve existing working behavior unless an actual defect is demonstrated.

Prefer additive evolution.

Do NOT create a second competing Word Intelligence system.
============================================================
PART A: MULTI-ANCHOR THEME UNDERSTANDING
============================================================

This is the highest-priority technical improvement.

Replace or extend narrow single-anchor theme judgment with a MULTI-ANCHOR theme profile.

Do NOT merely add more manual keywords.

Create a reusable domain concept such as:

ThemeProfile
TopicProfile
SemanticThemeProfile

Choose naming consistent with the existing codebase.

A theme profile should be capable of describing a PRIMARY TOPIC plus legitimate:

SUBTOPICS
CONCEPT CLUSTERS
GEOGRAPHIC CLUSTERS
ERA/TIME CLUSTERS
ACTIVITY CLUSTERS
OBJECT CLUSTERS
PEOPLE/ROLE CLUSTERS
CULTURAL CLUSTERS
NATURE/WILDLIFE CLUSTERS
FOOD CLUSTERS
TERMINOLOGY/VOCABULARY CLUSTERS

where appropriate.

Not every theme uses every cluster type.

Example:

ARIZONA

Primary:
Arizona

Possible legitimate anchors:

Sonoran Desert
Grand Canyon
Phoenix
Tucson
Southwest
Native wildlife
desert plants
mining/copper
Old West
Route 66
ranching
monsoon/weather
outdoor recreation
geography
landmarks

A word that matches any strong legitimate anchor should NOT automatically be
considered off-topic.

The implementation must be deterministic and explainable.

Avoid opaque black-box scoring.

A developer or human reviewer must be able to determine WHY a word was
considered relevant.

============================================================
PART B: HIERARCHICAL TAXONOMY
============================================================

The current taxonomy already organizes raw topics.

PRESERVE IT.

Extend it carefully to support:

TOPIC
→ SUBTOPIC
→ OPTIONAL CONCEPT CLUSTER

Examples:

FOOD
→ BBQ & GRILLING
   → meats
   → equipment
   → techniques
   → sauces
   → smoke woods
   → side dishes

NATURE
→ OCEAN LIFE
   → mammals
   → fish
   → crustaceans
   → mollusks
   → habitats
   → ocean geography

NOSTALGIA
→ 1990s
   → technology
   → toys
   → television
   → music culture
   → school life
   → fashion
   → slang
   → games
   → household objects

GEOGRAPHY
→ ARIZONA
   → cities
   → landmarks
   → deserts
   → plants
   → wildlife
   → history
   → culture
   → recreation

Avoid making hundreds of tiny unusable categories.

The taxonomy must help puzzle generation, not become an academic ontology.

Existing canonical topic identifiers and approved relationships must remain
compatible unless a demonstrated defect requires a migration.

If migration would be destructive or reinterpret human-approved decisions,
STOP under the project's stop conditions rather than proceeding silently.
============================================================
PART C: WORDS MAY BELONG TO MULTIPLE TOPICS
============================================================

A word must be able to legitimately belong to more than one topic/subtopic.

Examples:

APPLE

Food → Fruit
Technology → Companies/Products
Gardening → Fruit Trees

MUSTANG

Animals → Horses
Automotive → Cars
American West → Culture

JAGUAR

Animals → Big Cats
Automotive → Brands

Do NOT force every word into exactly one category.

Where consistent with the current architecture, relationships should support:

word
topic
subtopic
confidence
provenance
optional reason/signal

Use the existing approved-link architecture where practical.

Preserve human-approved relationships through regeneration.

Human decisions must outrank automated classification output.

============================================================
PART D: CONTEXTUAL AMBIGUITY
============================================================

Expand the existing ambiguity system.

A word should not be considered universally "good" or "bad".

Suitability depends on context.

Create or extend concepts to distinguish something equivalent to:

UNAMBIGUOUS
CONTEXTUAL
CONTEXTUAL_HIGH
HIGHLY_AMBIGUOUS

When a contextual word is selected, surrounding puzzle words should reinforce
the intended meaning.

Example:

APPLE in a fruit puzzle surrounded by:
ORCHARD
PEAR
PEACH
SEED
is coherent.

APPLE surrounded by:
LAPTOP
SOFTWARE
IPHONE
DEVICE

represents a different sense.

The system should avoid accidentally mixing unrelated senses within the same
puzzle.

Implement enough foundation during this batch to make contextual selection
possible and testable.
============================================================
PART E: PHRASE SUPPORT
============================================================

Ensure that the intelligence system can support useful phrases, not only
single dictionary words.

Examples:

GRAND CANYON
ROUTE SIXTY SIX / ROUTE 66 according to existing normalization rules
SMOKE RING
CAST IRON
ROLLER SKATES
VIDEO STORE
FAMILY COMPUTER

Follow existing puzzle normalization constraints.

Store/display human-readable phrase forms while allowing puzzle generation to
normalize them appropriately.

Avoid absurdly long phrases.

Phrase handling must remain deterministic and compatible with existing puzzle
generation.

============================================================
PART F: TRADEMARK / BRAND SEMANTIC SEPARATION
============================================================

Do not simply delete all brands.

Some topics legitimately require culturally recognizable brand/product
vocabulary, particularly:

1990s
2000s
technology
toys
gaming
nostalgia

However, commercial publishing may carry risk.

Trademark/brand status must remain a SEPARATE signal.

The system must be capable of representing:

semantic relevance = HIGH

while simultaneously:

commercial/trademark caution = REVIEW

Do not conflate semantic relevance with legal/commercial suitability.

Existing safety/trademark protections must not be weakened.
============================================================
PART G: DATA PROVENANCE
============================================================

Every promoted or approved relationship should remain explainable.

Preserve existing provenance concepts and extend only when necessary.

Possible provenance categories include:

existing curated bank
dictionary classifier
human approval
theme evidence
derived relationship
manual addition

Human-approved decisions must survive rebuild/regeneration.

Never silently overwrite a human decision with classifier output.

============================================================
PART H: CHECKPOINT / SESSION RECOVERY SYSTEM
============================================================

This project may exceed a single model/provider session.

Maintain ONE generated progress file during implementation:

out/word_intelligence_reports/CLINE_WORK_PROGRESS.md

This file is recovery information and must remain outside Git.

Periodically update it at meaningful milestones with:

- specification being implemented
- work completed
- current implementation stage
- important architectural decisions
- bugs discovered
- files intentionally modified
- tests already passing
- real-data validation already performed
- remaining tasks
- current books.db SHA-256 safety state
- confirmation that production themes remain untouched
- confirmation that no repair has been applied
- any blockers or stop-condition risks

Overwrite/update this same checkpoint rather than creating many checkpoint
files.

The checkpoint should allow another Cline/model session to resume the job
without repeating the entire repository investigation.

If the current provider/session approaches a limit, preserve useful recovery
information there before stopping whenever technically possible.

============================================================
END PART 1 OF 5
============================================================
============================================================
PART I — WORD QUALITY / PUZZLE-WORTHINESS 2.0
============================================================

Expand puzzle-worthiness beyond simple topic membership.

Create or extend a reusable quality score/profile.

Potential signals include:

- topic relevance
- subtopic relevance
- confidence
- commonness/familiarity
- length
- character cleanliness
- phrase length
- ambiguity
- trademark sensitivity
- safety
- proper noun status
- educational value
- visual/concrete quality
- repetition risk
- word-search usability

Do not pretend subjective scores are objective scientific truth.

Keep individual signals inspectable.

The system should be able to distinguish something equivalent to:

EXCELLENT
GOOD
ACCEPTABLE
REVIEW
REJECT

Examples of poor candidates:

- random obscure dictionary terms
- extremely technical words in a general-audience puzzle
- single letters
- garbled text
- punctuation-heavy strings
- URLs
- codes
- meaningless abbreviations
- words unrelated to the chosen sense of a topic
- excessive trademark dependence

A word being in a dictionary is NEVER sufficient reason to include it in a puzzle.

============================================================
PART J — MASTER WORD DATABASE EXPANSION
============================================================

This should be a major part of the job.

The current store reportedly contains approximately:

16,223 trusted records
370,000 dictionary entries

The goal is NOT to classify all 370,000 entries regardless of usefulness.

The goal is to extract as many HIGH-QUALITY, PUZZLE-WORTHY words and phrases as practical.

Analyze the dictionary/store progressively.

Use the existing signals/classifier/store architecture.

Conceptual pipeline:

RAW DICTIONARY
→ lexical/basic quality gate
→ familiarity/commonness gate
→ topic candidate generation
→ multi-signal classification
→ topic/subtopic assignment
→ ambiguity analysis
→ puzzle-worthiness
→ confidence
→ review/approval tier

Do not promote weak dictionary noise merely to increase database size.

QUALITY > RAW COUNT.

The master database may become extremely large.

Individual puzzles must remain selective and intentional.
============================================================
PART K — BROAD INTELLIGENCE VS PRODUCTION ELIGIBILITY
============================================================

Maintain a strong distinction between:

DATABASE KNOWLEDGE

and

PRODUCTION VOCABULARY

The intelligence system may understand that a word is semantically related to a topic.

That does NOT mean the word is automatically suitable for a customer-facing puzzle.

Create or preserve a production-eligibility concept.

Automatic puzzle use should require something equivalent to:

- sufficient topic confidence
- acceptable puzzle-worthiness tier
- no unresolved ambiguity conflict
- no unresolved trademark/safety restriction
- no human rejection
- appropriate audience/difficulty
- acceptable phrase/word length
- appropriate repetition history

REVIEW and REJECT words must never automatically enter production pools.

Specialized words may be usable only when the theme/audience supports them.

============================================================
PART L — FAMILIARITY / RECOGNIZABILITY
============================================================

Add or improve a familiarity/recognizability signal.

Do NOT confuse general frequency with puzzle usefulness.

For example:

THE

is common but useless for a themed puzzle.

BRISKET

may be less frequent globally but excellent for BBQ.

Use available offline evidence such as:

- production usage
- trusted theme occurrences
- curated topic sources
- dictionary frequency bands
- grade-band data
- word structure
- common vocabulary lists already available in the repository

Treat familiarity as ONE signal rather than the entire quality score.

============================================================
PART M — ANCHOR / SUPPORT / SPECIALTY ROLES
============================================================

Classify strong words by role where useful:

ANCHOR
Immediately recognizable, central theme terms.

SUPPORT
Clearly relevant words that add variety.

SPECIALTY
More specific vocabulary that adds depth.

Example BBQ:

ANCHOR:
GRILL
RIBS
BRISKET
SMOKER
SAUCE

SUPPORT:
HICKORY
TONGS
MARINADE
CHARCOAL

SPECIALTY:
PELLET
BARK
OFFSET
SPATCHCOCK

Commercial puzzle books should use a sensible mix.

Do not allow a general-audience book to become dominated by obscure specialty vocabulary.

============================================================
PART N — TOPIC EXCLUSIVITY / DISTINCTIVENESS
============================================================

Introduce or extend a topic-specific distinctiveness/exclusivity signal.

Some words are broad:

FIRE
HOT
OUTDOOR

They may apply to BBQ, camping, summer, survival, etc.

Other words are more distinctive:

BRISKET
SMOKER
MESQUITE

For tightly themed books, prefer words that strongly evoke the chosen theme while retaining enough broad anchors for accessibility.

This does NOT mean a word may only belong to one topic.

It measures something like:

"How strongly does this word make the reader think of THIS topic?"

Use this as one ranking signal for production selection.
============================================================
PART O — COVERAGE / CAPACITY ENGINE
============================================================

For every canonical topic/subtopic calculate useful production capacity.

We need to know:

Topic: Gardening

Excellent words: X
Good words: X
Acceptable words: X
Review/Ambiguous: X

Safe unique pool: X

Estimated capacity:

12-word puzzles: X
15-word puzzles: X
20-word puzzles: X

Also calculate realistic capacity with repetition constraints.

A topic with 500 associated words is not necessarily capable of 100 high-quality 20-word puzzles if only 80 are strongly relevant.

Create meaningful capacity metrics.

Capacity should help answer:

Can this niche support:

- 48 puzzles?
- 50 puzzles?
- 100 puzzles?
- 12 words each?
- 20 words each?

without dropping below quality standards.

============================================================
PART P — SELECTION STRICTNESS
============================================================

The master database should be LARGE.

Actual puzzle pools should be SELECTIVE.

Build a reusable pool-selection concept with modes equivalent to:

STRICT
BALANCED
BROAD

STRICT:
Primary topic plus only highly relevant approved subtopics/clusters.

BALANCED:
Primary topic plus normal legitimate supporting clusters.

BROAD:
Allows broader related vocabulary but still excludes random filler.

Default commercial behavior should favor tight relevance.

Do not allow a larger database to make individual puzzles sloppier.

============================================================
PART Q — BOOK-SPECIFIC WORD POOL BUILDER
============================================================

Create or extend a production pool-builder abstraction.

Conceptually:

build_word_pool(
    topic,
    subtopics,
    audience,
    difficulty,
    puzzle_count,
    words_per_puzzle,
    repetition_policy,
    series_context,
    strictness
)

The exact API should follow existing architecture rather than forcing this signature.

The output should be a curated candidate pool.

Selection priorities should include:

1. topic confidence
2. puzzle-worthiness
3. production eligibility
4. audience/difficulty suitability
5. subtopic balance
6. ambiguity safety
7. trademark/safety rules
8. word/phrase length
9. repetition history
10. cross-book overlap where available

Do not have Guided Builder or Theme Builder select directly from raw dictionary noise.
============================================================
PART R — PUZZLE COHERENCE
============================================================

Improve selection so an individual puzzle feels like a mini-theme rather than 12 random words from a giant topic.

Example:

BBQ book

Puzzle A:
BRISKET
SMOKER
HICKORY
BARK
RUB
LOW SLOW
PITMASTER
THERMOMETER
SMOKE RING
BUTCHER PAPER
RESTING
SLICING

Puzzle B:
BURGER
GRILL
CHARCOAL
BUN
CHEDDAR
PATTY
ONION
PICKLES
SPATULA
SEAR
KETCHUP
FLAME

Both belong to BBQ, but each puzzle has internal coherence.

Design or improve a cluster-aware pool builder capable of this behavior.

Preserve deterministic generation when a seed is supplied.

============================================================
PART S — SUBTOPIC BALANCING
============================================================

Broad themes should spread vocabulary across meaningful subtopics.

Example:

TEXAS

Potential legitimate subtopics:

cities
history
landmarks
food
wildlife
geography
culture
sports
industry
ranching
weather
travel

Avoid creating 100 puzzles dominated almost entirely by one subtopic such as city names.

Subtopics should derive from real taxonomy/data evidence.

Do not invent unsupported subtopics merely for numerical balance.

============================================================
PART T — REPETITION / DIVERSITY ENGINE
============================================================

Commercial 50/100-puzzle books should not excessively recycle the same vocabulary unless necessary.

Track:

- word usage across the book
- subtopic usage
- cluster usage
- recent-puzzle reuse
- high-frequency anchor reuse

Support configurable constraints such as:

- minimum puzzles before reuse
- maximum total appearances
- prefer unused
- prefer underused
- avoid identical word combinations

Do not make generation impossible for narrow niches.

Degrade gracefully and report when repetition becomes necessary.

============================================================
PART U — CROSS-PUZZLE QUALITY SCORING
============================================================

Create a way to score an entire proposed book, not only individual words.

Possible metrics:

- topic purity
- subtopic coverage
- word diversity
- repetition rate
- ambiguity rate
- weak-word rate
- cluster balance
- puzzle coherence
- capacity stress

Produce an overall quality report.

Example:

Arizona Word Search

Topic Purity: 98.4%
Unique Vocabulary: 1,327
Repeated Words: 73
Weak/Review Words: 8
Subtopics Represented: 14
Puzzle Coherence: A
Overall: A

Do not fabricate precision.

Document how each metric is calculated.
============================================================
PART V — CROSS-BOOK / SERIES REPETITION
============================================================

Where practical with existing architecture, extend overlap awareness across:

- books
- series
- editions
- related themes

Distinguish:

EXPECTED overlap

from:

EXCESSIVE overlap

Example:

GRILL appearing in several BBQ-related books is reasonable.

40% identical vocabulary between two books marketed as substantially different is a warning.

Do not automatically block reasonable overlap.

Provide measurable warnings or quality signals.

============================================================
PART W — AGE / AUDIENCE SUITABILITY FOUNDATION
============================================================

Do not build a large educational classification platform.

But preserve or add a lightweight audience-suitability foundation for:

- kids
- general
- adults
- seniors
- educational

A word may be semantically correct but too obscure or advanced for a children's puzzle.

Use existing grade-band/audience metadata where possible.

Do not require every WordRecord to have perfect age metadata.

============================================================
PART X — DATA QUALITY CHECKS
============================================================

Build or expand automated checks for:

- duplicates
- case-only duplicates
- punctuation variants
- plural/singular near-duplicates
- obvious misspellings
- garbled strings
- numbers-only entries
- URLs
- HTML remnants
- control characters
- extreme lengths
- empty topic assignments
- orphan subtopics
- invalid taxonomy references
- conflicting human decisions
- impossible confidence values
- duplicate topic links
- bad provenance
- safety/trademark inconsistencies

Do not blindly merge linguistic variants when they represent legitimate separate puzzle entries.

============================================================
PART Y — DATABASE QUERY / EXPLORATION BACKEND
============================================================

Provide efficient read-only querying of curated word intelligence.

The backend should eventually support questions such as:

- show all Excellent Arizona words
- show Arizona > Wildlife
- show words shared by Arizona and Desert
- show ambiguous Technology words
- show topics with fewer than 200 Good-or-better words
- show high-frequency unclassified dictionary candidates
- show words never used in a theme

Prefer existing store/index architecture.

Do not introduce a heavyweight database dependency.

============================================================
PART Z — SCALE / PERFORMANCE FOR WORD EXPANSION
============================================================

The source dictionary is approximately 370,000 entries.

Design candidate extraction and querying for that scale.

Avoid accidental:

every-word × every-topic × every-theme

processing when candidate narrowing can be used.

Consider where useful:

- normalized indexes
- inverted token indexes
- topic lexicons
- candidate narrowing
- cached co-occurrence
- incremental classification
- changed-word-only rechecks
- cached statistics

Cache only deterministic/rebuildable information.

Generated caches must not pollute Git.

Correctness and precision remain more important than micro-optimization.

============================================================
END PART 2 OF 5
============================================================
==============================
BEGIN PART 3 OF 5
==============================

MASTER WORD INTELLIGENCE 2.0
PART 3 — MASTER DATABASE EXPANSION, CAPACITY, EXCLUSIVITY, COHERENCE, DIVERSITY, AND BOOK QUALITY

Continue treating this specification as one authoritative work order.

DO NOT IMPLEMENT YET.

Append this entire PART 3 verbatim to:

docs/MASTER_WORD_INTELLIGENCE_2_SPEC.md

Do not paraphrase, summarize, restructure, reinterpret, or replace any text in this part.

============================================================
PART F — MASTER WORD DATABASE EXPANSION
============================================================

This should be a major part of the job.

The existing store reportedly includes approximately:

16,223 trusted records
370,000 dictionary entries

The goal is NOT to classify all 370,000 entries regardless of usefulness.

The goal is to extract as many HIGH-QUALITY, PUZZLE-WORTHY words and phrases as practical.

Analyze the dictionary/store and progressively identify candidates.

Use the existing signals/classifier architecture.

Potential pipeline:

RAW DICTIONARY
→ lexical/basic quality gate
→ familiarity/commonness gate
→ topic candidate generation
→ multi-signal classification
→ topic/subtopic assignment
→ ambiguity analysis
→ puzzle-worthiness
→ confidence
→ review/approval tier

Do not promote weak dictionary noise just to increase database size.

QUALITY > RAW COUNT.

But also do not remain artificially tiny.

We want a large curated database capable of supporting many niches.

The long-term objective is to create one of the strongest practical word databases possible for commercial word-search creation.

This means the system should go through as much of the available dictionary vocabulary as is practical and determine which entries are actually useful.

However, the existence of a word in the source dictionary is NOT sufficient reason to promote it.

The system must remain selective.

The master database may eventually contain a very large number of words and phrases, but every promoted entry should provide legitimate value to one or more topics or subtopics.

Where practical, distinguish between:

- raw dictionary vocabulary
- potentially useful vocabulary
- classified vocabulary
- curated/approved vocabulary
- rejected/noise vocabulary

Do not destroy or discard raw dictionary data merely because an entry is not promoted.
============================================================
PART G — COVERAGE / CAPACITY ENGINE
============================================================

For every canonical topic/subtopic, calculate usable capacity.

We need to know things such as:

Topic: Gardening

Excellent words: X
Good words: X
Acceptable words: X
Ambiguous/review: X

Safe unique pool: X

Estimated capacity:
12-word puzzles: X
15-word puzzles: X
20-word puzzles: X

Also calculate practical capacity with repetition constraints.

A database with 500 words is not necessarily capable of 100 high-quality 20-word puzzles if only 80 are highly relevant.

Create meaningful capacity metrics.

Capacity calculations should distinguish raw vocabulary count from genuinely usable commercial puzzle capacity.

Where practical, account for:

- quality tiers
- strictness level
- ambiguity
- trademark/commercial caution
- word reuse limits
- cluster/subtopic distribution
- required puzzle size
- requested puzzle count

Do not claim a topic can support a high-quality large book merely because the mathematical number of word slots can technically be filled.

============================================================

PART H — EXCLUSIVITY / TIGHTNESS CONTROL

============================================================



This is extremely important.



Jordan wants the word database to be LARGE, but actual generated puzzles must remain EXCLUSIVE to the chosen subject.



Build a reusable pool-selection concept supporting levels such as:



STRICT

BALANCED

BROAD



or equivalent.



STRICT:

Only primary topic + highly relevant subtopics.



BALANCED:

Primary + normal legitimate supporting clusters.



BROAD:

Allows broader related vocabulary but still excludes unrelated dictionary filler.



The default for commercial books should favor tight relevance.



Do not allow database size to make individual puzzles sloppier.



============================================================

PART I — PUZZLE COHERENCE

============================================================



Improve selection so an individual puzzle feels like a mini-theme rather than 12 random words from a giant topic.



Example:



BBQ book



Puzzle A:

BRISKET

SMOKER

HICKORY

BARK

RUB

LOW SLOW

PITMASTER

THERMOMETER

SMOKE RING

BUTCHER PAPER

RESTING

SLICING



Puzzle B:

BURGER

GRILL

CHARCOAL

BUN

CHEDDAR

PATTY

ONION

PICKLES

SPATULA

SEAR

KETCHUP

FLAME



Both belong to BBQ, but each puzzle has internal coherence.



Design/implement a cluster-aware pool builder capable of this behavior.



Preserve deterministic generation when a seed is supplied.



============================================================

PART J — REPETITION / DIVERSITY ENGINE

============================================================



Commercial 50/100-puzzle books should not repeatedly recycle the same obvious vocabulary unless necessary.



Introduce measurable repetition controls.



Track:



word usage across book

subtopic usage

cluster usage

recent-puzzle reuse

high-frequency anchor reuse



Support configurable constraints such as:



minimum puzzles before reuse

maximum total appearances

prefer unused

prefer underused subtopics

avoid identical word combinations



Do not make generation impossible when a niche has a limited pool.



Degrade gracefully and report when repetition becomes necessary.



============================================================

PART K — CROSS-PUZZLE QUALITY SCORING

============================================================



Create a way to score an entire proposed book, not merely individual words.



Possible metrics:



topic purity

subtopic coverage

word diversity

repetition rate

ambiguity rate

weak-word rate

cluster balance

puzzle coherence

capacity stress



Produce an overall quality report.



Example:



Arizona Word Search

Topic Purity: 98.4%

Unique Vocabulary: 1,327

Repeated Words: 73

Weak/Review Words: 8

Subtopics Represented: 14

Puzzle Coherence: A

Overall: A



Do not fabricate precision if the metric cannot support it.



Document how each metric is calculated.



============================================================

PART L — RE-AUDIT EXISTING 236-THEME LIBRARY

============================================================



AFTER the multi-anchor system is working:



re-run the complete theme inventory.



Compare OLD vs NEW.



We specifically need to know:



How many of the old 47,179 off\_topic findings remain?



How many disappear because the new engine correctly recognizes legitimate supporting vocabulary?



How many themes move:



FAIL → PASS

FAIL → PASS\_WITH\_NOTES

PASS\_WITH\_NOTES → PASS



Generate a comparison report.



Do NOT hide remaining failures.



If Christmas still contains MINECRAFT/FORTNITE and those are truly inappropriate for the intended Christmas book, keep them flagged.



If Desert Life contains DOLPHINS/FJORD/BANJO and they remain genuinely off-topic, keep them flagged.



The objective is fewer FALSE POSITIVES, not fewer findings at any cost.



============================================================

PART M — REBUILD REPAIR PLANS USING BETTER INTELLIGENCE

============================================================



Once the improved audit is complete, regenerate repair plans.



Preserve the existing repair safety tiers:



blocked

approval\_required

review

auto



Preserve:



dry-run default

\--write requirement

\--approve-plan requirement

sha256 snapshots

atomic writes

parse-back

rollback

capacity floor

duplicate protection

Standard/Signature pair protection



DO NOT APPLY ANY REPAIRS.



Instead compare:



OLD:

auto 2

review 57

approval\_required 22

blocked 55



against the new plan distribution.



Explain WHY it changed.



Large rewrites such as halloween\_100/christmas\_100/thanksgiving\_100 must NEVER become auto merely because the new classifier is more permissive.



============================================================

PART N — CANDIDATE GAP REDUCTION

============================================================



The previous system had 55 blocked plans due to unresolved candidate gaps.



Analyze those gaps.



Determine whether they are caused by:



insufficient topic vocabulary

bad subtopic modeling

overly restrictive candidate generation

ambiguity

trademark/safety restrictions

word-length constraints

duplicate restrictions

genuinely exhausted niche vocabulary



Use the expanded word database to resolve as many legitimate gaps as possible.



Do NOT fill gaps with weak words simply to unblock a plan.



Report remaining gaps honestly.



============================================================

PART O — HUMAN REVIEW SYSTEM

============================================================



Improve review output so a human can make decisions efficiently.



For each proposed classification/replacement, surface useful context:



word

current theme

proposed topic

proposed subtopic

confidence

quality tier

reason/signals

ambiguity warning

replacement target if applicable



Where practical, group review work by:



topic

subtopic

cause

confidence

theme



Do not dump thousands of undifferentiated rows.



Preserve human decisions.



============================================================

PART P — WORD INTELLIGENCE CENTER GUI

============================================================



Inspect the existing Word Intelligence Center.



Improve it where useful, but do NOT redesign the entire application.



Potential additions:



Topic Explorer

Subtopic Explorer

Word Search

Word Inspector

Coverage/Capacity

Theme Quality

Repair Plans

Review Queue

Unclassified Candidates

Ambiguous Words

Database Statistics



A useful Word Inspector could show:



WORD: Saguaro



Topics:

Arizona > Desert Plants

Nature > Cacti

Southwest > Landscape



Quality: Excellent

Confidence: 99

Ambiguity: Low

Trademark: No

Safety: Safe

Source/provenance: ...



Do not put expensive full-library operations on the Tk main thread.



Continue daemon/background work + safe Tk marshalling.



IMPORTANT COPY / CLIPBOARD USABILITY REQUIREMENT:



Where the Word Intelligence Center displays substantial reports, review information, diagnostics, word details, or generated textual results, provide an obvious Copy control where practical.



The purpose is to let the user copy useful output without relying on terminal Ctrl+C behavior.



Use the application's existing Tkinter clipboard facilities and existing GUI conventions.



Clipboard operations must occur safely on the Tk/UI thread.



Do not introduce an external clipboard dependency merely for this feature.



Useful controls may include:



Copy

Copy Selected

Copy Report



where appropriate.



============================================================

PART Q — DATABASE SEARCH / EXPLORATION

============================================================



Provide fast read-only querying of the curated word intelligence.



We should eventually be able to answer:



show all excellent Arizona words



show Arizona > Wildlife



show all words shared by Arizona and Desert



show ambiguous words in Technology



show topics with fewer than 200 good words



show unclassified high-frequency dictionary words



show words that have never been used in a theme



Prefer existing storage/index architecture.



Do not add a large external database dependency.



============================================================

PART R — DATA PROVENANCE

============================================================



Every promoted/approved relationship should remain explainable.



Track existing provenance concepts and extend only if necessary:



existing curated bank

dictionary classifier

human approval

theme evidence

derived relationship

manual addition



Human-approved decisions must survive rebuild/regeneration.



Never silently overwrite human decisions with classifier output.



============================================================

PART S — TRADEMARK / BRAND HANDLING

============================================================



Do not simply delete all brands.



Some topics legitimately require culturally recognizable brand/product vocabulary, especially:



1990s

2000s

technology

toys

gaming

nostalgia



But commercial publishing may carry risk.



Keep trademark/brand status as a separate signal.



Allow:



topic relevance = high



while:



commercial/trademark caution = review



Do not conflate semantic relevance with legal/commercial suitability.



============================================================

PART T — PHRASES

============================================================



Ensure the system can intelligently support useful phrases, not only single dictionary words.



Examples:



GRAND CANYON

ROUTE SIXTY SIX / ROUTE 66 depending normalization rules

SMOKE RING

CAST IRON

ROLLER SKATES

VIDEO STORE

FAMILY COMPUTER



Follow existing puzzle normalization constraints.



Store/display human-readable phrase forms while allowing puzzle generation to normalize them appropriately.



Avoid absurdly long phrases.



============================================================

PART U — AGE / AUDIENCE SUITABILITY FOUNDATION

============================================================



Do not build a giant educational system.



But leave room for basic audience suitability:



kids

general

adults

seniors

educational



A word may be semantically correct but inappropriate for a children's book because it is too obscure or advanced.



Use existing metadata where possible.



Add only a lightweight foundation if justified.



============================================================

END PART 3 OF 5

============================================================

BEGIN PART 4 OF 5



============================================================

PART V — DATA QUALITY CHECKS

============================================================



Build automated checks for:



duplicates

case-only duplicates

punctuation variants

plural/singular near duplicates where useful

obvious misspellings

garbled strings

numbers-only

URLs

HTML remnants

control characters

extreme lengths

empty topic assignments

orphan subtopics

invalid taxonomy references

conflicting human decisions

impossible confidence values

duplicate topic links

bad provenance

unsafe/trademark inconsistencies



Do not blindly merge linguistic variants where they represent legitimate separate puzzle entries.



============================================================

PART W — SCALE / PERFORMANCE

============================================================



The system has approximately 370k dictionary entries.



Design for that scale.



Measure:



cold store load

cached load

classification throughput

topic query latency

full theme audit

candidate generation

capacity analysis



Do not prematurely optimize.



But eliminate obvious accidental O(words × themes × topics) work if encountered.



Cache only deterministic/rebuildable information.



Generated caches must not pollute Git.



Record a new performance baseline and compare it to the previous one:



taxonomy load \~0.35s

cached store \~1.71s

candidate index \~0.16s

single theme audit \~73ms

236-theme inventory \~37s



Explain meaningful regressions.



============================================================

PART X — TESTING

============================================================



This phase needs substantial automated coverage.



Add tests for at least:



multi-anchor topic recognition

hierarchical taxonomy

multi-topic words

subtopics

ambiguous word senses

strict/balanced/broad selection

cluster coherence

deterministic selection

repetition control

capacity math

quality scoring

phrase handling

provenance preservation

human decision precedence

trademark semantic separation

canonical validation

repair tier safety

large rewrite non-auto invariant

candidate diversity

duplicate prevention

theme audit comparison

query/search

serialization/round-trip

corrupt-data handling

GUI helper logic where headless testing is practical

performance-sensitive algorithms at reasonable unit-test scale



No real network calls.



Do not weaken existing tests merely to make new behavior pass.



============================================================

PART Y — REAL DATA VALIDATION

============================================================



Unit tests alone are insufficient.



Run the improved engine against the ACTUAL repository word data.



Produce real statistics.



At minimum report:



Raw dictionary entries

Trusted/curated words

Words with >=1 topic

Words with >=1 subtopic

Words with multiple topics

Ambiguous words

Excellent/Good/Acceptable/Review/Reject counts

Unclassified but potentially useful words

Rejected dictionary-noise count



For each canonical topic:



usable vocabulary

excellent vocabulary

subtopic count

capacity estimate

health grade



Identify:



10 strongest topics

10 weakest topics

10 biggest opportunities for expansion



============================================================

PART Z — SAMPLE HUMAN QUALITY AUDIT

============================================================



This is important.



Automatically sample words from at least 20 materially different topics.



Include topics such as:



Arizona

Texas

1990s

Christmas

BBQ

Baking

Gardening

Ocean Life

National Parks

Weather

Pets

History

Movies

Home Cooking

Outdoor Activities



plus other useful topics from the actual taxonomy.



For each sampled topic, inspect a reasonable random/deterministic sample of proposed HIGH-confidence words.



The existing system required >=98% sampled precision before very-high-confidence auto-linking.



PRESERVE OR STRENGTHEN THAT STANDARD.



Do not loosen it just to grow the database.



If precision is below threshold:



do not auto-promote that class of candidates.



END PART 4 OF 5

BEGIN PART 5 OF 5



============================================================

PART AA — COMMERCIAL BOOK SIMULATION

============================================================



Use the improved pool builder to SIMULATE several books without overwriting existing themes.



Examples:



100 puzzles × 20 words:

Arizona



100 × 20:

BBQ



100 × 20:

1990s



100 × 20:

Christmas



50 × 12:

Gardening



48 × 15:

Ocean Life



For each simulation report:



required word slots

unique vocabulary used

reuse count

maximum word reuse

topic purity

subtopic coverage

weak-word count

ambiguity count

cluster coherence

whether the requested book can be generated at acceptable quality



Do NOT save these over production theme files.



Use temp/output report locations.



============================================================

PART AB — "BEST WORD DATABASE" METRICS

============================================================



Create a Word Intelligence health report/dashboard metric set.



Examples:



Curated Vocabulary

Topic Coverage

Subtopic Coverage

High-Confidence Coverage

Ambiguity Rate

Noise Rejection

Average Topic Capacity

Themes Passing Audit

Repair Gaps

Precision Gate Status



The objective is to measure improvement over time.



Do not create vanity metrics based only on raw word count.



============================================================

PART AC — DOCUMENTATION

============================================================



Update/create architecture documentation explaining:



dictionary vs curated vocabulary

taxonomy

subtopics

theme profiles

multi-anchor reasoning

word-topic links

ambiguity

quality

provenance

selection strictness

cluster-aware puzzle generation

diversity/repetition

theme auditing

repair safety

human review

capacity

precision gate



Document:



HOW TO ADD A NEW TOPIC

HOW TO ADD A SUBTOPIC

HOW TO APPROVE WORD RELATIONSHIPS

HOW TO INVESTIGATE A BAD CLASSIFICATION

HOW TO REGENERATE SAFE GENERATED ARTIFACTS

HOW TO RUN THE FULL AUDIT

HOW TO RUN A DRY-RUN REPAIR

HOW TO READ THE HEALTH REPORT



============================================================

PART AD — FULL APPLICATION STABILIZATION

============================================================



After implementation:



run a stabilization pass over everything changed.



Check:



imports

circular dependencies

exception handling

path portability

generated artifact hygiene

Tk threading

determinism

serialization

backwards compatibility

performance

data integrity



Run py\_compile over relevant production modules.



Run git diff --check.



Run the ENTIRE pytest suite.



Do not stop at Word Intelligence tests.



============================================================

PRODUCTION DATA SAFETY

============================================================



data/books.db MUST remain byte-identical.



Record SHA-256 before and after.



Do not modify existing production theme files.



Do not run repair with --write.



Do not silently promote questionable classifier output into authoritative human-curated data.



Generated analysis/report/plan files belong in existing generated/report locations and should remain ignored when appropriate.



If you discover a file that SHOULD be authoritative/version-controlled, explain why before treating it that way.



============================================================

IMPORTANT DECISION RULES

============================================================



When faced with a tradeoff:



PRECISION > RAW DATABASE SIZE



TOPIC COHERENCE > RANDOM VARIETY



HUMAN DECISION > CLASSIFIER



CURATED DATA > DICTIONARY NOISE



EXPLAINABLE SIGNALS > BLACK-BOX MAGIC



SAFE DRY RUN > AUTOMATIC REWRITE



DETERMINISTIC BEHAVIOR > UNREPRODUCIBLE OUTPUT



EXISTING ARCHITECTURE > PARALLEL REPLACEMENT SYSTEM



BUSINESS USEFULNESS > ACADEMIC COMPLEXITY



============================================================

DO NOT

============================================================



Do NOT:



mass-apply repair plans

rewrite production themes

touch books.db

rewrite the application from scratch

create a competing word database

remove existing approved links

weaken trademark/safety checks

lower the 98% precision gate merely to increase counts

introduce network-dependent AI classification into core operation

require cloud APIs for normal word generation

add heavyweight ML dependencies without explicit approval

modify publishing integrations unless absolutely required for compatibility

commit or push

hide failures

declare success solely because tests pass



============================================================

STOP CONDITIONS

============================================================



Stop and report before proceeding if:



a schema/data migration would risk destructive changes

a new third-party dependency appears necessary

human-approved decisions would need reinterpretation/destruction

the proposed architecture requires replacing the existing intelligence system rather than extending it

production themes would need modification to validate the design

books.db changes unexpectedly

precision testing materially fails

a repair operation unexpectedly writes production data



Otherwise continue through the entire batch autonomously.



============================================================

FINAL DELIVERABLE

============================================================



When complete, provide ONE comprehensive final report.



Use these sections:



1\. EXECUTIVE SUMMARY



What materially improved?



2\. FILES CREATED



3\. FILES MODIFIED



4\. MULTI-ANCHOR SYSTEM



Explain implementation and examples.



5\. TAXONOMY / SUBTOPICS



Counts and architecture.



6\. MASTER WORD DATABASE



Before/after statistics.



Include:

raw entries

curated/trusted

classified

multi-topic

subtopic-linked

ambiguous

quality tiers

noise rejected



7\. TOPIC HEALTH



Strongest/weakest topics and capacity.



8\. OLD VS NEW THEME AUDIT



Include previous and new:

PASS

PASS\_WITH\_NOTES

FAIL

off\_topic count



Explain major changes.



9\. REPAIR PLAN COMPARISON



Old:

auto 2

review 57

approval\_required 22

blocked 55



New distribution.



NO repairs applied.



10\. CANDIDATE GAPS



Resolved vs remaining and why.



11\. COMMERCIAL BOOK SIMULATIONS



Results for the requested simulated books.



12\. PRECISION VALIDATION



Human-quality sampling results and whether >=98% gate passes.



13\. PERFORMANCE



Old baseline vs new baseline.



14\. GUI IMPROVEMENTS



If any.



15\. TESTING



New tests

targeted results

full-suite result

py\_compile

git diff --check



16\. DATA SAFETY



books.db before/after hash

production themes unchanged

repairs not applied

generated artifacts ignored



17\. BUGS DISCOVERED AND FIXED



18\. TECHNICAL DEBT / REMAINING RISKS



19\. WORD INTELLIGENCE HEALTH SCORE



Give justified grades for:

Database breadth

Topic precision

Subtopic depth

Puzzle coherence

Diversity

Ambiguity handling

Repair safety

Performance

Maintainability



20\. RECOMMENDED NEXT STEP



Be specific.



If the improved system demonstrates that the repair recommendations are now trustworthy, recommend the safest next review/apply phase.



If not, say exactly what must improve before touching production themes.



============================================================

FINAL PRINCIPLE

============================================================



We are trying to build one of the strongest practical word-selection systems possible for commercial puzzle-book creation.



The master database can be enormous.



The individual puzzle must still feel intentional.



A user selecting:



"Arizona"



should get Arizona.



A user selecting:



"1990s Childhood"



should get 1990s childhood.



A user selecting:



"BBQ"



should get BBQ.



The system should have access to hundreds of thousands of words while having the intelligence NOT to use most of them.



That selectivity is the product.



Proceed through this as one large engineering + data-quality + validation batch. Take the time required to research the repository, test assumptions against the real data, and finish the entire authorized scope before reporting back.



Do not commit or push.



END PART 5 OF 5

