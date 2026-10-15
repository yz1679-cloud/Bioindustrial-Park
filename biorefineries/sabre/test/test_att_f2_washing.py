import unittest
from biorefineries.sabre.analyses._att_f2_washing import wash_balance

BASE=dict(dry_insolubles=1.0,retained_water=.4,retained_naoh=.14,retained_na2co3=.033,filtrate_water=3.,filtrate_naoh=1.04,filtrate_na2co3=.244,target_moisture=.25)

class TestWashing(unittest.TestCase):
    def test_zero_wash_returns_original(self):
        r=wash_balance(**BASE,wash_water=0)
        self.assertAlmostEqual(r['cake']['NaOH'],.14)
        self.assertEqual(r['cake']['Water'],.4)
    def test_solute_recovery(self):
        r=wash_balance(**BASE,wash_water=1)
        self.assertLess(r['cake']['NaOH'],.14)
        self.assertGreater(r['filtrate']['NaOH'],1.04)
        self.assertAlmostEqual(r['cake']['NaOH']+r['filtrate']['NaOH'],1.18)
    def test_water_conservation(self):
        r=wash_balance(**BASE,wash_water=1)
        self.assertAlmostEqual(r['cake']['Water']+r['filtrate']['Water'],4.4)
    def test_moisture(self):
        r=wash_balance(**BASE,wash_water=1)
        self.assertAlmostEqual(r['cake_moisture'],.25)
    def test_more_wash_more_recovery(self):
        a=wash_balance(**BASE,wash_water=.5)
        b=wash_balance(**BASE,wash_water=1.5)
        self.assertLess(b['cake']['NaOH'],a['cake']['NaOH'])
    def test_negative_rejected(self):
        with self.assertRaises(ValueError): wash_balance(**BASE,wash_water=-1)
    def test_bad_target(self):
        with self.assertRaises(ValueError): wash_balance(**(BASE|{'target_moisture':1}),wash_water=1)
    def test_factor_zero(self):
        r=wash_balance(**BASE,wash_water=1,displacement_factor=0)
        self.assertAlmostEqual(r['cake']['NaOH'],.14)
    def test_nonfinite(self):
        with self.assertRaises(ValueError): wash_balance(**BASE,wash_water=float('nan'))
    def test_no_negative_outputs(self):
        r=wash_balance(**BASE,wash_water=100)
        self.assertTrue(all(x>=0 for x in r['cake'].values()))

if __name__=='__main__': unittest.main()
