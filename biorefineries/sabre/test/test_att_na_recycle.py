"""Sodium ledger tests, no BioSTEAM dependency."""
from __future__ import annotations
import unittest

from biorefineries.sabre.analyses._att_na_recycle import (
    sodium_kgph, composition, get_stream_sodium, native_unit_sodium_ledger,
    read_only_att_na_probe, MW_NA,
)

class TestComposition(unittest.TestCase):
    def test_naoh_formula(self):
        self.assertAlmostEqual(sodium_kgph({'NaOH':39.997,'Na2CO3':0,'Water':0}), MW_NA)
    def test_carbonate_formula(self):
        self.assertAlmostEqual(sodium_kgph({'NaOH':0,'Na2CO3':105.9888,'Water':0}),2*MW_NA)
    def test_water_carries_no_sodium(self):
        self.assertEqual(sodium_kgph({'NaOH':0,'Na2CO3':0,'Water':10}),0)
    def test_require_three_components(self):
        with self.assertRaises(ValueError): composition({'NaOH':1,'Water':1})
    def test_no_extra_component_sneaks_in(self):
        with self.assertRaises(ValueError): composition({'NaOH':1,'Na2CO3':2,'Water':1,'NaCl':1})
    def test_negative_mass(self):
        with self.assertRaises(ValueError): composition({'NaOH':-1,'Na2CO3':0,'Water':0})
    def test_nan(self):
        with self.assertRaises(ValueError): composition({'NaOH':float('nan'),'Na2CO3':0,'Water':0})
    def test_inf(self):
        with self.assertRaises(ValueError): composition({'NaOH':float('inf'),'Na2CO3':0,'Water':0})
    def test_strings_rejected(self):
        with self.assertRaises(ValueError): composition({'NaOH':'bad','Na2CO3':0,'Water':0})

class Stream:
    def __init__(self, id, naoh, carb, atomic_kmolph=None):
        self.ID=id;self.imass={'NaOH':naoh,'Na2CO3':carb}
        self._atomic=atomic_kmolph
        self.source=None;self.sink=None
    def get_atomic_flow(self, element):
        assert element=='Na'
        if self._atomic is not None: return self._atomic
        return sodium_kgph({'NaOH':self.imass['NaOH'],'Na2CO3':self.imass['Na2CO3'],'Water':0})/MW_NA
class Unit:
    def __init__(self,id,ins,outs):
        self.ID=id;self.ins=ins;self.outs=outs
        for s in ins: s.sink=self
        for s in outs: s.source=self
class Obj: pass

class TestNative(unittest.TestCase):
    def test_stream_species_and_atomic_same(self):
        s=Stream('x',1,2)
        d=get_stream_sodium(s)
        self.assertAlmostEqual(d['other_Na_in_other_species_or_thermo_kgph'],0)
    def test_stream_detects_other_na(self):
        s=Stream('x',1,2)
        s._atomic=(sodium_kgph({'NaOH':1,'Na2CO3':2,'Water':0})+.01)/MW_NA
        self.assertAlmostEqual(get_stream_sodium(s)['other_Na_in_other_species_or_thermo_kgph'],.01)
    def test_unit_balanced_reaction(self):
        a=Stream('in',2*39.997,0)
        b=Stream('out',0,105.9888)
        u=Unit('U2',[a],[b])
        self.assertTrue(native_unit_sodium_ledger(u)['balance_pass'])
    def test_unit_fail_loss(self):
        a=Stream('in',1,0);b=Stream('out',0,0)
        self.assertFalse(native_unit_sodium_ledger(Unit('u',[a],[b]))['balance_pass'])
    def test_external_boundary_two_units(self):
        feed=Stream('feed',2*39.997,0)
        midway=Stream('midway',0,105.9888)
        final=Stream('final',0,105.9888)
        u1=Unit('P1',[feed],[midway])
        u2=Unit('D0',[midway],[final])
        # Pass-through units named like the current ATT flowsheet.
        names=('P1','D0','M1','U2','U3HX','U3C','U3D','U3P','U3K','RC1','D1','F1','C1','F2','SP1','EC1','M2')
        registry=Obj(); setattr(registry,'P1',u1); setattr(registry,'D0',u2)
        prev=final
        for name in names[2:]:
            nxt=Stream('out_'+name,0,105.9888)
            setattr(registry,name,Unit(name,[prev],[nxt]));prev=nxt
        fs=Obj();fs.unit=registry
        sys=Obj();sys.flowsheet=fs;sys.units=[getattr(registry,name) for name in names]
        r=read_only_att_na_probe(sys)
        self.assertEqual(len(r['unit_ledger']),len(names))
        self.assertTrue(r['all_unit_Na_balances_pass'])
        self.assertTrue(r['total_external_Na_balance_pass'])
        self.assertAlmostEqual(r['external_Na_residual_kgph'],0)

if __name__=='__main__':unittest.main(verbosity=2)
