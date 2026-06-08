---
date: 2026-06-08
description: Three durable architectural ideas harvested from the engram-vang clone before it was removed from the repo — kept here so the concepts survive the deletion.
tags: [brain, patterns, reference]
aliases: [Engram Ideas, Engram Patterns]
---

# Engram Harvest

The optional `engram-vang/` operator-knowledge clone was removed from VERDICT (gitignored orphan,
zero product-code imports, dead weight for the submission — see [[Key Decisions]]). Before deleting
it, these three ideas were worth keeping. They are **design notes, not committed code**.

## 1. Source-tier confidence weighting (low-effort, port candidate for Hermes)

Engram ranks a retrieval hit by composing three independent signals rather than raw search score:

```
ranked_score = rrf_score × stored_confidence × source_tier_weight × recency_decay
recency_decay = 0.5 ** (age_days / half_life_days)        # exponential half-life
```

`source_tier_weight` is a per-source-class trust multiplier (e.g. vendor docs > blog > forum),
defaulting to `0.5` for unknown tiers. From `engram-vang/src/engram/rag/query.py` (`hybrid_search`,
`_confidence_decay`).

**Why it matters for VERDICT:** Hermes (`MemoryStore.recall`, `services/agent/findevil_agent/memory/store.py`)
already does a 90-day exponential decay. Adding a tier multiplier — trust a `finding_summary` from a
CONFIRMED prior case more than a loose `ioc` note — is ~10 lines on top of the existing decay and
makes cross-case recall ranking correct without manual tuning. This is the one harvested idea worth
actually porting (tracked as the optional follow-up in the memory-refactor plan). See [[Patterns]].

## 2. RRF hybrid retrieval — BM25 ⊕ vectors (future work, NOT a Hermes priority)

Engram runs sparse (FTS5/BM25) and dense (vector embedding) search in parallel and fuses the two
rankings with **Reciprocal Rank Fusion**:

```
rrf_score(hash) = Σ over rankings of  1 / (rrf_k + rank + 1)
```

Embedding failure falls back to BM25-only (retrieval never dies). From `query.py` (`_rrf_fuse`,
`_vector_hits`, `_bm25_hits`). RRF is a well-published pattern that beats either modality alone on
semantic recall.

**Why it's deferred for VERDICT:** Hermes is BM25-only today and that's deliberate — it's an
audit-safe, lightweight `ioc/hash/ttp/hostname/finding_summary` lookup, not a semantic research
engine. Hermes' real gap is source curation and confidence, not ranking sophistication, and adding
embeddings drags in model weights + ~200 MB/case of vectors. Capture the pattern; don't build it
unless cross-case semantic recall becomes a real need.

## 3. "The vault is a view, not the source of truth" (apply conceptually to obsidian-mind)

Engram treats its append-only event log as canonical and the Obsidian vault as a **materialized
view**: the projector tails the log, renders markdown, and snapshots the rendered bytes into a
`vault_state` table so a watcher can diff later human edits. A corrupted/lost vault file is
non-fatal — it re-renders from the log. From `engram-vang/src/engram/projector/projector.py`
(`_project_one`, `_handle_event`).

**Why it matters for obsidian-mind:** today the vault `brain/` notes ARE the source of truth — a
corrupted note is just gone. We don't need Engram's daemon machinery, but the *principle* is worth
adopting cheaply: **treat git history as the canonical store, route durable writes through
`/om-dump` (hook-validated), and don't hand-edit-then-lose.** The vault is the readable view;
git + QMD reindex is the recovery path. See [[Skills]] and [[Key Decisions#Memory is never evidence]].

## What was intentionally NOT harvested

Engram's event-log-as-canonical store, 4-daemon architecture (projector/watcher/reactor/poller),
autonomous source-polling, and near-dup/supersede gates are well-built but solve a personal-research
curation problem, not VERDICT's. They are overkill for both obsidian-mind (dev memory) and Hermes
(narrow in-investigation recall). The ideas are durable even though the implementation isn't —
that's the point of this note.
