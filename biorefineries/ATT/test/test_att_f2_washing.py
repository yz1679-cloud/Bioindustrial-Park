import unittest
from biorefineries.ATT.analyses.mass_energy import wash_balance

BASE=dict(dry_insolubles=1.0,retained_water=.4,retained_naoh=.14,retained_na2co3=.033,filtrate_water=3.,filtrate_naoh=1.04,filtrate_na2co3=.244,target_moisture=.25)

class TestWashing(unittest.TestCase):
    def test_wash_conserves_solute_and_water(self):
        r=wash_balance(**BASE,wash_water=1)
        self.assertLess(r['cake']['NaOH'],.14)
        self.assertGreater(r['filtrate']['NaOH'],1.04)
        self.assertAlmostEqual(r['cake']['NaOH']+r['filtrate']['NaOH'],1.18)
        self.assertAlmostEqual(r['cake']['Water']+r['filtrate']['Water'],4.4)

if __name__=='__main__': unittest.main()
