"""Synthetic contract tests only; these are not candidate performance measurements."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import assess_candidate as wrapper


class AcceptanceTests(unittest.TestCase):
    def timing(self,factors):
        contract=wrapper.load(wrapper.HERE/'acceptance.json')
        runs=[]
        for factor,duration,count in factors:
            for platform in contract['timing']['required_platforms']:
                for workload in contract['timing']['required_workloads']:
                    row={'platform':platform,'integration_substeps':factor,'workload_id':workload,'workload_sha256':'synthetic-'+workload,'outer_hz':64,'warmup_ticks':1024,'measurements_ms':[duration]*count}
                    row.update({flag:True for flag in contract['timing']['required_workload_flags']})
                    runs.append(row)
        with TemporaryDirectory() as temporary:
            path=Path(temporary)/'synthetic-benchmark.json'
            path.write_text(json.dumps({'schema':'precision-benchmark-v1','runs':runs}))
            return wrapper.assess_timing(SimpleNamespace(benchmarks=path),contract)

    def test_full_cap_factor_needs_all_platforms_and_workloads(self):
        result=self.timing([(32,10.0,8192)])
        self.assertEqual(result['highest_measured_timing_pass_factor'],32)
        self.assertTrue(result['selection_bracket_supported'])
        self.assertTrue(result['globally_highest_measured_claim_supported'])

    def test_next_higher_failure_establishes_bracket(self):
        result=self.timing([(16,8.0,8192),(32,13.0,8192)])
        self.assertEqual(result['highest_measured_timing_pass_factor'],16)
        self.assertTrue(result['selection_bracket_supported'])

    def test_screening_does_not_masquerade_as_full_higher_measurement(self):
        result=self.timing([(8,8.0,8192),(16,13.0,8192),(32,20.0,32)])
        self.assertTrue(result['selection_bracket_supported'])
        self.assertFalse(result['globally_highest_measured_claim_supported'])

    def test_insufficient_next_higher_coverage_does_not_establish_bracket(self):
        result=self.timing([(16,8.0,8192),(32,30.0,32)])
        self.assertFalse(result['selection_bracket_supported'])

    def test_oracle_pin_rejects_unqualified_source(self):
        with TemporaryDirectory() as temporary:
            path=Path(temporary)/'not-an-oracle.py'
            path.write_text('raise RuntimeError("must never be imported")\n')
            with self.assertRaisesRegex(ValueError,'hash'):
                wrapper.oracle(path)


if __name__=='__main__':unittest.main()
