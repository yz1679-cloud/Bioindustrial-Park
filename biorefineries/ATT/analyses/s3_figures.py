"""
The 10-page S3 figure PDF of the advisor meeting (S3 REE On), drawn from the model.

Run:  python -m biorefineries.ATT.analyses.s3_figures [--out DIR]       (default: results/s3_figures/ATT_S3_Figures.pdf)

Every number comes from a run of the model in this checkout: the cases of the comprehensive report (comprehensive_report),
the industrial heat case (s3_industrial), and the four stages P0 (pessimistic disposal) to P3 (S3) of the waterfall.
The EROI and the hydrogen benchmarks are computed in headline_results. The checks inside raise if the groupings of the
figures do not add up to the totals they explain. Nothing is written but the PDF and a JSON file with its values.
"""
import argparse
import json
import math
import textwrap
from collections import defaultdict
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle, Patch

from biorefineries.ATT.analyses import headline_results as hr
from biorefineries.ATT.analyses import inventory, scenarios
from biorefineries.ATT.analyses.paths import output_dir

COL = dict(ink='#233746',muted='#5E6C76',line='#D8E0E5',wash='#F2F5F7',
    materials='#4477AA',heat='#CC7744',electricity='#D3A638',waste='#88949A',
    fixed='#9B83B8',capital='#66558F',tax='#B09BC5',caco3='#228877',ree='#66AA99',
    whr='#66A8C7',storage='#337766',hxn='#A7C7A3',other='#AA6677',bad='#B5524D')
INK, MUTED, LINE, WASH = COL['ink'], COL['muted'], COL['line'], COL['wash']
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.labelsize':10,
    'axes.titlesize':12,'axes.titleweight':'bold','axes.edgecolor':COL['line'],
    'text.color':COL['ink'],'axes.labelcolor':COL['ink'],'xtick.color':COL['muted'],
    'ytick.color':COL['muted'],'pdf.fonttype':42,'ps.fonttype':42,
    'axes.spines.top':False,'axes.spines.right':False,'axes.spines.left':False,
    'axes.grid':False,'savefig.facecolor':'white','figure.facecolor':'white',
    'text.parse_math':False})

# Hydrogen benchmarks: the prices and GWP values are in headline_results; the sources are listed here.
BENCHMARKS=[dict(name='Gray',technology='Natural gas SMR without CCS',
        cost_source='NETL 2022 [1]; illustrative price, not its exact LCOH',ci_source='Argonne 2024 [3], §5: 9.3, excluding plant CapEx'),
    dict(name='Blue',technology='Natural gas SMR with high-capture CCS',
        cost_source='DOE Liftoff 2024 [2]: approximately $2/kg production cost',ci_source='Argonne 2024 [3], Fig. 5: approximately 3.5, including CapEx'),
    dict(name='Green',technology='Wind-powered PEM water electrolysis',
        cost_source='DOE Liftoff 2024 [2]: midpoint of $5–7/kg cost range',ci_source='Argonne 2024 [3], Fig. 5: rounded wind PEM value, including CapEx')]
for _b in BENCHMARKS:
    _b['price'], _b['ci'] = hr.BENCHMARKS[_b['name']]

CHECKS = []
def check(name, actual, expected, atol=1e-7, rtol=1e-8):
    ok = math.isclose(float(actual),float(expected),abs_tol=atol,rel_tol=rtol)
    CHECKS.append(dict(check=name,actual=float(actual),expected=float(expected),status='PASS' if ok else 'FAIL'))
    if not ok: raise AssertionError(CHECKS[-1])


# ---------------------------------------------------------------------------
# Data: filled by _load()
# ---------------------------------------------------------------------------

C = B = S = ECON = DCF = LCA = U = None
DRY = H2 = HOURS = YIELD = ANNUAL_T = None


def _stages():
    """P0 (pessimistic disposal), P1 (S1 REE off), P2 (S1 REE on) and P3 (S3 REE on): MSP and GWP, and the S3 industrial case."""
    from biorefineries.ATT.analyses import lca, tea
    from biorefineries.ATT.analyses.s3_industrial import run as s3_run
    from biorefineries.ATT.analyses.breakdown import build_att_breakdown
    stages = {}
    for enabled, stage in [(False, 'P1'), (True, 'P2')]:
        system = scenarios.create(scenarios.ATT_S1, ree_recovery=enabled)
        summary = build_att_breakdown('att_s1', sys=system)['summary']
        streams = inventory._streams(system)
        stages[stage] = dict(msp=summary['MSP_USD_per_kg_H2'], gwp=summary['GWP_kgCO2e_per_kg_H2'])
        if enabled:
            continue
        prices_before = {s.ID: float(s.price) for s in (*system.feeds, *system.products)}
        baseline = tea.evaluate_att_tea(system)
        cake_ids = tuple(baseline['caco3_sales'])
        try:
            # P0: no CaCO3 sale; both cakes and the ATT char are disposed of at the existing 0.04 USD/kg disposal price
            result = tea.evaluate_att_tea(system, caco3_sales=None,
                price_overrides={**scenarios.tea_config()['price_overrides'], 'att_char': -0.04})
            for ID in cake_ids:
                if not np.isclose(streams[ID].price, -0.04):
                    raise ValueError('Full cake disposal not enabled: '+ID)
            lca.apply_att_gwp(system, overrides=scenarios.lca_overrides())
            h2 = float(streams['h2_product'].imass['H2'])
            gwp = system.get_net_impact(lca.KEY)/system.operating_hours/h2
            cake = sum(float(streams[ID].F_mass) for ID in cake_ids)
            char = float(streams['att_char'].F_mass)
            stages['P0'] = dict(msp=result['msp'], gwp=gwp, cake_disposal_kgph=cake, char_disposal_kgph=char,
                cake_disposal_usd_per_year=cake*0.04*system.operating_hours, char_disposal_usd_per_year=char*0.04*system.operating_hours)
        finally:
            tea.evaluate_att_tea(system)
            for st in (*system.feeds, *system.products):
                st.price = prices_before[st.ID]
    industrial = s3_run(enable_ree_recovery=True)
    stages['P3'] = dict(msp=industrial['s3_MSP_usd_per_kg_H2'], gwp=industrial['s3_GWP_kg_per_kg_H2'])
    assert np.isclose(stages['P0']['gwp'], stages['P1']['gwp'], rtol=1e-10)         # disposal does not change the carbon storage
    return stages, industrial


