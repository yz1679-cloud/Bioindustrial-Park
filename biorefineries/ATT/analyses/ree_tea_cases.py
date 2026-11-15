"""Reporting-only reconciliation of REE economics and the existing ATT DCF.

No process parameters or TEA methods are changed. Each counterfactual price is
temporary and restored on the scratch calculation system.
"""
import math

import numpy as np
from scipy.optimize import brentq


def _group(row):
    item, category = row['item'], row['category']
    if category == 'FOC': return 'fixed'
    if category in ('CaCO3 sales', 'REE sales'): return 'coproduct_revenue'
    if category in ('waste disposal', 'CaCO3 cake', 'off-gas') or item.startswith('Purge neutralization'):
        return 'waste'
    if category == 'materials': return 'materials'
    if category in ('utilities', 'extra VOC'): return 'utilities'
    raise ValueError((item,category))


def _npv_from_table(t):
    """Discount reported cash flows independently of TEA.solve_price/solve_sales."""
    df=t.get_cashflow_table()
    return float(np.dot(df['Cash flow [MM$]'],df['Discount factor']))*1e6


def _root(t, gas, h2_fraction):
    original=gas.price
    def objective(h2_price):
        gas.price=h2_price*h2_fraction
        return _npv_from_table(t)
    try:
        lo,hi=-10.,10.
        while objective(lo)*objective(hi)>0:
            lo*=2.; hi*=2.
            if hi>1e5: raise ValueError('Could not bracket DCF selling price')
        return float(brentq(objective,lo,hi,xtol=1e-12))
    finally:
        gas.price=original


def _dcf_components(t, ledger, annual_h2):
    """Actual discounted ledger; no allocation of a residual to equipment."""
    df=t.get_cashflow_table()
    discount=df['Discount factor'].to_numpy()
    profiles={name:np.zeros(len(df)) for name in ('VOC','FOC','sales')}
    start=t._start; end=start+int(t._startup_time); partial=t._startup_time%1
    for name, frac in [('VOC',t.startup_VOCfrac),('FOC',t.startup_FOCfrac),('sales',t.startup_salesfrac)]:
        profiles[name][start:end]=frac
        profiles[name][end]=partial*frac+(1-partial)
        profiles[name][end+1:]=1.
    factors={name:float(np.dot(values,discount)) for name,values in profiles.items()}
    discounted_h2=annual_h2*factors['sales']
    def pv(name): return float(np.dot(df[name+' [MM$]'],discount))*1e6
    rows=[]
    def add(component,group,amount,basis):
        rows.append(dict(component=component,group=group,present_value_usd=amount,
                         usd_per_kg_H2=amount/discounted_h2,basis=basis))
    for row in ledger:
        profile=('FOC' if row['category']=='FOC' else 'VOC' if row['category'] in ('materials','utilities','extra VOC') else 'sales')
        add(row['item'],row['cost_group'],row['USD_per_yr']*factors[profile],profile+' startup profile discounted at IRR')
    add('Fixed capital including modeled replacements','capital',pv('Fixed capital investment'),'Actual DCF fixed-capital column')
    add('Working capital, net of terminal recovery','working_capital',pv('Working capital'),'Actual DCF working-capital column')
    add('Loan proceeds','financing',-pv('Loan'),'Actual DCF loan column')
    construction_interest=0.
    if t.finance_interest and not t.accumulate_interest_during_construction:
        construction_interest=float(np.dot(df['Loan interest payment [MM$]'].to_numpy()[:start],discount[:start]))*1e6
    add('Debt service and construction interest','financing',pv('Loan payment')+construction_interest,'Actual DCF debt payments; no double-count of operating loan interest')
    add('Income taxes','tax',pv('Tax'),'Actual DCF tax column after depreciation and loss carryforwards')
    if pv('Incentives'): add('Incentives','incentives',-pv('Incentives'),'Actual DCF incentive column')
    return rows,factors,discounted_h2


