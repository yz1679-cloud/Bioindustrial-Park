"""GWP100 of the frozen ATT model (att.lca): accounting and conversions."""
import unittest
import warnings

from biorefineries.ATT.analyses import inventory as inv
from biorefineries.ATT.analyses import lca


class TestATTGWP(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = lca.create_att_lca_system()


    def test_neutralization_stoichiometry(self):
        streams = inv._streams(self.sys)
        expected = sum(float(streams[ID].imol["NaOH"] + streams[ID].imol["Na2CO3"])
                       for ID in ("liquor_purge", "f2_wash_liquor")
                       if ID in streams and streams[ID] in self.sys.products) / 2 * 98.07848
        self.assertAlmostEqual(lca._h2so4_kgph(self.sys), float(expected), places=6)


if __name__ == "__main__":
    unittest.main()