def _load():
    """Run the model and set the data the pages read."""
    global C, B, S, ECON, DCF, LCA, U, DRY, H2, HOURS, YIELD, ANNUAL_T
    from biorefineries.ATT.analyses.comprehensive_report import clean, collect, tables
    data = collect()
    R = clean(dict(data, tables=tables(data)))
    stages, S = _stages()
    C = dict(stages=stages)
    B = R['details']['True']['base']
    DRY = float(scenarios.ATT_S1['dry_feed_kgph'])
    H2 = S['h2_kg_per_hour']
    HOURS = S['operating_hours_per_year']
    YIELD = H2/DRY*1000
    ANNUAL_T = DRY*HOURS/1000
    U = {r['item']:r['per_kg_dry'] for r in B['utilities']}
    ECON = next(r for r in R['ree_tea']['cases'] if r['scenario']=='S3' and r['ree_enabled'])
    DCF = [r for r in R['ree_tea']['dcf_components'] if r['scenario']=='S3' and r['ree_enabled']]
    LCA = [r for r in R['tables']['lca_breakdown'] if r['scenario']=='S3' and str(r['ree_enabled'])=='True']
    # the two independent computations of the same S1 and S3 prices agree
    check('P3 MSP equals the S3 REE-on DCF case', stages['P3']['msp'], ECON['dcf_msp_usd_per_kg_H2'], atol=1e-6)


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def fmt(v, digits=2):
    if v is None: return '—'
    if isinstance(v,str): return v
    return f'{v:,.{digits}f}'


def wrap(s, width):
    return '\n'.join('\n'.join(textwrap.wrap(p,width=width,break_long_words=True,break_on_hyphens=False) or ['']) for p in str(s).split('\n'))


class Book:
    def __init__(self,pdf): self.pdf=pdf; self.page=0; self.pages=[]
    def new(self,title,kicker='S3 · LAND-BASED INDUSTRIAL WHR · REE ON',subtitle=None):
        self.page+=1
        f=plt.figure(figsize=(13,8.5))
        f.text(.047,.954,kicker.upper(),fontsize=8.8,color=COL['caco3'],weight='bold')
        f.text(.047,.910,title,fontsize=20,weight='bold')
        if subtitle: f.text(.047,.872,subtitle,fontsize=10,color=COL['muted'])
        f.add_artist(plt.Line2D([.047,.953],[.071,.071],transform=f.transFigure,color=COL['line'],lw=.8))
        f.text(.047,.041,f'ATT  |  S3 figures  |  computed from the model on {date.today():%B %d, %Y}',fontsize=7.5,color=COL['muted'])
        f.text(.953,.041,f'{self.page:02d}',fontsize=8,ha='right',color=COL['muted'])
        self.pages.append(title)
        return f
    def save(self,f):
        self.pdf.savefig(f)
        plt.close(f)


def paragraph(fig,text,x=.05,y=.19,width=138,fs=9,color=None):
    fig.text(x,y,wrap(text,width),ha='left',va='top',fontsize=fs,linespacing=1.45,color=color or COL['muted'])


def note(fig, text, x, y, width, fs=9.5):
    fig.text(x, y, '\n'.join(textwrap.wrap(text, width, break_long_words=False)),
             fontsize=fs, va='top', color=MUTED, linespacing=1.35)


def table(fig,columns,rows,widths=None,top=.82,bottom=.15,fs=9,x=.047,total_width=.906,row_colors=None):
    """Draw a bounded, wrapped vector table; fail if it cannot fit on the page."""
    if widths is None: widths=[1/len(columns)]*len(columns)
    widths=np.array(widths)/sum(widths)*total_width
    # At 13 inches, 936 pt page width; ~0.53 em per text character.
    caps=[max(5,int(w*936/(fs*.55))-2) for w in widths]
    lines=[[wrap(v,cap) for v,cap in zip(row,caps)] for row in [columns]+list(rows)]
    heights=[max(v.count('\n')+1 for v in row)*fs*1.30/612+.015 for row in lines]
    if top-sum(heights)<bottom:
        raise ValueError(f'Table exceeds page: needs {sum(heights):.3f}, has {top-bottom:.3f}; rows={len(rows)}')
    y=top
    for i,(row,height) in enumerate(zip(lines,heights)):
        bg=COL['ink'] if i==0 else (COL['wash'] if i%2 else '#FFFFFF')
        fig.add_artist(Rectangle((x,y-height),total_width,height,transform=fig.transFigure,facecolor=bg,edgecolor='none',zorder=0))
        if row_colors and i>0 and i<=len(row_colors):
            fig.add_artist(Rectangle((x-.012,y-height+.006),.006,height-.012,
                transform=fig.transFigure,facecolor=row_colors[i-1],edgecolor='none',zorder=2))
        left=x
        for val,w in zip(row,widths):
            fig.text(left+.007,y-.008,val,fontsize=fs,va='top',color='white' if i==0 else COL['ink'],
                     weight='bold' if i==0 else 'normal',linespacing=1.3)
            left+=w
        y-=height
    return y


