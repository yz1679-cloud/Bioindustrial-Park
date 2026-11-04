"""
Independent checks of the ATT S1 baseline.

The other tests compare the model with its own pinned values or with its own balance routines. The checks here
recompute a result from first principles, from boundary data and textbook formulas, without calling the routines that
produced it:

* whole-flowsheet mass and element balance, from the feed and product streams only (every unit, recycle and the heat
  integration included);
* the H2 product from the experimental gas yield, by hand;
* flows that scale linearly with the dry feed (mass balance is scale free);
* the discounted cash flow: an independent re-implementation of the MSP arithmetic (MACRS-7 depreciation, annuity
  loan, start-up year, loss carry-forward, tax, discounting) from the capital and operating costs, reproducing the
  BioSTEAM cash flow table and showing that the MSP is the price at which the NPV at the required IRR is zero.

None of these checks changes the model. They add no pinned numbers beyond the experimental inputs of the design basis
(docs/ATT_S1_S2_DESIGN_BASIS_AND_LIMITATIONS.md).
"""
import unittest
import warnings
from collections import defaultdict

import numpy as np

from biorefineries.ATT.analyses import inventory as inv
from biorefineries.ATT.analyses import scenarios as scen
from biorefineries.ATT.analyses import tea as tea_mod

H2_MW = 2.01588                                           # g/mol
# Experimental summary values (design basis, evidence table): Ni-CatATT 1:1 gas yields on the daf feed [mmol/g daf].
YIELD = {"H2": 54.15, "CH4": 0.60, "CO": 0.0, "CO2": 0.77}
DAF_FRACTION = 1.0 - 0.3207                               # presscake: ash 32.07 wt % of the dry solids (Wiatrowski 2026)
CO2_CAPTURE = 0.99                                        # scrubber design basis (att.yaml downstream.scrubber)
# IRS Publication 946, Table A-1, 7-year MACRS, half-year convention.
MACRS7 = (0.1429, 0.2449, 0.1749, 0.1249, 0.0893, 0.0892, 0.0893, 0.0446)


def _atoms(streams):
    total = defaultdict(float)
    for stream in streams:
        for chemical in stream.chemicals:
            n = float(stream.imol[chemical.ID])
            if n:
                for element, count in chemical.atoms.items():
                    total[element] += n * count
    return total


class TestWholeFlowsheetBalance(unittest.TestCase):
    """Mass and element balance of the full-scale S1 (washing, REE recovery, heat integration on)."""

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = scen.create(scen.ATT_S1)

    def test_total_mass_closes(self):
        mass_in = sum(float(s.F_mass) for s in self.sys.feeds)
        mass_out = sum(float(s.F_mass) for s in self.sys.products)
        self.assertAlmostEqual(mass_out / mass_in, 1.0, delta=1e-9)

    def test_every_element_closes(self):
        inflow, outflow = _atoms(self.sys.feeds), _atoms(self.sys.products)
        self.assertEqual(set(inflow), set(outflow))
        for element in inflow:
            self.assertAlmostEqual(outflow[element] / inflow[element], 1.0, delta=1e-8, msg=element)
        # the main elements of the process are all present, so the loop above is not vacuous
        for element in ("C", "H", "O", "N", "Na", "Ca", "K", "Cl"):
            self.assertGreater(inflow[element], 0.0, element)

    def test_boundary_has_no_stray_streams(self):
        # nothing is both a feed and a product, and every feed or product carries a recognisable flow
        feeds, products = {s.ID for s in self.sys.feeds}, {s.ID for s in self.sys.products}
        self.assertEqual(feeds & products, set())
        for stream in (*self.sys.feeds, *self.sys.products):
            self.assertTrue(np.isfinite(stream.mol).all(), stream.ID)
            self.assertTrue((stream.mol >= 0.0).all(), stream.ID)


