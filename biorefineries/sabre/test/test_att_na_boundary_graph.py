"""Regression tests for graph-derived ATT external Na boundary."""
import unittest
from biorefineries.sabre.analyses.att.validation import read_only_att_na_probe

class FakeStream:
    def __init__(self, ID, naoh=0):
        self.ID=ID; self.imass={'NaOH':naoh,'Na2CO3':0.0}
    def get_atomic_flow(self, symbol):
        assert symbol=='Na'
        return self.imass['NaOH']/39.997

class FakeUnit:
    def __init__(self, ID, ins, outs):
        self.ID=ID; self.ins=ins;self.outs=outs

class FakeSystem:
    def __init__(self, units): self.units=units

class TestGraphAudit(unittest.TestCase):
    def test_without_washer(self):
        feed=FakeStream('feed',1); product=FakeStream('cake',1)
        rep=read_only_att_na_probe(FakeSystem([FakeUnit('F2',[feed],[product])]))
        self.assertEqual(rep['audited_unit_count'],1)
        self.assertTrue(rep['total_external_Na_balance_pass'])
        self.assertEqual([x['id'] for x in rep['external_product_streams']],['cake'])

    def test_washer_new_final_cake_is_counted(self):
        feed=FakeStream('feed',1)
        cake=FakeStream('old_cake',.1); filtrate=FakeStream('old_filtrate',.9)
        wash=FakeStream('wash',0)
        final_cake=FakeStream('washed_cake',.01); washed_liquor=FakeStream('washed_liquor',.99)
        units=[FakeUnit('F2',[feed],[cake,filtrate]),FakeUnit('W2',[cake,filtrate,wash],[final_cake,washed_liquor])]
        rep=read_only_att_na_probe(FakeSystem(units))
        self.assertTrue(rep['all_unit_Na_balances_pass'])
        self.assertTrue(rep['total_external_Na_balance_pass'])
        self.assertEqual(rep['audited_unit_ids'],['F2','W2'])
        out_ids={s['id'] for s in rep['external_product_streams']}
        self.assertEqual(out_ids,{'washed_cake','washed_liquor'})
        self.assertNotIn('old_cake',out_ids)

    def test_unbalanced_washer_detected(self):
        feed=FakeStream('feed',1)
        oldcake=FakeStream('old_cake',.1); oldliq=FakeStream('old_liquor',.9)
        wash=FakeStream('wash',0)
        finalcake=FakeStream('washed_cake',.01); finalliq=FakeStream('washed_liquor',.98)
        units=[FakeUnit('F2',[feed],[oldcake,oldliq]),
               FakeUnit('W2',[oldcake,oldliq,wash],[finalcake,finalliq])]
        rep=read_only_att_na_probe(FakeSystem(units))
        self.assertFalse(rep['all_unit_Na_balances_pass'])
        self.assertFalse(rep['total_external_Na_balance_pass'])

    def test_duplicate_unit_ids_rejected(self):
        s=FakeStream('s',1)
        with self.assertRaises(ValueError):
            read_only_att_na_probe(FakeSystem([FakeUnit('X',[s],[s]),FakeUnit('X',[s],[s])]))

    def test_empty_rejected(self):
        with self.assertRaises(ValueError): read_only_att_na_probe(FakeSystem([]))

if __name__=='__main__': unittest.main()