def style(ax,ylabel):
    ax.set_ylabel(ylabel,labelpad=10)
    ax.axhline(0,color=COL['muted'],lw=.8)
    ax.yaxis.grid(True,color=COL['line'],lw=.6,zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(axis='both',length=0)


def stack(ax,x,components,width=.58,label_threshold=0,number_fmt='.2f'):
    pos=neg=0.
    for label,value,color in components:
        base=pos if value>=0 else neg
        ax.bar(x,value,width,bottom=base,color=color,edgecolor='white',linewidth=.65,zorder=3,label=label)
        if abs(value)>label_threshold:
            ax.text(x,base+value/2,format(value,number_fmt),ha='center',va='center',fontsize=8.5,
                    color='white' if color in (COL['materials'],COL['capital'],COL['caco3'],COL['storage'],COL['ink'],COL['bad']) else COL['ink'])
        if value>=0: pos+=value
        else: neg+=value
    return pos,neg


def leg_entry(fig, x, y, label, color, fs=10.6):
    fig.add_artist(Rectangle((x, y-.006), .014, .016, transform=fig.transFigure, facecolor=color, edgecolor='none'))
    fig.text(x+.022, y+.001, label, fontsize=fs, va='center')


def stacked(ax, items, factor=1, negative_hatches=False):
    pos = neg = 0.0
    span = sum(abs(v * factor) for _, v, _ in items)
    for i, (name, value, color) in enumerate(items):
        v = value * factor
        bottom = pos if v >= 0 else neg
        hatch = ('///', '\\\\', 'xx')[i % 3] if v < 0 and negative_hatches else None
        ax.bar(0, v, .66, bottom=bottom, color=color, edgecolor='white', linewidth=.8, hatch=hatch, zorder=3)
        if abs(v) / span >= .065:                       # interior labels only where the segment has room
            rgb = matplotlib.colors.to_rgb(color)
            lum = .2126*rgb[0] + .7152*rgb[1] + .0722*rgb[2]
            ax.text(0, bottom+v/2, f'{v:.1f}' if factor != 1 else f'{v:.2f}', ha='center', va='center', fontsize=11.5,
                    color='white' if lum < .53 else INK, weight='bold')
        if v >= 0:
            pos += v
        else:
            neg += v
    return pos, neg


# ---------------------------------------------------------------------------
# Numbers behind the pages
# ---------------------------------------------------------------------------

def energy():
    groups=defaultdict(float)
    colors={}
    for r in B['unit_energy']:
        unit=r['unit']
        if unit=='HXN': continue
        if r['kind']=='heating':
            label,color=(('ATT reactor U2',COL['heat']) if unit=='U2' else
                ('Drying D0/D2/D3',COL['materials']) if unit in ('D0','D2','D3') else
                ('NaOH evaporation EC1',COL['capital']) if unit=='EC1' else
                ('Causticization C1',COL['fixed']) if unit=='C1' else
                ('REE processing',COL['ree']) if unit in ('LC1','RO1') else
                ('Gas processing heat',COL['other']))
            groups[label]+=r['process_duty_MJ_per_kg_dry']; colors[label]=color
        if r['kind']=='electricity':
            label,color=(('Gas processing power',COL['electricity']) if unit.startswith('U3') else
                ('REE processing',COL['ree']) if unit in ('LC1','RO1') else ('Other unit power',COL['waste']))
            groups[label]+=r['electricity_kWh_per_kg_dry']*3.6; colors[label]=color
    groups['Cooling-system power']=U['Electricity: cooling tower and CW pumps (estimate)']*3.6
    colors['Cooling-system power']=COL['tax']
    hxn= -sum(r['process_duty_MJ_per_kg_dry'] for r in B['unit_energy'] if r['unit']=='HXN' and r['agent']=='low_pressure_steam')
    whr={r['source']:r['steam_kW']*3.6/DRY for r in S['source_details']}
    eta=S['steam_agent']['utility_to_process_ratio']
    eroi=hr.s3_energy_and_eroi(industrial=S)
    aux=eroi['whr_auxiliary_power_MJ_per_kg_dry']
    fuel,boiler,avoided,electric=(eroi['fuel_MJ_per_kg_dry'],eroi['boiler_fuel_S1_MJ_per_kg_dry'],
                                  eroi['avoided_boiler_fuel_MJ_per_kg_dry'],eroi['electricity_MJ_per_kg_dry'])
    process_total=sum(groups.values())
    supply=[('Fired heat to process',U['U2 natural gas: process heat'],COL['heat']),
        ('Boiler steam to process',U['LP steam: process heat'],COL['other']),
        ('Internal HXN heat',hxn,COL['hxn']),
        ('Purchased electricity',U['Electricity: total']*3.6,COL['electricity'])]
    supply_s3=[(name,value-sum(whr.values())*eta if name=='Boiler steam to process' else value,color) for name,value,color in supply]
    supply_s3 += [('H1 recovered heat to process',whr['H1']*eta,COL['whr']),
                  ('H3 recovered heat to process',whr['H3']*eta,COL['ree']),
                  ('WHR auxiliary power',aux,COL['tax'])]
    requirements=[(k,v,colors[k]) for k,v in groups.items()]
    check('Process-plane balance before WHR',process_total,sum(v for _,v,_ in supply))
    check('Process-plane balance S3',process_total+aux,sum(v for _,v,_ in supply_s3))
    check('WHR heat source sum',sum(r['steam_kW'] for r in S['source_details']),S['used_average_kW'])
    return dict(requirements=requirements,supply=supply,supply_s3=supply_s3,aux=aux,hxn=hxn,
        fuel=fuel,boiler_before=boiler,boiler_after=boiler-avoided,electric=electric,
        ext0=eroi['external_S1_MJ_per_kg_dry'],ext3=eroi['external_S3_MJ_per_kg_dry'],
        eroi_before=eroi['EROI_S1'],eroi_s3=eroi['EROI_S3'],
        eroi_all_heat=eroi['EROI_S3_counting_recovered_heat'],output=eroi['h2_output_MJ_per_kg_dry'],whr=whr,
        steam_before=U['LP steam: utility heat incl. 5 % loss'],
        steam_after=U['LP steam: utility heat incl. 5 % loss']-sum(whr.values()))


def dcf_groups():
    groups=defaultdict(float)
    for r in DCF:
        n=r['component']
        label=('WHR heat savings' if n=='Industrial WHR: avoided heat' else
            'WHR auxiliary / heat purchase' if n.startswith('Industrial WHR:') else
            'Raw materials / chemicals' if r['group']=='materials' else
            'Heating / natural gas' if n in ('Utility: natural_gas','Utility: low_pressure_steam') or n.startswith('Natural gas:') else
            'Electricity / cooling' if n in ('Utility: cooling_water','Electricity: modeled units') else
            'Waste treatment / disposal' if r['group']=='waste' else
            'Fixed operating costs' if r['group']=='fixed' else
            'CaCO3 revenue' if n.startswith('CaCO3 sales:') else
            'REE revenue' if n=='REE product sales' else
            'Capital / net financing' if r['group'] in ('capital','financing') else
            'Taxes / working capital')
        groups[label]+=r['usd_per_kg_H2']
    order=[('Raw materials / chemicals','materials'),('Heating / natural gas','heat'),
        ('Electricity / cooling','electricity'),('Waste treatment / disposal','waste'),
        ('Fixed operating costs','fixed'),('Capital / net financing','capital'),
        ('Taxes / working capital','tax'),('WHR auxiliary / heat purchase','other'),
        ('CaCO3 revenue','caco3'),('REE revenue','ree'),('WHR heat savings','whr')]
    result=[(k,groups.pop(k),COL[c]) for k,c in order]
    assert not groups
    check('Discounted MSP component sum',sum(v for _,v,_ in result),C['stages']['P3']['msp'],atol=5e-7)
    return result


def lca_groups():
    g=defaultdict(float)
    for r in LCA:
        n=r['contributor']
        label=('Direct natural gas combustion' if ': combustion' in n else
            'Upstream natural gas' if 'upstream supply' in n else
            'Purchased electricity' if n.startswith('Electricity:') else
            'NaOH input' if n=='NaOH makeup' else
            'HCl input (provisional)' if n.startswith('HCl') else
            'Oxalic acid (provisional)' if n=='Oxalic acid' else
            'Other chemicals / water' if n in ('Ca(OH)2','Process water (D1)','Purge neutralization (H2SO4)') else
            'Waste treatment' if n in ('Wastewater treatment','Landfill: solid residues') else
            'Biogenic carbon storage' if n.startswith('Biogenic carbon') else
            'Industrial WHR avoided emissions' if n=='avoided_emissions_kg_per_hour' else
            'WHR auxiliary electricity' if n=='auxiliary_emissions_kg_per_hour' else
            'WHR host heat burden')
        g[label]+=r['kgCO2e_per_kg_H2']
    order=[('Direct natural gas combustion','heat'),('Upstream natural gas','other'),
        ('Purchased electricity','electricity'),('NaOH input','materials'),
        ('HCl input (provisional)','fixed'),('Oxalic acid (provisional)','tax'),
        ('Other chemicals / water','capital'),('Waste treatment','waste'),
        ('WHR auxiliary electricity','ree'),('WHR host heat burden','hxn'),
        ('Biogenic carbon storage','storage'),('Industrial WHR avoided emissions','whr')]
    result=[(k,g.pop(k),COL[c]) for k,c in order]
    assert not g
    check('Carbon intensity component sum',sum(v for _,v,_ in result),C['stages']['P3']['gwp'])
    return result


def treatment_components(b):
    eco=[('Gross operating costs',ECON['gross_opex_usd_per_year']/ANNUAL_T,COL['heat']),
        ('Annualized capital (FCI × CRF)',ECON['screening_capital_usd_per_year']/ANNUAL_T,COL['capital']),
        ('CaCO3 revenue',-ECON['caco3_revenue_usd_per_year']/ANNUAL_T,COL['caco3']),
        ('REE revenue',-ECON['reo_revenue_usd_per_year']/ANNUAL_T,COL['ree']),
        ('H2 revenue',-YIELD*b['price'],COL['materials'])]
    # Existing ATT LCA components are carried through exactly once.
    base=lca_groups()
    positive=sum(v for _,v,_ in base if v>0)*YIELD
    storage=sum(v for k,v,_ in base if k=='Biogenic carbon storage')*YIELD
    whr=sum(v for k,v,_ in base if k=='Industrial WHR avoided emissions')*YIELD
    env=[('ATT positive emissions',positive,COL['heat']),('Existing storage credit',storage,COL['storage']),
        ('Existing WHR utility credit',whr,COL['whr']),('Additional H2 displacement',-YIELD*b['ci'],COL['materials'])]
    check(b['name']+' treatment cost',sum(v for _,v,_ in eco),
        ECON['net_treatment_cost_usd_per_year']/ANNUAL_T-YIELD*b['price'])
    check(b['name']+' treatment GWP',sum(v for _,v,_ in env),YIELD*(C['stages']['P3']['gwp']-b['ci']))
    return eco,env


def energy_page_values(E):
    """Demand and supply of S3 grouped for the energy figure (H1 + H3 summed; minor demands together)."""
    req = {k: v for k, v, _ in E['requirements']}
    supply = {k: v for k, v, _ in E['supply_s3']}
    major = ['Drying D0/D2/D3', 'ATT reactor U2', 'NaOH evaporation EC1', 'Causticization C1']
    demand = [(k, req[k], c) for k, c in zip(major, ['#0072B2', '#D55E00', '#7B3294', '#E6AB02'])]
    minor = {k: v for k, v in req.items() if k not in major}
    minor['WHR auxiliary power'] = E['aux']
    demand.append(('Other demand (heat + electricity)', math.fsum(minor.values()), '#717B83'))
    whr = supply['H1 recovered heat to process'] + supply['H3 recovered heat to process']
    delivered = [
        ('Fired heat to process', supply['Fired heat to process'], '#D55E00'),
        ('Boiler steam to process', supply['Boiler steam to process'], '#CC79A7'),
        ('Internal HXN heat', supply['Internal HXN heat'], '#0072B2'),
        ('Waste Heat Recovery', whr, '#009E73'),
        ('Purchased electricity (incl. WHR auxiliary)', supply['Purchased electricity'] + supply['WHR auxiliary power'], '#E6AB02'),
    ]
    check('Demand grouping preserves S3', math.fsum(v for _, v, _ in demand), math.fsum(req.values()) + E['aux'])
    check('Supply grouping preserves S3', math.fsum(v for _, v, _ in delivered), math.fsum(supply.values()))
    check('Demand and supply of S3 are equal', math.fsum(v for _, v, _ in demand), math.fsum(v for _, v, _ in delivered), atol=1e-6)
    return demand, delivered, DRY/H2


def contribution_values():
    d = {k: v for k, v, _ in dcf_groups()}
    l = {k: v for k, v, _ in lca_groups()}
    dcf_names = ['Raw materials / chemicals', 'Heating / natural gas', 'Electricity / cooling',
                 'Waste treatment / disposal', 'Fixed operating costs', 'Capital / net financing']
    dcf_colors = ['#0072B2', '#D55E00', '#E6AB02', '#8C564B', '#CC79A7', '#5E3C99']
    dcf = [(k, d[k], c) for k, c in zip(dcf_names, dcf_colors)]
    other_cost = d['Taxes / working capital'] + d['WHR auxiliary / heat purchase']
    dcf += [('Other costs', other_cost, '#717B83'), ('CaCO3 revenue', d['CaCO3 revenue'], '#00875A'),
            ('REE revenue', d['REE revenue'], '#A4AD39'), ('WHR heat savings', d['WHR heat savings'], '#56B4E9')]
    other_names = ['HCl input (provisional)', 'Oxalic acid (provisional)', 'Other chemicals / water',
                   'Waste treatment', 'WHR auxiliary electricity']
    other_emissions = math.fsum(l[k] for k in other_names)
    net_ng = l['Direct natural gas combustion'] + l['Industrial WHR avoided emissions']
    lca = [('Natural gas combustion\n(net WHR adjustment)', net_ng, '#D55E00'),
           ('Upstream natural gas', l['Upstream natural gas'], '#7B3294'),
           ('Purchased electricity', l['Purchased electricity'], '#E6AB02'),
           ('NaOH input', l['NaOH input'], '#0072B2'),
           ('Other emissions', other_emissions, '#717B83'),
           ('Biogenic carbon storage', l['Biogenic carbon storage'], '#00875A')]
    check('MSP grouping preserves the sum', math.fsum(v for _, v, _ in dcf), math.fsum(d.values()))
    check('GWP grouping preserves the sum', math.fsum(v for _, v, _ in lca), math.fsum(l.values()))
    check('Host heat contributes no burden', l['WHR host heat burden'], 0)
    return dcf, lca, l


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def cover(book,E):
    f=book.new('ATT advisor meeting figures',kicker='ATT · S3 LAND-BASED INDUSTRIAL WASTE HEAT',
        subtitle='S3 REE On · TEA, LCA, material and energy ledgers of the current model')
    cards=[('Hydrogen MSP',f"${C['stages']['P3']['msp']:.6f}",'per kg H2 · discounted cash flow'),
        ('Net carbon intensity',f"{C['stages']['P3']['gwp']:.6f}",'kg CO2e/kg H2 · existing storage credit'),
        ('External-energy EROI',f"{E['eroi_s3']:.3f}",'H2 LHV / burdened external energy')]
    for i,(name,value,txt) in enumerate(cards):
        x=.047+i*.308
        f.add_artist(Rectangle((x,.656),.29,.155,transform=f.transFigure,facecolor=COL['wash'],edgecolor='none'))
        f.text(x+.015,.775,name,fontsize=11,color=COL['muted'])
        f.text(x+.015,.716,value,fontsize=25,weight='bold')
        f.text(x+.015,.678,txt,fontsize=8.2,color=COL['muted'])
    rows=[['Dry Sargassum presscake',f'{DRY:,.2f} kg/h','Total dry mass, including ash; not DAF'],
        ['H2 component / H2-rich gas',f'{H2:,.5f} / {B["products"]["h2_product_gas_kgph"]:,.5f} kg/h','20 bar; no PSA; only H2 component earns H2 credits'],
        ['H2 yield / annual dry throughput',f'{YIELD:,.5f} kg/t / {ANNUAL_T:,.2f} t/y',f'{HOURS:,.0f} operating h/y'],
        ['Industrial WHR delivered',f'{S["used_average_kW"]:,.2f} kW','Useful LP steam from H1 and H3; upstream heat burden = 0'],
        ['Treatment cost before H2 revenue',f'${ECON["net_treatment_cost_usd_per_year"]/ANNUAL_T:,.2f}/t dry','Existing screening capital convention; not the DCF MSP']]
    table(f,['Quantity','Value','Interpretation'],rows,[.29,.29,.42],top=.606,bottom=.25,fs=9)
    paragraph(f,'Figures 1–3 use S3 REE On. Figure 4 adds CaCO3 commercialization, REE recovery and S3 heat recovery sequentially from a new pessimistic disposal sensitivity. Hydrogen price benchmarks are illustrative plant-gate selling assumptions; no offtake agreement or harmonized market-price set was established.',y=.22,width=143)
    book.save(f)


def energy_figure(book,E):
    demand,supply,factor=energy_page_values(E)
    fig=book.new('Figure 1 · Heat duty and energy supply',
        subtitle='Process-heat accounting plane: useful heat transferred to the process + delivered electrical energy')
    total=math.fsum(v for _,v,_ in demand)
    for i,(fac,unit,title) in enumerate([(factor,'MJ/kg H2 produced','A  Hydrogen basis'),
                                         (1,'MJ/kg dry Sargassum treated','B  Dry-feed basis')]):
        ax=fig.add_axes([.09+i*.465,.425,.375,.365])
        for x,items in enumerate([demand,supply]):
            pos=0
            for name,v,color in items:
                value=v*fac
                ax.bar(x,value,.56,bottom=pos,color=color,edgecolor='white',linewidth=.8,zorder=3)
                if v/total>=.075:
                    rgb=matplotlib.colors.to_rgb(color)
                    lum=.2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2]
                    ax.text(x,pos+value/2,f'{value:.1f}' if i==0 else f'{value:.2f}',fontsize=12,ha='center',va='center',
                            weight='bold',color='white' if lum<.53 else INK)
                pos+=value
            ax.text(x,pos+total*fac*.025,f'{pos:.2f}',fontsize=13,ha='center',weight='bold')
        style(ax,unit)
        ax.set_ylabel(unit,fontsize=11)
        ax.set_xticks([0,1],['Demand S3','Supply S3'],fontsize=12)
        ax.set_xlim(-.6,1.6)
        ax.set_ylim(0,total*fac*1.13)
        ax.tick_params(axis='y',labelsize=11)
        ax.set_title(title,loc='left',fontsize=13,pad=16)
    # One common legend area, two physically distinct columns shared by both panels.
    fig.add_artist(Rectangle((.047,.183),.906,.171,transform=fig.transFigure,facecolor=WASH,edgecolor='none',zorder=0))
    for x,heading,items in [(.062,'DEMAND',demand),(.51,'SUPPLY',supply)]:
        fig.text(x,.331,heading,fontsize=10,weight='bold',color=MUTED)
        for j,(label,_,color) in enumerate(items):
            leg_entry(fig,x,.306-j*.024,label,color)
    note(fig,'S3 supply and demand close on both bases. Other demand includes minor gas/REE process heat and unit, gas-processing, cooling and WHR auxiliary power. H1 + H3 are summed as Waste Heat Recovery at the process-heat plane. Internal HXN is counted once; purchased electricity includes WHR auxiliary power once. Fuel input, utility losses and EROI assumptions remain on the next page. Cooling duty is rejected heat.',
         .05,.157,157,9)
    book.save(fig)


