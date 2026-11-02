# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Azhar Razin,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.
"""
Techno-economic analysis base class of the ATT flowsheet (the SaBRe TEA).
"""
import biosteam as bst

__all__ = ('SaBReTEA',)


class SaBReTEA(bst.TEA):
    """
    Simplified TEA

    Assumptions:
    - Fixed operating cost (FOC) is modeled as a fraction of FCI.
    - Variable operating cost (VOC) is taken from BioSTEAM system-level
      material and utility costs, plus any unit-level add_OPEX.
    """

    def __init__(
        self,
        *args,
        foc_frac_of_fci: float = 0.04,
        **kwargs,
    ):
        self.foc_frac_of_fci = float(foc_frac_of_fci)
        super().__init__(*args, **kwargs)

    def _FOC(self, FCI):
        return self.foc_frac_of_fci * FCI

    def _annual_unit_add_opex(self):
        """
        Sum all unit-level add_OPEX contributions and annualize them.
        These are stored as $/hr on the units.
        """
        hourly = 0.0
        for u in self.system.units:
            add_opex = getattr(u, "add_OPEX", None)
            if not add_opex:
                continue

            if isinstance(add_opex, dict):
                hourly += sum(float(v or 0.0) for v in add_opex.values())
            else:
                hourly += float(add_opex or 0.0)

        return hourly * self.operating_days * 24.0

    @property
    def VOC(self):
        """
        Override BioSTEAM's default VOC property so reagent add_OPEX is included
        in the cashflow / MSP calculation --> for reagent cost and other OPEX
        """
        return (
            self.material_cost
            + self.utility_cost
            + self._annual_unit_add_opex()
        )