class TestH2FromTheExperimentalYield(unittest.TestCase):
    """The H2 product by hand: daf feed x yield x molar mass (no PSA, no H2 loss)."""

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = scen.create(scen.ATT_S1)
        cls.h2 = next(s for s in cls.sys.products if s.ID == "h2_product")

    def test_h2_mass_flow(self):
        daf_kgph = scen.ATT_S1["dry_feed_kgph"] * DAF_FRACTION
        expected = daf_kgph * 1e3 * YIELD["H2"] * 1e-3 / 1e3 * H2_MW                  # kg/h
        self.assertAlmostEqual(float(self.h2.imass["H2"]) / expected, 1.0, delta=1e-9)
        self.assertAlmostEqual(float(self.h2.imass["H2"]) * self.sys.operating_hours / 1e3 / 2953.563, 1.0, delta=1e-6)

    def test_product_composition(self):
        # H2 and the unscrubbed CH4 and CO2 (CO is zero); CH4 passes, 1 % of the CO2 is not captured; no other gas
        left = {"H2": YIELD["H2"], "CH4": YIELD["CH4"], "CO2": YIELD["CO2"] * (1.0 - CO2_CAPTURE)}
        total = sum(left.values())
        for ID, y in left.items():
            self.assertAlmostEqual(float(self.h2.imol[ID]) / float(self.h2.F_mol), y / total, delta=1e-6, msg=ID)
        self.assertAlmostEqual(sum(float(self.h2.imol[ID]) for ID in left) / float(self.h2.F_mol), 1.0, delta=1e-9)


class TestLinearScaling(unittest.TestCase):
    """Flows per kg of dry feed do not depend on the plant size (the heat integration is off in both)."""

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.small = scen.create(scen.ATT_S1, dry_kgph=1.0, hxn=False)
        cls.large = scen.create(scen.ATT_S1, dry_kgph=scen.ATT_S1["dry_feed_kgph"], hxn=False)

    def test_boundary_flows_per_kg_dry(self):
        scale = scen.ATT_S1["dry_feed_kgph"]
        small = {s.ID: s for s in (*self.small.feeds, *self.small.products)}
        large = {s.ID: s for s in (*self.large.feeds, *self.large.products)}
        self.assertEqual(set(small), set(large))
        for ID in small:
            a, b = float(small[ID].F_mass), float(large[ID].F_mass) / scale
            self.assertAlmostEqual(b, a, delta=1e-6 * max(a, 1e-12) + 1e-14, msg=ID)

    def test_h2_per_kg_dry(self):
        scale = scen.ATT_S1["dry_feed_kgph"]
        a = float(next(s for s in self.small.products if s.ID == "h2_product").imass["H2"])
        b = float(next(s for s in self.large.products if s.ID == "h2_product").imass["H2"]) / scale
        self.assertAlmostEqual(b / a, 1.0, delta=1e-9)


def independent_cash_flow(tea, annual_sales, interest_only_deduction=False):
    """
    Cash flow [USD] of years -1, 0, 1, ... (two construction years, then the operating years), from first principles.

    Inputs are the plant's own cost results (fixed capital, working capital, variable and fixed operating cost) and the
    financial parameters of the TEA; everything after that is written out here:

    * capital spent in the two construction years in the proportions of the construction schedule; ``finance_fraction``
      of each year's capital is borrowed, and interest on a year's draw is paid in that year;
    * the loan is repaid in equal annual payments (annuity) over ``finance_years`` operating years;
    * the first operating year runs ``startup_months`` months at ``startup_VOCfrac`` of the variable cost and of the
      sales, the fixed cost in full;
    * MACRS-7 depreciation of the fixed capital;
    * taxable earnings = sales - operating cost - depreciation - loan payment (the BioSTEAM convention: the whole payment,
      principal included, is deducted; ``interest_only_deduction=True`` deducts only the interest instead);
    * losses are carried forward, tax is paid on the earnings left after them;
    * working capital is recovered in the last year.
    """
    fci, wc = tea.FCI, tea.working_capital
    schedule = np.asarray(tea.construction_schedule, dtype=float)
    years = len(schedule) + int(tea.duration[1] - tea.duration[0])
    rate = tea.finance_interest
    draw = tea.finance_fraction * fci * schedule
    principal = float(draw.sum())
    payment = principal * rate / (1.0 - (1.0 + rate) ** -tea.finance_years)
    balance = principal
    startup = (12.0 - tea.startup_months + tea.startup_months * tea.startup_VOCfrac) / 12.0
    cash = np.zeros(years)
    for k, d in enumerate(draw):
        cash[k] = -(fci * schedule[k] - d) - d * rate                      # equity share and interest on the draw
    cash[len(schedule) - 1] -= wc
    loss = 0.0
    for k in range(years - len(schedule)):
        y = k + len(schedule)
        share = startup if k == 0 else 1.0
        sales = annual_sales * share
        operating = tea.VOC * share + tea.FOC
        depreciation = fci * MACRS7[k] if k < len(MACRS7) else 0.0
        interest = repaid = 0.0
        if k < tea.finance_years:
            interest = balance * rate
            repaid = payment - interest
            balance -= repaid
        deductible = interest if interest_only_deduction else interest + repaid
        earnings = sales - operating - depreciation - deductible
        if earnings > 0.0:
            used = min(loss, earnings)
            loss -= used
            tax = tea.income_tax * (earnings - used)
        else:
            loss -= earnings
            tax = 0.0
        cash[y] = sales - operating - tax - (interest + repaid)
    cash[-1] += wc
    return cash


