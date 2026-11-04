"""Every boundary stream and utility of the S1 flowsheet has a documented price basis (tea.yaml) and emission basis (lca.yaml)."""
import unittest
import warnings

from biorefineries.ATT.analyses import scenarios as scen
from biorefineries.ATT.utils import load_assumptions

UTILITIES = {"natural_gas", "low_pressure_steam", "cooling_water", "electricity"}


class TestStreamRegister(unittest.TestCase):

    def test_every_boundary_stream_and_utility_is_documented(self):
        warnings.filterwarnings("ignore")
        system = scen.create(scen.ATT_S1, dry_kgph=1.0)
        streams = {s.ID for s in (*system.feeds, *system.products)}
        prices = load_assumptions("tea.yaml")
        factors = load_assumptions("lca.yaml")["lca"]
        self.assertEqual(streams - set(prices["stream_prices"]), set())
        self.assertEqual(streams - set(factors["stream_factors"]), set())
        self.assertEqual(UTILITIES - set(prices["utility_prices"]), set())
        self.assertEqual(UTILITIES - set(factors["utility_factors"]), set())
        for note in (*prices["stream_prices"].values(), *factors["stream_factors"].values()):
            self.assertTrue(str(note).strip())


if __name__ == "__main__":
    unittest.main()
