from __future__ import annotations

import json
import math
import re
import sys
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

MATCH_THRESHOLD = 0.67
MAX_HOURS = 24.0
MAX_KM = 75.0


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.casefold()) if len(t) > 2}


def _jaccard(a: str, b: str) -> float:
    aa, bb = _tokens(a), _tokens(b)
    if not aa and not bb:
        return 1.0
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _hours(a: str | None, b: str | None) -> float | None:
    da, db = _dt(a), _dt(b)
    if da is None or db is None:
        return None
    return abs((da - db).total_seconds()) / 3600.0


def _point(event: dict[str, Any]) -> tuple[float, float] | None:
    g = event.get("geometry")
    if not isinstance(g, dict) or g.get("type") != "Point":
        return None
    c = g.get("coordinates")
    if not isinstance(c, list) or len(c) != 2:
        return None
    try:
        lon, lat = float(c[0]), float(c[1])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(lon) or not math.isfinite(lat):
        return None
    if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
        return None
    return lon, lat


def _km(a: tuple[float, float] | None, b: tuple[float, float] | None) -> float | None:
    if a is None or b is None:
        return None
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(max(0.0, h))))


def candidate_score(a: dict[str, Any], b: dict[str, Any]) -> tuple[float, dict[str, float | None]]:
    ka = str(a.get("kind") or "other").casefold()
    kb = str(b.get("kind") or "other").casefold()
    if ka != kb and "other" not in (ka, kb):
        return 0.0, {"text": 0.0, "time": None, "distance": None, "area": 0.0}

    hours = _hours(a.get("observed_at"), b.get("observed_at"))
    if hours is not None and hours > MAX_HOURS:
        return 0.0, {"text": 0.0, "time": 0.0, "distance": None, "area": 0.0}

    distance = _km(_point(a), _point(b))
    if distance is not None and distance > MAX_KM:
        return 0.0, {"text": 0.0, "time": 0.0, "distance": 0.0, "area": 0.0}

    ta = f"{a.get('title', '')} {a.get('description', '')}"
    tb = f"{b.get('title', '')} {b.get('description', '')}"
    text_score = _jaccard(ta, tb)
    time_score = 0.5 if hours is None else max(0.0, 1.0 - hours / MAX_HOURS)
    distance_score = 0.5 if distance is None else max(0.0, 1.0 - distance / MAX_KM)
    area_score = _jaccard(str(a.get("area") or ""), str(b.get("area") or ""))

    score = 0.55 * text_score + 0.20 * time_score + 0.15 * distance_score + 0.10 * area_score
    return score, {
        "text": round(text_score, 4),
        "time": round(time_score, 4),
        "distance": round(distance_score, 4),
        "area": round(area_score, 4),
    }


def _source_key(event: dict[str, Any]) -> str:
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    return str(source.get("name") or source.get("url") or source.get("source_id") or event.get("id") or "unknown")


def _event_key(event: dict[str, Any]) -> tuple[str, str, str, str, str]:
    observed = _dt(event.get("observed_at"))
    observed_key = observed.isoformat() if observed is not None else ""
    return (
        str(event.get("kind") or "other").casefold(),
        observed_key,
        _source_key(event).casefold(),
        str(event.get("id") or ""),
        str(event.get("title") or "").casefold(),
    )


def _evidence_weight(event: dict[str, Any]) -> float:
    try:
        base = float(event.get("confidence", 0.4))
    except (TypeError, ValueError):
        base = 0.4
    if not math.isfinite(base):
        base = 0.4
    if event.get("official"):
        base = max(base, 0.82)
    return max(0.05, min(0.95, base))


def aggregate_confidence(events: list[dict[str, Any]]) -> tuple[float, list[dict[str, Any]]]:
    strongest_by_source: dict[str, float] = {}
    for event in events:
        key = _source_key(event)
        strongest_by_source[key] = max(strongest_by_source.get(key, 0.0), _evidence_weight(event))

    residual = 1.0
    explanation: list[dict[str, Any]] = []
    for source, weight in sorted(strongest_by_source.items(), key=lambda item: item[0].casefold()):
        residual *= 1.0 - weight
        explanation.append({"source": source, "weight": round(weight, 4)})
    return round(min(0.995, 1.0 - residual), 4), explanation


def cluster(events: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Create deterministic complete-link clusters.

    Input order must not change the result. An event may join a group only when
    it clears the match threshold against every current member, preventing a
    weak A-B-C bridge from merging reports that do not directly corroborate
    one another.
    """

    groups: list[list[dict[str, Any]]] = []
    for event in sorted(events, key=_event_key):
        candidates: list[tuple[float, tuple, int]] = []
        for index, group in enumerate(groups):
            scores = [candidate_score(event, member)[0] for member in group]
            if scores and min(scores) >= MATCH_THRESHOLD:
                candidates.append((sum(scores) / len(scores), _event_key(group[0]), index))
        if not candidates:
            groups.append([event])
            continue
        _, _, chosen = max(candidates, key=lambda row: (row[0], tuple(reversed(row[1]))))
        groups[chosen].append(event)

    for group in groups:
        group.sort(key=_event_key)
    groups.sort(key=lambda group: _event_key(group[0]))
    return groups


def merge_group(group: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = sorted(
        group,
        key=lambda e: (-_evidence_weight(e), -int(bool(e.get("official"))), _event_key(e)),
    )
    merged = deepcopy(ranked[0])
    confidence, sources = aggregate_confidence(group)
    merged["confidence"] = confidence
    merged["official"] = any(bool(e.get("official")) for e in group)
    merged["evidence"] = sources
    merged["verification"] = {
        "method": "crisisweave-deterministic-v2",
        "report_count": len(group),
        "independent_source_count": len(sources),
        "merged_event_ids": [str(e.get("id")) for e in sorted(group, key=_event_key)],
        "confidence_note": "ranking signal, not probability of truth",
    }
    return merged


def verify(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean = [event for event in events if isinstance(event, dict)]
    return [merge_group(group) for group in cluster(clean)]


def main() -> int:
    events = [json.loads(line) for line in sys.stdin if line.strip()]
    for event in verify(events):
        print(json.dumps(event, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