def npv_at(tea, cash):
    t = np.arange(len(cash)) - 1                                           # year -1 is discounted one year forward
    return float((cash * (1.0 + tea.IRR) ** -t).sum())


class TestIndependentDCF(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        spec = scen.ALL_SCENARIOS["att_s1"]
        cls.sys = scen.create(spec)
        cls.estimates = inv.get_att_cost_estimates(cls.sys)
        cls.result = tea_mod.evaluate_att_tea(cls.sys, cls.estimates, **scen.tea_config(spec, None))
        cls.tea = cls.sys.TEA
        cls.h2_kg_yr = float(inv._streams(cls.sys)["h2_product"].imass["H2"]) * cls.sys.operating_hours

    def test_financial_parameters_are_the_stated_basis(self):
        # design basis: IRR 10 %, 20 yr, MACRS-7, 21 % tax, 60 % debt at 8 % over 10 yr
        t = self.tea
        self.assertEqual((t.IRR, t.income_tax, t.finance_fraction, t.finance_interest, t.finance_years),
                         (0.10, 0.21, 0.60, 0.08, 10))
        self.assertEqual(str(t.depreciation), "MACRS7")
        self.assertEqual(int(t.duration[1] - t.duration[0]), 20)

    def test_cash_flow_reproduces_the_biosteam_table(self):
        table = self.tea.get_cashflow_table()
        reference = table["Cash flow [MM$]"].to_numpy() * 1e6
        mine = independent_cash_flow(self.tea, self.tea.sales)
        self.assertEqual(mine.shape, reference.shape)
        np.testing.assert_allclose(mine, reference, rtol=1e-9, atol=1e-3)

    def test_depreciation_is_the_macrs_schedule(self):
        table = self.tea.get_cashflow_table()
        dep = table["Depreciation [MM$]"].to_numpy() * 1e6
        np.testing.assert_allclose(dep[2:2 + len(MACRS7)], self.tea.FCI * np.array(MACRS7), rtol=1e-9)
        self.assertAlmostEqual(float(dep.sum()), self.tea.FCI, delta=1e-6 * self.tea.FCI)

    def test_msp_is_the_zero_npv_price(self):
        # independent NPV at the reported price is ~0; a 1 % higher price gives a clearly positive NPV
        msp = self.result["msp"]
        self.assertAlmostEqual(npv_at(self.tea, independent_cash_flow(self.tea, self.tea.sales)) / self.tea.FCI, 0.0,
                               delta=1e-6)
        higher = self.tea.sales + 0.01 * msp * self.h2_kg_yr
        self.assertGreater(npv_at(self.tea, independent_cash_flow(self.tea, higher)), 1e-3 * self.tea.FCI)

    def test_independent_root_finding_gives_the_same_msp(self):
        msp = self.result["msp"]
        lo, hi = 0.0, 10.0 * msp
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            sales = self.tea.sales + (mid - msp) * self.h2_kg_yr
            if npv_at(self.tea, independent_cash_flow(self.tea, sales)) > 0.0:
                hi = mid
            else:
                lo = mid
        self.assertAlmostEqual(mid / msp, 1.0, delta=1e-6)


if __name__ == "__main__":
    unittest.main()