def energy_accounting(book,E):
    f=book.new('Figure 1 · Calculation and EROI assumptions',subtitle='Useful process heat and primary fuel are separate accounting planes; the steam boiler is counted once')
    burner=float(inventory._NG['burner_efficiency']); boiler=float(inventory._LCA['steam_boiler_efficiency'])
    vals=[('Direct-fired NG (U2 + roaster), fuel LHV',E['fuel'],E['fuel'],f'Delivered utility heat / {burner:.2f} burner efficiency'),
        ('Boiler NG, fuel LHV',E['boiler_before'],E['boiler_after'],f'Steam utility heat / {boiler:.2f} boiler efficiency'),
        ('Purchased electricity, delivered',E['electric'],E['electric']+E['aux'],'Unit power + cooling auxiliaries + S3 WHR power'),
        ('EROI denominator: burdened external inputs',E['ext0'],E['ext3'],'Fuel LHV + delivered electricity; zero-burden recovered heat'),
        ('H2 energy output, LHV',E['output'],E['output'],f'{hr.H2_LHV_MJ_PER_KG:.0f} MJ/kg H2; only modeled H2 component'),
        ('Recovered industrial heat, steam utility plane',0,sum(E['whr'].values()),'H1/H3 heat delivered at LP steam boundary'),
        ('Steam utility duty purchased',E['steam_before'],E['steam_after'],'Physical steam; its fuel equivalent is already above'),
        ('Internal HXN, useful process heat',E['hxn'],E['hxn'],'Recovered internally; excluded from external-input denominator')]
    rows=[[n,fmt(v0,4),fmt(v1,4),fmt(v1*DRY/H2,3),txt] for n,v0,v1,txt in vals]
    y=table(f,['Energy item','WHR off\nMJ/kg dry','S3\nMJ/kg dry','S3\nMJ/kg H2','Calculation / boundary'],rows,[.29,.12,.12,.12,.35],top=.818,bottom=.32,fs=8.8)
    steam={r['source']:r['steam_kW'] for r in S['source_details']}
    table(f,['Ratio / source detail','WHR off','S3','Interpretation'],[
        ['External-energy EROI',fmt(E['eroi_before'],4),fmt(E['eroi_s3'],4),'H2 LHV / external fuel LHV + delivered electricity'],
        ['Ratio including physical industrial heat','—',fmt(E['eroi_all_heat'],4),'Denominator additionally counts recovered LP-steam heat; no host fuel allocated'],
        ['H1 / H3 useful steam (kW)','0 / 0',f"{steam['H1']:,.2f} / {steam['H3']:,.2f}",'90% transfer effectiveness; 20 °C approach; D0/EC1 sinks'],
        ['S3 electricity / external heat (kW)','—',f"{(E['electric']+E['aux'])*DRY/3.6:,.2f} / {S['heating_after_average_kW']:,.2f}",
         f"WHR auxiliary power = {S['auxiliary_average_kW']:,.2f} kW (1% of useful steam)"]
    ],[.29,.12,.22,.37],top=y-.032,bottom=.14,fs=8.7)
    paragraph(f,'Electricity is delivered energy (3.6 MJ/kWh), with no primary-energy multiplier. Waste heat has zero energy burden under the current host cut-off. EROI excludes upstream chemical embodied energy, construction energy and feedstock chemical energy; therefore it is an operational external-energy ratio, not a full life-cycle EROI. No defensible feedstock LHV is available in the validated ledger, so no feedstock-inclusive EROI is calculated.',y=.145,width=165,fs=8.1)
    book.save(f)


