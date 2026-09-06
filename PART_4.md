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

