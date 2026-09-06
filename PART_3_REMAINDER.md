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