def contribution_table(fig, items, row_height):
    x, top, width = .475, .805, .478
    fig.add_artist(Rectangle((x, top-.035), width, .035, transform=fig.transFigure, facecolor=INK))
    fig.text(x+.012, top-.0175, 'Contribution', color='white', fontsize=11, weight='bold', va='center')
    fig.text(x+width-.012, top-.0175, 'Value', color='white', fontsize=11, weight='bold', ha='right', va='center')
    y = top-.035
    for i, (label, value, color) in enumerate(items):
        fig.add_artist(Rectangle((x, y-row_height), width, row_height, transform=fig.transFigure,
                                 facecolor=WASH if i%2 == 0 else 'white', edgecolor='none'))
        fig.add_artist(Rectangle((x+.003, y-row_height+.007), .008, row_height-.014, transform=fig.transFigure, facecolor=color))
        fig.text(x+.018, y-row_height/2, label, fontsize=10.8, va='center', linespacing=1.15)
        fig.text(x+width-.012, y-row_height/2, f'{value:+.6f}', fontsize=11, va='center', ha='right')
        y -= row_height
    fig.add_artist(Rectangle((x, y-.039), width, .039, transform=fig.transFigure, facecolor=INK))
    fig.text(x+.012, y-.0195, 'NET (sum of components)', fontsize=11, weight='bold', color='white', va='center')
    fig.text(x+width-.012, y-.0195, f'{math.fsum(v for _, v, _ in items):.6f}', fontsize=11.5,
             weight='bold', color='white', va='center', ha='right')
    return y-.039


