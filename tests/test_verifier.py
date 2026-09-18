import io
import itertools
import unittest

from verifier import MAX_EVENT_LINE_CHARS, _point, candidate_score, load_events, verify


class VerifierTests(unittest.TestCase):
    def event(self, event_id, source, *, observed_at="2026-01-01T12:00:00Z", title="River flooding reported", lon=-3.7, lat=40.4, confidence=0.6):
        return {
            "id": event_id,
            "kind": "flood",
            "title": title,
            "description": "water rising near the river",
            "observed_at": observed_at,
            "area": "Test Area",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "severity": 0.8,
            "official": False,
            "source": {"name": source},
            "confidence": confidence,
        }

    def test_naive_and_aware_datetimes_can_be_compared(self):
        a = self.event("a", "A", observed_at="2026-01-01T12:00:00")
        b = self.event("b", "B", observed_at="2026-01-01T13:00:00Z")
        score, parts = candidate_score(a, b)
        self.assertGreater(score, 0)
        self.assertIsNotNone(parts["time"])

    def test_invalid_coordinates_are_not_used_as_distance_evidence(self):
        bad = self.event("a", "A", lon=999, lat=999)
        good = self.event("b", "B")
        self.assertIsNone(_point(bad))
        score, parts = candidate_score(bad, good)
        self.assertGreater(score, 0)
        self.assertEqual(parts["distance"], 0.5)

    def test_non_finite_confidence_cannot_poison_library_output(self):
        a = self.event("a", "A", confidence=float("nan"))
        b = self.event("b", "B", confidence=0.7)
        result = verify([a, b])
        self.assertEqual(len(result), 1)
        self.assertGreaterEqual(result[0]["confidence"], 0)
        self.assertLessEqual(result[0]["confidence"], 0.995)

    def test_cli_loader_rejects_non_standard_json_numbers(self):
        with self.assertRaises(ValueError):
            load_events(io.StringIO('{"id":"x","confidence":NaN}\n'))
        with self.assertRaises(ValueError):
            load_events(io.StringIO('{"id":"x","confidence":Infinity}\n'))

    def test_cli_loader_requires_objects(self):
        with self.assertRaises(ValueError):
            load_events(io.StringIO('[1,2,3]\n'))

    def test_cli_loader_rejects_oversized_lines(self):
        with self.assertRaises(ValueError):
            load_events(io.StringIO("x" * (MAX_EVENT_LINE_CHARS + 1)))

    def test_output_is_invariant_under_input_permutation(self):
        a = self.event("a", "A")
        b = self.event("b", "B", observed_at="2026-01-01T12:20:00+00:00", confidence=0.7)
        c = self.event("c", "C", observed_at="2026-01-03T12:00:00Z", title="Different flood report")
        expected = verify([a, b, c])
        for permutation in itertools.permutations([a, b, c]):
            self.assertEqual(verify(list(permutation)), expected)

    def test_provenance_keeps_report_level_details(self):
        a = self.event("a", "Agency A", confidence=0.6)
        a["source"].update({"source_id": "A-001", "type": "cap", "url": "https://example.invalid/a"})
        b = self.event("b", "Agency B", observed_at="2026-01-01T13:30:00Z", confidence=0.8)
        b["source"].update({"source_id": "B-002", "type": "field"})

        result = verify([a, b])[0]
        self.assertEqual(result["verification"]["independent_source_count"], 2)
        self.assertEqual(result["verification"]["provenance_entries"], 2)
        self.assertEqual(result["verification"]["observation_window"]["span_hours"], 1.5)
        self.assertEqual(result["verification"]["severity_range"], {"min": 0.8, "max": 0.8})
        by_source = {item["source"]: item for item in result["evidence"]}
        self.assertEqual(by_source["Agency A"]["source_id"], "A-001")
        self.assertEqual(by_source["Agency A"]["event_id"], "a")
        self.assertEqual(by_source["Agency A"]["source_type"], "cap")
        self.assertEqual(by_source["Agency B"]["observed_at"], "2026-01-01T13:30:00Z")

    def test_duplicate_reports_from_same_source_count_once(self):
        a = self.event("a", "Agency A", confidence=0.6)
        b = self.event("b", "Agency A", confidence=0.9)
        result = verify([a, b])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["verification"]["independent_source_count"], 1)
        self.assertEqual(result[0]["confidence"], 0.9)


if __name__ == "__main__":
    unittest.main()
