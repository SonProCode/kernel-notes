"""Boundary and small-sample semantics of the independent S4 acceptance report."""
import unittest
from s4.review import phase_metrics


class PhaseMetricTests(unittest.TestCase):
    def metrics(self, records):
        def moment(seconds): return f"2026-01-01T00:00:{seconds:02d}+00:00"
        timeline=[{"phase":p,"time":moment(t)} for p,t in (("pre_attack",0),("attack",10),("recovery",20),("finalize",30))]
        requests=[dict(started=moment(a),ended=moment(b),duration_ms=latency,status_code=status,error=None if status==200 else "HTTPError") for a,b,latency,status in records]
        return phase_metrics(requests,timeline,moment(30))

    def test_crossing_requests_count_once_in_starts_and_completions(self):
        r=self.metrics([(9,11,2000,200),(12,13,1000,200)])
        self.assertEqual(r["pre_attack"]["request_starts"],1)
        self.assertEqual(r["pre_attack"]["crossing_out_requests"],1)
        self.assertEqual(r["attack"]["request_completions"],2)
        self.assertEqual(r["attack"]["crossing_in_requests"],1)
        self.assertEqual(r["attack"]["requests"],1)
        self.assertEqual(r["attack"]["completed_rps"],.2)

    def test_half_open_boundaries_count_exact_boundary_in_next_phase(self):
        r=self.metrics([(10,11,1000,200)])
        self.assertEqual(r["pre_attack"]["request_starts"],0)
        self.assertEqual(r["attack"]["request_starts"],1)

    def test_p99_small_success_population_and_failed_request_kept_separate(self):
        r=self.metrics([(11,12,1000,200),(13,14,1,500)])["attack"]
        self.assertEqual(r["p99_ms"],1000)
        self.assertTrue(r["p99_is_max_for_fewer_than_100_successes"])
        self.assertEqual(r["failures"],1)


if __name__=="__main__":unittest.main()