def contribution_page(book, items, kind, original_lca=None):
    dcf = kind == 'dcf'
    title = 'Figure 2A · Discounted cash-flow MSP breakdown' if dcf else 'Figure 2B · Carbon intensity breakdown'
    unit = 'USD/kg H2' if dcf else 'kg CO2e/kg H2'
    net = C['stages']['P3']['msp' if dcf else 'gwp']
    fig = book.new(title, subtitle='Positive costs and negative economic credits' if dcf
                   else 'Natural-gas contribution includes the existing WHR adjustment; storage remains a separate credit')
    ax = fig.add_axes([.09, .295, .325, .49])
    pos, neg = stacked(ax, items, negative_hatches=True)
    span = pos-neg
    style(ax, unit)
    ax.set_ylabel(unit, fontsize=12)
    ax.tick_params(axis='both', labelsize=11)
    ax.set_xticks([0], ['S3 REE On'], fontsize=12)
    ax.set_xlim(-.85, .85)
    ax.set_ylim(neg-span*.10, pos+span*.12)
    ax.text(0, pos+span*.035, f'Positive {pos:.3f}', fontsize=11, ha='center')
    ax.text(0, neg-span*.06, f'Credits {neg:.3f}', fontsize=11, ha='center')
    ax.plot([.34, .60], [net, net], color=INK, linewidth=1.1, zorder=5)
    ax.plot(.60, net, 'D', color=INK, markersize=7, zorder=5)
    fig.text(.09, .247, f'◆ Net {net:.6f} {unit}', fontsize=13, weight='bold')
    bottom = contribution_table(fig, items, .035 if dcf else .058)
    if dcf:
        note(fig, 'DCF: 10% IRR; 20 operating years; 21% income tax; MACRS7; 60% debt at 8% for 10 years; working capital = 5% FCI.',
             .475, bottom-.024, 79, 9.2)
        note(fig, f"WHR additions included above: installed capital ${S['incremental_capex_usd']:,.0f}; fixed OPEX ${S['incremental_foc_usd_per_year']:,.0f}/y; auxiliary power ${S['auxiliary_electricity_cost_usd_per_year']:,.0f}/y.",
             .475, bottom-.077, 79, 9.2)
        residual = abs(math.fsum(v for _, v, _ in items)-net)
        note(fig, 'Each operating contribution uses the actual startup profile and discount factors divided by discounted H2 sales. Capital and net financing comprise fixed capital + debt service − loan proceeds; taxes and working capital use their actual DCF columns. WHR capital and fixed costs remain inside their corresponding groups; avoided heat and auxiliary electricity are explicit. Other costs combines taxes / working capital and WHR auxiliary / heat purchase. No annualized-screening residual is presented as DCF capital. The difference between the component sum and the solver MSP is '+f'{residual:.1e} USD/kg H2.',
             .05, .195, 158, 9)
    else:
        l = original_lca
        note(fig, 'Other emissions combines HCl, oxalic acid, other chemicals / water, waste treatment and WHR auxiliary electricity. Values are aggregated before rounding.',
             .475, bottom-.026, 79, 9.5)
        net_ng = l['Direct natural gas combustion'] + l['Industrial WHR avoided emissions']
        note(fig, 'The existing WHR-related natural-gas emissions savings are incorporated once into the displayed natural-gas contribution: '
             f"{l['Direct natural gas combustion']:.6f} − {-l['Industrial WHR avoided emissions']:.6f} = {net_ng:.6f} kg CO2e/kg H2. "
             'This is presentation-only netting of the inherited modeled fuel-related emissions credit, not a recalculated direct-combustion emission factor. Upstream natural gas is unchanged. Storage credits assume permanence for eligible feed-derived cake/char carbon. HCl and oxalic-acid factors are provisional. Landfill emissions, untracked-residue treatment and beach-decomposition benefits remain excluded. Host waste heat has zero assigned burden.',
             .05, .203, 156, 9.2)
    book.save(fig)


