"""Unit tests for the risk engine. Run without Django:  python -m unittest routing.tests -v"""
import unittest

from . import geo, risk
from .risk import HIGH, LOW, MODERATE, NO_TRAVEL, SEVERE


class ThresholdTests(unittest.TestCase):
    def test_wind_bands(self):
        cases = [(0, LOW), (24.9, LOW), (25, MODERATE), (34.9, MODERATE), (35, HIGH), (44.9, HIGH),
                 (45, SEVERE), (54.9, SEVERE), (55, NO_TRAVEL), (80, NO_TRAVEL)]
        for v, want in cases:
            self.assertEqual(risk.classify("wind", v), want, f"wind {v}")

    def test_rain_bands(self):
        cases = [(0.09, LOW), (0.10, MODERATE), (0.24, MODERATE), (0.25, HIGH), (0.49, HIGH),
                 (0.50, SEVERE), (1.00, SEVERE), (1.01, NO_TRAVEL)]
        for v, want in cases:
            self.assertEqual(risk.classify("rain", v), want, f"rain {v}")

    def test_snow_bands(self):
        cases = [(0.4, LOW), (0.5, MODERATE), (0.99, MODERATE), (1.0, HIGH), (1.99, HIGH),
                 (2.0, SEVERE), (3.0, SEVERE), (3.01, NO_TRAVEL)]
        for v, want in cases:
            self.assertEqual(risk.classify("snow", v), want, f"snow {v}")


class LoadRuleTests(unittest.TestCase):
    def test_wind_55_no_travel_any_load(self):
        self.assertEqual(risk.assess(55, 0, 0, 1_000).level, NO_TRAVEL)

    def test_wind_45_54_heavy_is_no_travel(self):
        self.assertEqual(risk.assess(50, 0, 0, 30_001).level, NO_TRAVEL)

    def test_wind_45_54_at_30k_stays_severe(self):
        self.assertEqual(risk.assess(50, 0, 0, 30_000).level, SEVERE)

    def test_wind_35_44_over_40k_is_severe(self):
        self.assertEqual(risk.assess(40, 0, 0, 40_001).level, SEVERE)

    def test_wind_35_44_at_40k_stays_high(self):
        self.assertEqual(risk.assess(40, 0, 0, 40_000).level, HIGH)

    def test_load_rule_never_downgrades(self):
        # heavy rain already No Travel; wind load rule must not lower it
        self.assertEqual(risk.assess(40, 1.5, 0, 50_000).level, NO_TRAVEL)

    def test_overall_is_worst_factor(self):
        a = risk.assess(10, 0.3, 0.6, 10_000)
        self.assertEqual((a.wind_level, a.rain_level, a.snow_level, a.level), (LOW, HIGH, MODERATE, HIGH))


class SummaryAndRankingTests(unittest.TestCase):
    def test_segment_miles_sum_to_total(self):
        d = [0, 25, 50, 75, 90]
        self.assertAlmostEqual(sum(risk.segment_miles(d, 90)), 90)

    def test_summary_weighting(self):
        s = risk.summarize([LOW, SEVERE, LOW], [0, 50, 100], 100)
        self.assertEqual(s["severe_miles"], 50.0)  # middle checkpoint owns 25..75
        self.assertEqual(s["max_label"], "Severe")

    def _route(self, severe, high, avg, dur, nt=0):
        return {"summary": {"no_travel_miles": nt, "severe_miles": severe, "high_miles": high, "avg_risk": avg},
                "duration_s": dur}

    def test_fewest_severe_wins_over_speed(self):
        routes = [self._route(30, 0, 0.1, 3600), self._route(0, 90, 1.0, 9000)]
        self.assertEqual(risk.recommend(routes)[0], 1)

    def test_high_miles_break_severe_tie(self):
        routes = [self._route(0, 40, 0.5, 3600), self._route(0, 10, 0.9, 7200)]
        self.assertEqual(risk.recommend(routes)[0], 1)

    def test_avg_risk_then_time(self):
        routes = [self._route(0, 0, 0.30, 5000), self._route(0, 0, 0.10, 9000), self._route(0, 0, 0.10, 8000)]
        self.assertEqual(risk.recommend(routes)[0], 2)

    def test_no_travel_is_worse_than_severe(self):
        routes = [self._route(0, 0, 2, 3600, nt=10), self._route(80, 0, 2, 3600)]
        self.assertEqual(risk.recommend(routes)[0], 1)


class GeoTests(unittest.TestCase):
    def test_haversine_known_distance(self):
        # Chicago -> St. Louis is roughly 260 mi as the crow flies
        d = geo.haversine_mi((-87.6298, 41.8781), (-90.1994, 38.6270))
        self.assertTrue(255 < d < 270, d)

    def test_interpolate_midpoint(self):
        coords = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
        cum = geo.cumulative_miles(coords)
        lon, lat = geo.interpolate_at(coords, cum, cum[-1] / 2)
        self.assertAlmostEqual(lat, 1.0, places=3)


if __name__ == "__main__":
    unittest.main()
