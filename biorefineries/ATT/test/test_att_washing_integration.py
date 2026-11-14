"""The F2 wash conserves mass and calcium solids."""
import unittest
import warnings
import numpy as np
from biorefineries.ATT.analyses import scenarios as scen, inventory as inv


def washing_checks(system):
    u = inv._units(system)
    rows = []
    for ID in ("W2", "F2R"):
        unit = u[ID]
        residual = sum((s.mass for s in unit.outs)) - sum((s.mass for s in unit.ins))
        for component, error in zip(unit.chemicals.IDs, residual):
            rows.append(dict(check=f"{ID} {component} component balance [kg/h]",
                             residual=float(error), status="PASS" if abs(error) < 1e-8 else "FAIL"))
        error = sum(s.F_mass for s in unit.outs) - sum(s.F_mass for s in unit.ins)
        rows.append(dict(check=f"{ID} total mass [kg/h]", residual=float(error),
                         status="PASS" if abs(error) < 1e-8 else "FAIL"))
    for component in ("CaCO3", "CaOH2"):
        error = float(u["F2R"].outs[0].imass[component] - u["F2"].outs[0].imass[component])
        rows.append(dict(check=f"Washing preserves {component} [kg/h]", residual=error,
                         status="PASS" if abs(error) < 1e-8 else "FAIL"))
    return rows


class TestNativeF2Washing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.on = scen.create(scen.ATT_S1)
        cls.u = inv._units(cls.on)


    def test_wash_conserves_mass_and_calcium_solids(self):
        for row in washing_checks(self.on):
            self.assertEqual(row["status"], "PASS", row)
        W2, F2R = self.u["W2"], self.u["F2R"]
        inputs = self.u["F2"].outs[0].mass + W2.ins[1].mass + W2.ins[2].mass          # cake + fresh water + condensate
        outputs = F2R.outs[0].mass + F2R.outs[1].mass                                 # washed cake + wash liquor
        np.testing.assert_allclose(inputs, outputs, rtol=1e-12, atol=1e-8)
        for ID in ("CaCO3", "CaOH2"):
            self.assertAlmostEqual(float(F2R.outs[0].imass[ID]), float(self.u["F2"].outs[0].imass[ID]), places=8)
            self.assertEqual(float(F2R.outs[1].imass[ID]), 0)


if __name__ == "__main__":
    unittest.main()