def benchmark_assumptions(book):
    f=book.new('Figure 3 · Hydrogen benchmark assumptions',subtitle='Illustrative selling-price and avoided-production sensitivities; no ATT MSP is used as a market price')
    rows=[]
    for b in BENCHMARKS:
        rows.append([b['name']+' H2\n'+b['technology'],f"${b['price']:.2f}/kg",f"{b['ci']:.2f} kg CO2e/kg",b['cost_source'],b['ci_source']])
    table(f,['Reference case','Selling price','GWP factor','Economic basis','LCA basis'],rows,[.21,.11,.13,.27,.28],top=.813,bottom=.56,fs=9)
    paragraph(f,'Price year and geography: all three prices are analyst-selected 2024-USD screening assumptions for a U.S. plant gate. They are informed by production-cost studies, not quoted sales contracts. No price inflation or deflation is applied; the ATT model retains its existing 2020 equipment cost basis and mixed-year operating prices. This is not a harmonized price-year comparison.',y=.537,width=147,fs=9)
    paragraph(f,'Environmental boundary: U.S. well-to-production-gate H2. Gray uses the published 9.3 value excluding plant capital emissions; Blue and Green are rounded Figure 5 values including embodied capital. This small boundary mismatch is retained explicitly rather than claiming a harmonized inventory. Delivery, dispensing and further purification are excluded. ATT gas is 98.89 mol% H2 at 20 bar, with no PSA; full selling-price realization and 1:1 H2 substitution are provisional.',y=.405,width=147,fs=9)
    refs=[('[1] Lewis et al. (NETL), 2022 · Commercial fossil-based H2 production',
        'https://www.hydrogen.energy.gov/docs/hydrogenprogramlibraries/pdfs/review22/fe005_lewis_2022_o-pdf.pdf',
        'U.S. SMR cost context; 2018-dollar cost basis. Gray $1.50 is an illustrative selection, not an extracted NETL result.'),
        ('[2] U.S. DOE · Pathways to Commercial Liftoff: Clean Hydrogen, 2024 Update',
        'https://www.energy.gov/sites/default/files/2025-07/LIFTOFF_DOE_Clean-Hydrogen-2024-Update.pdf',
        '2024 developer-cost context; approximately $2/kg reforming with CCS and $5–7/kg electrolysis before 45V.'),
        ('[3] Elgowainy et al., 2024 · U.S. hydrogen pathways, Argonne R&D GREET',
        'https://doi.org/10.3389/fenrg.2024.1473383',
        'Frontiers in Energy Research 12:1473383, §5 and Fig. 5. CCS performance and renewable technology are pathway-specific.')]
    y=.255
    for title,url,txt in refs:
        f.text(.05,y,title,fontsize=9,color=COL['materials'],url=url,weight='bold')
        f.text(.05,y-.023,txt,fontsize=8.1,color=COL['muted']); y-=.056
    f.text(.05,.086,'Sources checked November 10, 2026. DOE 2024 PDF text was accessible through the search index; its direct URL returned 404.',fontsize=7.5,color=COL['muted'])
    book.save(f)


def treatment_page(book,b,index):
    eco,env=treatment_components(b)
    f=book.new(f"Figure 3{index} · {b['name']} H2 reference case",subtitle=f"S3 REE On · assumed H2 selling price ${b['price']:.2f}/kg · avoided H2 intensity {b['ci']:.2f} kg CO2e/kg")
    for i,(items,ylabel,lim) in enumerate([(eco,'USD/metric tonne dry Sargassum',(-700,390)),
            (env,'kg CO2e/metric tonne dry Sargassum',(-2200,2200))]):
        ax=f.add_axes([.10+i*.47,.37,.37,.42])
        stack(ax,0,items,label_threshold=25 if i==0 else 100,number_fmt='.1f')
        net=sum(v for _,v,_ in items)
        ax.plot(0,net,'D',color=COL['ink'],markersize=7,zorder=5)
        ax.annotate(f'Net {net:,.2f}',(0,net),xytext=(42,0),textcoords='offset points',va='center',weight='bold',fontsize=10)
        ax.set_xlim(-.85,1.2); ax.set_ylim(*lim)
        ax.set_xticks([0],['Treatment economics' if i==0 else 'Avoided-production scenario'])
        style(ax,ylabel)
        ax.set_title('Economic credit' if i==0 else 'Environmental substitution',loc='left',pad=15)
        handles=[Patch(facecolor=c) for _,_,c in items]
        ax.legend(handles,[k for k,_,_ in items],loc='upper left',bbox_to_anchor=(-.08,-.12),fontsize=8.5,frameon=False,ncol=1)
    paragraph(f,f"H2 component yield = {YIELD:.5f} kg per dry tonne. Economic result = ${ECON['net_treatment_cost_usd_per_year']/ANNUAL_T:.2f}/t before H2 revenue − {YIELD:.5f} × ${b['price']:.2f}/kg. Environmental result = {C['stages']['P3']['gwp']*YIELD:.2f} kg CO2e/t existing ATT net GWP − {YIELD:.5f} × {b['ci']:.2f}. This is system expansion through avoided production, not an attributional reallocation; existing storage and utility credits are retained once. Axis limits are identical in all three reference cases.",y=.14,width=150,fs=8.5)
    book.save(f)