def _snapshot(system,result,scenario,enabled):
    from biorefineries.ATT.analyses import inventory, tea
    t=result['tea']; streams=inventory._streams(system); gas=streams['h2_product']
    hours=float(system.operating_hours); h2=float(gas.imass['H2']); annual_h2=h2*hours
    ledger=[dict(x,cost_group=_group(x)) for x in tea._opex_table(system,result)
            if x['category'] not in ('capital','total')]
    for unit in system.units:
        extra=float(getattr(unit,'add_OPEX',0.) or 0.)*hours
        if extra:
            ledger.append(dict(item=unit.ID+' unit additional OPEX',category='extra VOC',USD_per_yr=extra,
                               cost_group='utilities',basis='Unit add_OPEX included by ATTTEA.VOC'))
    group={name:sum(x['USD_per_yr'] for x in ledger if x['cost_group']==name)
           for name in ('materials','utilities','waste','fixed','coproduct_revenue')}
    by_item=lambda name:sum(x['USD_per_yr'] for x in ledger if x['item']==name)
    revenue=-group['coproduct_revenue']
    gross=sum(group[name] for name in ('materials','utilities','waste','fixed'))
    crf=t.IRR/(1-(1+t.IRR)**-t._years) if t.IRR else 1/t._years
    independent=_root(t,gas,h2/float(gas.F_mass))
    rows,factors,discounted_h2=_dcf_components(t,ledger,annual_h2)
    df=t.get_cashflow_table()
    reo_revenue=-by_item('REE product sales')
    caco3_revenue=sum(x['revenue_usd_ph'] for x in result['caco3_sales'].values())*hours
    without={}
    for kind in ('reo','caco3'):
        changed=[]
        try:
            if kind=='reo' and 'ree_product' in streams:
                st=streams['ree_product']; changed.append((st,st.price)); st.price=0.
            if kind=='caco3':
                for ID,sales in result['caco3_sales'].items():
                    st=streams[ID]; changed.append((st,st.price))
                    st.price-=sales['revenue_usd_ph']/float(st.F_mass)
            without[kind]=_root(t,gas,h2/float(gas.F_mass))
        finally:
            for st,price in changed: st.price=price
    def feed_cost(ID): return float(streams[ID].cost)*hours if ID in streams else 0.
    capital=[dict(item=unit.ID+' '+type(unit).__name__,installed_cost_usd=float(unit.installed_cost),
                  ree_specific=unit.ID in ('LC1','RO1'),source='Unit installed cost, including its auxiliaries')
             for unit in system.units if unit.installed_cost]
    capital += [dict(item=name,installed_cost_usd=value,ree_specific=False,source=source)
                for name,value,source in result['capital_items']]
    fci_factor=next((1+value/(sum(u.installed_cost for u in system.units)) for name,value,_ in result['capital_items'] if name.startswith('FCI factor')),1.)
    case=dict(scenario=scenario,ree_enabled=enabled,operating_hours=hours,h2_kg_per_hour=h2,h2_kg_per_year=annual_h2,
        FCI_usd=float(t.FCI),installed_capital_sum_usd=sum(x['installed_cost_usd'] for x in capital),
        ree_equipment_capex_usd=sum(x['installed_cost_usd'] for x in capital if x['ree_specific'])*fci_factor,
        materials_usd_per_year=group['materials'],utilities_usd_per_year=group['utilities'],
        waste_usd_per_year=group['waste'],fixed_usd_per_year=group['fixed'],
        gross_opex_usd_per_year=gross,coproduct_revenue_usd_per_year=revenue,
        reo_revenue_usd_per_year=reo_revenue,caco3_revenue_usd_per_year=caco3_revenue,
        net_opex_usd_per_year=gross-revenue,screening_capital_usd_per_year=t.FCI*crf,
        net_treatment_cost_usd_per_year=gross-revenue+t.FCI*crf,capital_recovery_factor=crf,
        dcf_msp_usd_per_kg_H2=result['msp'],independent_msp_usd_per_kg_H2=independent,
        discounted_cashflow_residual_usd=_npv_from_table(t),
        msp_without_reo_revenue=without['reo'],msp_without_caco3_revenue=without['caco3'],
        HCl_usd_per_year=by_item('HCl (31 %)'),HCl_feed_cost_usd_per_year=feed_cost('fresh_hcl'),
        oxalic_usd_per_year=by_item('Oxalic acid'),oxalic_feed_cost_usd_per_year=feed_cost('fresh_oxalic_acid'),
        NaOH_usd_per_year=by_item('NaOH makeup')+by_item('NaOH (REE leach)'),
        electricity_usd_per_year=by_item('Electricity: modeled units')+sum(x['USD_per_yr'] for x in ledger if 'WHR:' in x['item'] and ('electricity' in x['item'] or 'pump' in x['item'])),
        raw_TEA_AOC_usd_per_year=float(t.AOC),working_capital_usd=float(t.working_capital),
        depreciation_total_usd=float(df['Depreciation [MM$]'].sum())*1e6,
        replacement_capital_usd=float(df['Fixed capital investment [MM$]'].iloc[t._start:].sum())*1e6,
        taxes_present_value_usd=float(np.dot(df['Tax [MM$]'],df['Discount factor']))*1e6,
        discounted_h2_kg=discounted_h2,VOC_discount_factor=factors['VOC'],
        FOC_discount_factor=factors['FOC'],sales_discount_factor=factors['sales'],
        finance_accumulate_interest_during_construction=bool(t.accumulate_interest_during_construction))
    prefix=dict(scenario=scenario,ree_enabled=enabled)
    cashflows=[dict(prefix,year=int(year),**row) for year,row in df.to_dict('index').items()]
    return case,[dict(prefix,**x) for x in ledger],[dict(prefix,**x) for x in capital],\
        [dict(prefix,**x) for x in rows],cashflows


