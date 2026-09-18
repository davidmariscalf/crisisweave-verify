# crisisweave-verify

Explainable deduplication and confidence aggregation for CrisisWeave events.

The goal is deliberately narrower than "AI fact checking": given multiple reports, identify likely duplicates, preserve every source, and calculate a confidence score whose inputs are visible.

## Why deterministic first

In a crisis, an opaque model can fail silently. The MVP therefore combines lexical similarity, time distance, optional geographic distance, source independence, and official-source status. The score is not a probability that an event is true; it is a ranking signal for human review.

## Quick start

```bash
cat events.jsonl | python verifier.py > verified.jsonl
```

The CLI accepts normalized CrisisWeave JSON objects, one per line. Likely duplicates are clustered and emitted as one merged event with `verification` metadata.

## Matching gates

Reports can merge only when their event kind is compatible and their time/location are not obviously contradictory. A weighted candidate score then considers:

- title/description token overlap
- observation time proximity
- point distance when both reports have coordinates
- area-name overlap

The thresholds are constants at the top of `verifier.py` so deployments can audit and tune them.

## Confidence

Evidence is aggregated with diminishing returns. Multiple independent sources increase confidence; repeated copies from the same source do not count as independent corroboration. Official reports receive a higher default evidence weight, but community reports are never discarded solely because they are unofficial.

## Provenance in merged incidents

Merged incidents retain report-level provenance for the strongest contribution from every independent source, including the original event ID, source ID/type/URL, observation time, official status and evidence weight. The verification block also exposes the observation time window and severity range so downstream tools can show disagreement and age instead of collapsing corroboration into a single opaque score. Confidence remains a ranking signal, not a probability of truth.