def waterfall(ax,values,ylabel):
    x=[0,1.2,2.4,3.6,4.8]
    increments=[values[0],values[1]-values[0],values[2]-values[1],values[3]-values[2],values[3]]
    for i,(xx,v) in enumerate(zip(x,increments)):
        start=0 if i in (0,4) else values[i-1]
        color=COL['ink'] if i in (0,4) else COL['caco3'] if v<0 else COL['bad']
        ax.bar(xx,v,bottom=start,width=.74,color=color,edgecolor='white',zorder=3)
        end=start+v
        if i<4:
            ax.plot([xx+.37,x[i+1]-.37],[end,end],color=COL['muted'],lw=.8,ls='--',zorder=2)
        label=f'{v:.6f}' if i in (0,4) else f'{v:+.6f}'
        ax.annotate(label,(xx,max(start,end)),xytext=(0,8),textcoords='offset points',ha='center',fontsize=9,weight='bold')
        if i in (1,2):
            ax.annotate(f'P{i}: {end:.6f}',(xx,min(start,end)),xytext=(0,-16),textcoords='offset points',ha='center',fontsize=8,color=COL['muted'])
    ax.set_xticks(x,['P0\nPessimistic','P1 change\nCaCO3 + char','P2 change\nREE recovery','P3 change\nIndustrial WHR','P3\nFinal S3'])
    ax.set_ylim(0,max(values)*1.25)
    style(ax,ylabel)


def waterfall_page(book):
    f=book.new('Figure 4 · Sequential MSP and carbon intensity',kicker='LAND-BASED · P0 → P1 → P2 → P3',subtitle='True waterfalls: increments float from the preceding stage; worsening changes are shown in red')
    for i,(key,ylabel) in enumerate([('msp','USD/kg H2'),('gwp','kg CO2e/kg H2')]):
        ax=f.add_axes([.08+i*.47,.42,.40,.36])
        values=[C['stages'][stage][key] for stage in ['P0','P1','P2','P3']]
        waterfall(ax,values,ylabel)
        ax.set_title('4A  Hydrogen MSP' if i==0 else '4B  Carbon intensity',loc='left',pad=16)
        check('Waterfall telescopes '+key,values[0]+sum(values[j]-values[j-1] for j in range(1,4)),values[-1])
    P=C['stages']
    rows=[['P0','Off','Off','No sale; full cakes + char at $0.04/kg',fmt(P['P0']['msp'],6),fmt(P['P0']['gwp'],6)],
        ['P1 = S1 Off','Off','Off','CaCO3 component sold; char $0/kg',fmt(P['P1']['msp'],6),fmt(P['P1']['gwp'],6)],
        ['P2 = S1 On','On','Off','Retain P1 commercialization',fmt(P['P2']['msp'],6),fmt(P['P2']['gwp'],6)],
        ['P3 = S3 On','On','On','Retain P2; add existing S3 WHR',fmt(P['P3']['msp'],6),fmt(P['P3']['gwp'],6)]]
    table(f,['Stage','REE','WHR','Cake / char economics','MSP','GWP'],rows,[.15,.07,.07,.43,.14,.14],top=.307,bottom=.13,fs=8.3)
    p0=P['P0']
    paragraph(f,f"Only P0 adds new disposal assumptions: both full CaCO3 cakes ({p0['cake_disposal_kgph']:,.2f} kg/h) and ATT char ({p0['char_disposal_kgph']:,.2f} kg/h) incur $0.04/kg. P0 cake disposal is ${p0['cake_disposal_usd_per_year']:,.2f}/y and char disposal is ${p0['char_disposal_usd_per_year']:,.2f}/y. No new disposal or carbon credit is assigned to att_residue_untracked. Carbon storage treatment is identical across sale/disposal; P0 → P1 GWP change is zero.",y=.126,width=166,fs=8)
    book.save(f)


# ---------------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--out', type=Path, help='output directory (default: results/s3_figures)')
    args = p.parse_args(argv)
    out = Path(args.out) if args.out else output_dir('s3_figures')
    out.mkdir(parents=True, exist_ok=True)
    pdf_path = out/'ATT_S3_Figures.pdf'
    print('Running the model ...', flush=True)
    _load()
    E = energy()
    dcf, lca, lca_all = contribution_values()
    with PdfPages(pdf_path, metadata={'Title':'ATT S3 figures','Author':'ATT research model',
            'Subject':'S3 REE On; TEA, LCA, heat recovery and treatment sensitivities'}) as pdf:
        book = Book(pdf)
        cover(book, E)
        energy_figure(book, E)
        energy_accounting(book, E)
        contribution_page(book, dcf, 'dcf')
        contribution_page(book, lca, 'lca', original_lca=lca_all)
        benchmark_assumptions(book)
        for b, index in zip(BENCHMARKS, ['A', 'B', 'C']): treatment_page(book, b, index)
        waterfall_page(book)
    results = dict(pdf=str(pdf_path), pages=book.pages, checks=CHECKS, stages=C['stages'], energy=E,
        benchmark_results=[dict(b, cost=sum(v for _, v, _ in treatment_components(b)[0]),
                                gwp=sum(v for _, v, _ in treatment_components(b)[1])) for b in BENCHMARKS])
    (out/'ATT_S3_Figures_data.json').write_text(json.dumps(results, indent=2, default=float), encoding='utf-8')
    print(f'Saved {pdf_path} ({book.page} pages, {len(CHECKS)} checks)')
    return pdf_path


if __name__ == '__main__':
    main()