def collect_ree_tea(industrial_cases=None):
    """Rebuild all six existing financial cases and verify their DCF credits."""
    import biosteam as bst
    from biorefineries.ATT.analyses import scenarios, tea, marine_tea, marine_whr
    from biorefineries.ATT.analyses.s3_industrial import run as s3_run
    output={key:[] for key in ('cases','ledger','equipment','dcf_components','cashflows','increments')}
    for enabled in (False,True):
        system=scenarios.create(scenarios.ATT_S1,ree_recovery=enabled)
        base=tea.evaluate_att_tea(system); base_fci=base['tea'].FCI
        def save(scenario,result):
            records=_snapshot(system,result,scenario,enabled)
            for key,rows in zip(('cases','ledger','equipment','dcf_components','cashflows'),records):
                output[key].extend([rows] if key=='cases' else rows)
        save('S1',base)
        config=marine_tea.load_tea_config(); _,hours,load=marine_tea.operating_mode()
        whr=marine_whr.evaluate_whr(system,load=load)
        steam=sum(a['assigned_kW']*a['usd_per_kWh'] for a in whr['assignments'] if 'steam' in a['sink_utility'])
        fired=sum(a['assigned_kW']*a['usd_per_kWh'] for a in whr['assignments'] if 'natural_gas' in a['sink_utility'])
        share=config['s1_labor_share_of_foc']; rate=tea._FIN['foc_frac_of_fci']
        marine=tea.evaluate_att_tea(system,operating_hours=hours,fci_factor=config['capex_multiplier'],
            extra_capital=whr['equipment'],extra_voc=[
                ('Marine WHR: purchased LP steam displaced',-steam*hours),
                ('Marine WHR: U2 furnace natural gas displaced (feed preheat)',-fired*hours),
                ('Marine WHR: pump electricity',whr['pump_kW']*bst.PowerUtility.price*hours)],
            foc_frac_of_fci=rate*(1-share),foc_fixed=config['labor_multiplier']*share*rate*base_fci)
        save('S2',marine)
        s=industrial_cases[str(enabled)] if industrial_cases is not None else s3_run(enable_ree_recovery=enabled)
        industrial=tea.evaluate_att_tea(system,operating_hours=s['operating_hours_per_year'],
            extra_capital=[('Industrial WHR installed screening allowance',s['incremental_capex_usd'],'Existing S3 allowance')],
            extra_voc=[('Industrial WHR: avoided heat',-s['avoided_cost_usd_per_year']),
                       ('Industrial WHR: auxiliary electricity',s['auxiliary_electricity_cost_usd_per_year']),
                       ('Industrial WHR: heat purchase',s['heat_purchase_cost_usd_per_year'])])
        if not math.isclose(industrial['msp'],s['s3_MSP_usd_per_kg_H2'],abs_tol=1e-9):
            raise ValueError('Rebuilt S3 TEA differs from its existing calculation')
        save('S3',industrial)
    for scenario in ('S1','S2','S3'):
        off,on=[next(x for x in output['cases'] if x['scenario']==scenario and x['ree_enabled']==enabled) for enabled in (False,True)]
        keys=('h2_kg_per_year','operating_hours','FCI_usd','ree_equipment_capex_usd','gross_opex_usd_per_year',
              'materials_usd_per_year','utilities_usd_per_year','waste_usd_per_year','fixed_usd_per_year',
              'coproduct_revenue_usd_per_year','reo_revenue_usd_per_year','caco3_revenue_usd_per_year',
              'net_opex_usd_per_year','screening_capital_usd_per_year','net_treatment_cost_usd_per_year',
              'HCl_usd_per_year','oxalic_usd_per_year','NaOH_usd_per_year','electricity_usd_per_year',
              'working_capital_usd','replacement_capital_usd','taxes_present_value_usd')
        row=dict(scenario=scenario,**{'delta_'+key:on[key]-off[key] for key in keys},
                 delta_msp_usd_per_kg_H2=on['dcf_msp_usd_per_kg_H2']-off['dcf_msp_usd_per_kg_H2'],
                 off_msp_usd_per_kg_H2=off['dcf_msp_usd_per_kg_H2'],on_msp_usd_per_kg_H2=on['dcf_msp_usd_per_kg_H2'])
        row['screening_cost_change_usd_per_kg_H2']=row['delta_net_treatment_cost_usd_per_year']/on['h2_kg_per_year']
        output['increments'].append(row)
    output['financial_assumptions']=dict(tea._FIN)
    return output
