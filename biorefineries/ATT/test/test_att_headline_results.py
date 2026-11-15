"""
Headline results of the 2026-11-12 advisor package (Yu Zhou's email, the S3 figures PDF), reproduced from the model.

Values: biosteam a4f6d15, thermosteam d3d4c7f, hensmith 95e9362 (see test_att_baseline). The values reported in the email
and the PDF come from Yu Zhou's environment; they differ from the values here only through the heat integration
(hensmith), by up to 5.4 % in the treatment cost, 7.5 % in the EROI and 13 % in the S3 GWP. The tolerances below cover
both sets of values. The recovered heat and the hydrogen output do not depend on the heat integration and are tight.
"""
import unittest
import warnings

from biorefineries.ATT.analyses import headline_results as hr
from biorefineries.ATT.analyses.s3_industrial import run as s3_run
from biorefineries.ATT.analyses.ree_tea_cases import collect_ree_tea
from biorefineries.ATT.analyses.treatment_report import run as treatment_run


def close(test, value, expected, rtol, msg=""):
    test.assertAlmostEqual(value / expected, 1.0, delta=rtol, msg=f"{msg}: {value} vs {expected}")


class TestHeadlineResults(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.industrial = s3_run(enable_ree_recovery=True)
        cls.rows = treatment_run()[0]
        cls.eroi = hr.s3_energy_and_eroi(industrial=cls.industrial)
        cls.benchmarks = hr.benchmark_treatment(industrial=cls.industrial, ree_tea=collect_ree_tea())

    def test_s3_recovered_heat(self):
        # email: about 12.54 MW of useful recovered heat from the two calcium carbide sources
        close(self, self.industrial["used_average_kW"], 12536.38, 5e-3, "recovered heat")

    def test_s3_net_gwp(self):
        # email: 7.356 kg CO2e/kg H2 (REE on)
        close(self, self.industrial["s3_GWP_kg_per_kg_H2"], 8.3367, 0.15, "S3 GWP")

    def test_treatment_cost_per_tonne_wet_presscake(self):
        # email, REE on: S1 31.52, S2 35.16, S3 24.78 USD/t wet
        expected = {"S1": 32.854, "S2": 36.493, "S3": 26.114}
        rows = {r["scenario"]: r for r in self.rows if r["basis"] == "per_tonne_wet" and r["ree_enabled"]}
        for scenario, value in expected.items():
            close(self, rows[scenario]["net_treatment_cost_usd"], value, 0.08, scenario)

    def test_eroi(self):
        # PDF: output 8.898 MJ/kg dry, EROI 0.345 (S1) and 0.608 (S3)
        close(self, self.eroi["h2_output_MJ_per_kg_dry"], 8.89827857, 1e-6, "H2 energy output")
        close(self, self.eroi["EROI_S1"], 0.3312, 0.10, "EROI S1")
        close(self, self.eroi["EROI_S3"], 0.5654, 0.10, "EROI S3")

    def test_hydrogen_benchmarks(self):
        # PDF, S3 treatment cost [USD/t dry feed] and GWP [kg CO2e/t dry feed] when the H2 replaces gray, blue and green H2:
        # Gray -6.67 / -144, Blue -43.7 / +286, Green -340 / +501
        expected = {"Gray": (-1.04, -71.4), "Blue": (-38.1, 358.7), "Green": (-334.7, 573.7)}
        for name, (cost, gwp) in expected.items():
            self.assertAlmostEqual(self.benchmarks[name]["treatment_cost_USD_per_t"], cost, delta=10.0, msg=name)
            self.assertAlmostEqual(self.benchmarks[name]["treatment_GWP_kg_per_t"], gwp, delta=100.0, msg=name)


if __name__ == "__main__":
    unittest.main()
