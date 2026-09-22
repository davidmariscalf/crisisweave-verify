# crisisweave-verify

**Explainable event deduplication and confidence aggregation for noisy multi-source crisis reports.**

`crisisweave-verify` takes normalized JSONL reports, finds likely duplicates, preserves source-level provenance and emits merged incidents with auditable verification metadata.

It is deliberately narrower than “AI fact checking”: the output is a transparent ranking signal for human review, not a claim that an event is true.

## 60-second demo

Requires Python 3.10+ and no third-party packages.

```bash
cat events.jsonl | python verifier.py > verified.jsonl
```

A useful end-to-end test with the companion simulator:

```bash
git clone https://github.com/davidmariscalf/crisisweave-sim.git
python crisisweave-sim/simulate.py --scenario mixed --count 60 --seed 42 > events.jsonl
cat events.jsonl | python verifier.py > verified.jsonl
```

Now `verified.jsonl` contains clustered incidents with evidence and provenance instead of silently discarding duplicate reports.

## What the verifier considers

Reports can merge only when their event kind is compatible and their time/location are not obviously contradictory. Candidate matching then considers:

- title/description token overlap
- observation-time proximity
- geographic distance when both reports have coordinates
- area-name overlap

The thresholds are constants at the top of `verifier.py`, so deployments can inspect and tune them.

## Why deterministic first?

Opaque models can fail silently, especially on edge cases. This verifier is designed so that a reviewer can understand why two reports were grouped and what evidence contributed to the resulting confidence signal.

That makes it useful for:

- regression testing
- incident-feed prototyping
- explainable deduplication benchmarks
- provenance-preserving aggregation
- human-in-the-loop triage systems

## Confidence is not probability

Evidence is aggregated with diminishing returns:

- independent sources can increase confidence
- repeated copies from the same source do not count as independent corroboration
- official reports receive a higher default evidence weight
- unofficial/community reports are not discarded solely because they are unofficial

The resulting confidence value is a ranking signal for review, **not** a calibrated probability that an incident is true.

## Provenance survives merging

Merged incidents retain report-level provenance for the strongest contribution from every independent source, including:

- original event ID
- source ID/type/URL
- observation time
- official status
- evidence weight
- observation-time window
- severity range

Downstream tools can therefore expose disagreement, age and source diversity instead of collapsing everything into one opaque number.

## Part of CrisisWeave

This repository is a standalone component of [CrisisWeave](https://github.com/davidmariscalf/CrisisWeave).

Related repositories:

- [crisisweave-sim](https://github.com/davidmariscalf/crisisweave-sim) — deterministic synthetic crisis-event generation
- [crisisweave-map](https://github.com/davidmariscalf/crisisweave-map) — browser interfaces for incident and recovery views

## Safety

This project supports information review; it is not an emergency authority, dispatch system or substitute for official instructions. A higher confidence score must not be interpreted as proof of safety or truth.
