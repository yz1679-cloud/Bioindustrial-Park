"""Standalone ATT advisor meeting PDF; no model or HTML report mutations.

Reproduce: repository .venv/Scripts/python.exe <this file>
Refresh controlled scratch runs first with collect_meeting_data.py.
"""
from pathlib import Path
import os
import json
import math
import hashlib
import textwrap
from collections import defaultdict

OUT = Path(__file__).resolve().parent
ATT = OUT.parents[1]
REPO = ATT.parents[1]
os.environ.setdefault('MPLCONFIGDIR', str(ATT/'outputs/runtime_cache/matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle, Patch
import numpy as np

from collect_meeting_data import reference

PDF = OUT/'ATT_Advisor_Meeting_Figures.pdf'
R = reference()
C = json.loads((OUT/'controlled_results.json').read_text(encoding='utf8'))
B = R['details']['True']['base']
S = C['industrial']
A = C['activities']
H2 = S['h2_kg_per_hour']
DRY = 5029.17
HOURS = S['operating_hours_per_year']
YIELD = H2/DRY*1000
ANNUAL_T = DRY*HOURS/1000
U = {r['item']:r['per_kg_dry'] for r in B['utilities']}
ECON = next(r for r in R['ree_tea']['cases'] if r['scenario']=='S3' and r['ree_enabled'])
DCF = [r for r in R['ree_tea']['dcf_components'] if r['scenario']=='S3' and r['ree_enabled']]
LCA = [r for r in R['tables']['lca_breakdown'] if r['scenario']=='S3' and str(r['ree_enabled'])=='True']
TEA = [r for r in R['ree_tea']['ledger'] if r['scenario']=='S3' and r['ree_enabled']]

COL = dict(ink='#233746',muted='#5E6C76',line='#D8E0E5',wash='#F2F5F7',
    materials='#4477AA',heat='#CC7744',electricity='#D3A638',waste='#88949A',
    fixed='#9B83B8',capital='#66558F',tax='#B09BC5',caco3='#228877',ree='#66AA99',
    whr='#66A8C7',storage='#337766',hxn='#A7C7A3',other='#AA6677',bad='#B5524D')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.labelsize':10,
    'axes.titlesize':12,'axes.titleweight':'bold','axes.edgecolor':COL['line'],
    'text.color':COL['ink'],'axes.labelcolor':COL['ink'],'xtick.color':COL['muted'],
    'ytick.color':COL['muted'],'pdf.fonttype':42,'ps.fonttype':42,
    'axes.spines.top':False,'axes.spines.right':False,'axes.spines.left':False,
    'axes.grid':False,'savefig.facecolor':'white','figure.facecolor':'white',
    'text.parse_math':False})

CHECKS = []
def check(name, actual, expected, atol=1e-7, rtol=1e-8):
    ok = math.isclose(float(actual),float(expected),abs_tol=atol,rel_tol=rtol)
    CHECKS.append(dict(check=name,actual=float(actual),expected=float(expected),status='PASS' if ok else 'FAIL'))
    if not ok: raise AssertionError(CHECKS[-1])


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
        f.text(.047,.041,'ATT  |  Advisor meeting · November 12, 2026  |  Reference: November 7 validated working tree',fontsize=7.5,color=COL['muted'])
        f.text(.953,.041,f'{self.page:02d}',fontsize=8,ha='right',color=COL['muted'])
        self.pages.append(title)
        return f
    def save(self,f):
        self.pdf.savefig(f)
        plt.close(f)


def paragraph(fig,text,x=.05,y=.19,width=138,fs=9,color=None):
    fig.text(x,y,wrap(text,width),ha='left',va='top',fontsize=fs,linespacing=1.45,color=color or COL['muted'])


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


def legend(fig,components,y=.18,ncol=3,fs=9):
    seen={}
    for label,_,color in components: seen[label]=color
    fig.legend([Patch(facecolor=c) for c in seen.values()],list(seen),loc='upper center',
        bbox_to_anchor=(.5,y),ncol=ncol,frameon=False,fontsize=fs,columnspacing=1.8,handlelength=1.2)


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
    aux=S['auxiliary_average_kW']*3.6/DRY
    eta=S['steam_agent']['utility_to_process_ratio']
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
    fuel=U['U2 natural gas: fuel input (LHV)']
    boiler=U['LP steam: boiler natural gas (LHV)']
    avoided=S['used_average_kW']*3.6/DRY/.8
    electric=U['Electricity: total']*3.6
    ext0=fuel+boiler+electric
    ext3=fuel+boiler-avoided+electric+aux
    output=120*H2/DRY
    check('S3 external heating kW',S['heating_after_average_kW'],16369.228574839113)
    check('WHR heat source sum',sum(r['steam_kW'] for r in S['source_details']),S['used_average_kW'])
    check('Both energy normalization bases',ext3*DRY/H2,ext3/(H2/DRY))
    return dict(requirements=requirements,supply=supply,supply_s3=supply_s3,aux=aux,hxn=hxn,
        fuel=fuel,boiler_before=boiler,boiler_after=boiler-avoided,electric=electric,
        ext0=ext0,ext3=ext3,eroi_before=output/ext0,eroi_s3=output/ext3,
        eroi_all_heat=output/(ext3+sum(whr.values())),output=output,whr=whr,
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
    check('Discounted MSP component sum',sum(v for _,v,_ in result),C['stages']['P3']['msp'],atol=5e-8)
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


BENCHMARKS=[dict(name='Gray',price=1.5,ci=9.3,technology='Natural gas SMR without CCS',
        cost_source='NETL 2022 [1]; illustrative price, not its exact LCOH',ci_source='Argonne 2024 [3], §5: 9.3, excluding plant CapEx'),
    dict(name='Blue',price=2.,ci=3.5,technology='Natural gas SMR with high-capture CCS',
        cost_source='DOE Liftoff 2024 [2]: approximately $2/kg production cost',ci_source='Argonne 2024 [3], Fig. 5: approximately 3.5, including CapEx'),
    dict(name='Green',price=6.,ci=.6,technology='Wind-powered PEM water electrolysis',
        cost_source='DOE Liftoff 2024 [2]: midpoint of $5–7/kg cost range',ci_source='Argonne 2024 [3], Fig. 5: rounded wind PEM value, including CapEx')]


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


def cover(book,E):
    f=book.new('ATT advisor meeting figures',kicker='RESEARCH MEETING · THURSDAY, NOVEMBER 12, 2026',
        subtitle='S3 REE On · current TEA, LCA, material and energy ledgers · standalone figure set')
    cards=[('Hydrogen MSP',f"${C['stages']['P3']['msp']:.6f}",'per kg H2 · discounted cash flow'),
        ('Net carbon intensity',f"{C['stages']['P3']['gwp']:.6f}",'kg CO2e/kg H2 · existing storage credit'),
        ('External-energy EROI',f"{E['eroi_s3']:.3f}",'H2 LHV / burdened external energy')]
    for i,(name,value,note) in enumerate(cards):
        x=.047+i*.308
        f.add_artist(Rectangle((x,.656),.29,.155,transform=f.transFigure,facecolor=COL['wash'],edgecolor='none'))
        f.text(x+.015,.775,name,fontsize=11,color=COL['muted'])
        f.text(x+.015,.716,value,fontsize=25,weight='bold')
        f.text(x+.015,.678,note,fontsize=8.2,color=COL['muted'])
    rows=[['Dry Sargassum presscake',f'{DRY:,.2f} kg/h','Total dry mass, including ash; not DAF'],
        ['H2 component / H2-rich gas',f'{H2:,.5f} / {B["products"]["h2_product_gas_kgph"]:,.5f} kg/h','20 bar; no PSA; only H2 component earns H2 credits'],
        ['H2 yield / annual dry throughput',f'{YIELD:,.5f} kg/t / {ANNUAL_T:,.2f} t/y',f'{HOURS:,.0f} operating h/y'],
        ['Industrial WHR delivered',f'{S["used_average_kW"]:,.2f} kW','Useful LP steam from H1 and H3; upstream heat burden = 0'],
        ['Treatment cost before H2 revenue',f'${ECON["net_treatment_cost_usd_per_year"]/ANNUAL_T:,.2f}/t dry','Existing screening capital convention; not the DCF MSP'],
        ['Version reconciliation','All recorded source hashes match','Fresh P1–P3 runs reproduce reference values; HTML unchanged']]
    table(f,['Quantity','Verified value','Interpretation'],rows,[.29,.29,.42],top=.606,bottom=.25,fs=9)
    paragraph(f,'Figures 1–3 use S3 REE On. Figure 4 adds CaCO3 commercialization, REE recovery and S3 heat recovery sequentially from a new pessimistic disposal sensitivity. Hydrogen price benchmarks are illustrative plant-gate selling assumptions; no offtake agreement or harmonized market-price set was established.',y=.22,width=143)
    book.save(f)


def energy_figure(book,E):
    f=book.new('Figure 1 · Heat duty and energy supply',subtitle='Process-heat accounting plane: useful heat transferred to the process + delivered electrical energy')
    for i,(factor,label) in enumerate([(DRY/H2,'MJ/kg H2 produced'),(1.,'MJ/kg dry Sargassum treated')]):
        ax=f.add_axes([.085+i*.468,.39,.395,.405])
        req=E['requirements']; req3=req+[('WHR auxiliary power',E['aux'],COL['tax'])]
        sets=[req,E['supply'],req3,E['supply_s3']]
        for x,items in zip([0,1,2.4,3.4],sets):
            pos,_=stack(ax,x,[(k,v*factor,c) for k,v,c in items],width=.69,label_threshold=1.6*factor,number_fmt='.1f')
            ax.text(x,pos+factor*.4,f'{pos:.2f}',ha='center',fontsize=9,weight='bold')
        ax.set_xticks([0,1,2.4,3.4],['Demand\nWHR off','Supply\nWHR off','Demand\nS3','Supply\nS3'])
        ax.set_ylim(0,(sum(v for _,v,_ in req3))*factor*1.16)
        style(ax,label)
        ax.set_title('A  Hydrogen basis' if i==0 else 'B  Dry-feed basis',loc='left',pad=16)
    req=E['requirements']+[('WHR auxiliary power',E['aux'],COL['tax'])]
    supply=E['supply_s3']
    f.text(.06,.308,'DEMAND',fontsize=8.5,weight='bold',color=COL['muted'])
    f.legend([Patch(facecolor=c) for _,_,c in req],[k for k,_,_ in req],loc='upper left',bbox_to_anchor=(.05,.294),ncol=4,fontsize=8.1,frameon=False,columnspacing=1.4)
    f.text(.06,.214,'SUPPLY',fontsize=8.5,weight='bold',color=COL['muted'])
    f.legend([Patch(facecolor=c) for _,_,c in supply],[k for k,_,_ in supply],loc='upper left',bbox_to_anchor=(.05,.200),ncol=4,fontsize=8.1,frameon=False,columnspacing=1.4)
    paragraph(f,'Supply and demand close before and after external WHR. Internal HXN heat is included once as useful process heat; its steam-utility displacement is not added again. Fuel input, utility losses, primary-energy accounting and numerical values are separated on the next page. Cooling duty is rejected heat, not an energy input.',y=.126,fs=8.1,width=162)
    book.save(f)


def energy_accounting(book,E):
    f=book.new('Figure 1 · Calculation and EROI assumptions',subtitle='Useful process heat and primary fuel are separate accounting planes; the steam boiler is counted once')
    vals=[('Direct-fired NG (U2 + roaster), fuel LHV',E['fuel'],E['fuel'],'Delivered utility heat / 0.90 burner efficiency'),
        ('Boiler NG, fuel LHV',E['boiler_before'],E['boiler_after'],'Steam utility heat / 0.80 boiler efficiency'),
        ('Purchased electricity, delivered',E['electric'],E['electric']+E['aux'],'Unit power + cooling auxiliaries + S3 WHR power'),
        ('EROI denominator: burdened external inputs',E['ext0'],E['ext3'],'Fuel LHV + delivered electricity; zero-burden recovered heat'),
        ('H2 energy output, LHV',E['output'],E['output'],'120 MJ/kg H2; only modeled H2 component'),
        ('Recovered industrial heat, steam utility plane',0,sum(E['whr'].values()),'H1/H3 heat delivered at LP steam boundary'),
        ('Steam utility duty purchased',E['steam_before'],E['steam_after'],'Physical steam; its fuel equivalent is already above'),
        ('Internal HXN, useful process heat',E['hxn'],E['hxn'],'Recovered internally; excluded from external-input denominator')]
    rows=[[n,fmt(v0,4),fmt(v1,4),fmt(v1*DRY/H2,3),note] for n,v0,v1,note in vals]
    y=table(f,['Energy item','WHR off\nMJ/kg dry','S3\nMJ/kg dry','S3\nMJ/kg H2','Calculation / boundary'],rows,[.29,.12,.12,.12,.35],top=.818,bottom=.32,fs=8.8)
    table(f,['Ratio / source detail','WHR off','S3','Interpretation'],[
        ['External-energy EROI',fmt(E['eroi_before'],4),fmt(E['eroi_s3'],4),'H2 LHV / external fuel LHV + delivered electricity'],
        ['Ratio including physical industrial heat','—',fmt(E['eroi_all_heat'],4),'Denominator additionally counts recovered LP-steam heat; no host fuel allocated'],
        ['H1 / H3 useful steam (kW)','0 / 0',f"{S['source_details'][1]['steam_kW']:,.2f} / {S['source_details'][0]['steam_kW']:,.2f}",'90% transfer effectiveness; 20 °C approach; D0/EC1 sinks'],
        ['S3 electricity / external heat (kW)','—',f"{(E['electric']+E['aux'])*DRY/3.6:,.2f} / {S['heating_after_average_kW']:,.2f}",'WHR auxiliary power = 125.36 kW (1% of useful steam)']
    ],[.29,.12,.22,.37],top=y-.032,bottom=.14,fs=8.7)
    paragraph(f,'Electricity is delivered energy (3.6 MJ/kWh), with no primary-energy multiplier. Waste heat has zero energy burden under the current host cut-off. EROI excludes upstream chemical embodied energy, construction energy and feedstock chemical energy; therefore it is an operational external-energy ratio, not a full life-cycle EROI. No defensible feedstock LHV is available in the validated ledger, so no feedstock-inclusive EROI is calculated.',y=.145,width=165,fs=8.1)
    book.save(f)


def contribution_page(book,title,items,net,ylabel,notes,kind):
    f=book.new(title,subtitle='Positive expenditures / emissions and negative credits are stacked separately about zero')
    ax=f.add_axes([.10,.30,.31,.48])
    pos,neg=stack(ax,0,items,width=.55,label_threshold=.25 if kind=='dcf' else .7,number_fmt='.2f')
    ax.plot([.28,.40],[net,net],color=COL['ink'],lw=.7,zorder=5)
    ax.plot(.40,net,'D',color=COL['ink'],markersize=6,zorder=5)
    ax.annotate(f'Net {net:.6f}',(.40,net),xytext=(10,0),textcoords='offset points',fontsize=10,weight='bold',va='center')
    ax.text(0,pos+(pos-neg)*.035,f'Positive {pos:.3f}',ha='center',fontsize=9)
    ax.text(0,neg-(pos-neg)*.05,f'Credits {neg:.3f}',ha='center',fontsize=9)
    ax.set_xticks([0],['S3 REE On']); ax.set_xlim(-.8,1.15)
    ax.set_ylim(neg-(pos-neg)*.1,pos+(pos-neg)*.13)
    style(ax,ylabel)
    rows=[[k,fmt(v,6)] for k,v,_ in items]+[['NET (sum of components)',fmt(sum(v for _,v,_ in items),6)]]
    table(f,['Contribution','Value'],rows,[.78,.22],x=.48,total_width=.47,top=.80,bottom=.22,fs=9,
          row_colors=[c for _,_,c in items])
    if kind=='dcf':
        paragraph(f,'DCF: 10% IRR; 20 operating years; 21% income tax; MACRS7; 60% debt at 8% for 10 years; working capital = 5% FCI.',
                  x=.48,y=.285,width=71,fs=8.4)
        paragraph(f,f"WHR additions included above: installed capital ${S['incremental_capex_usd']:,.0f}; fixed OPEX ${S['incremental_foc_usd_per_year']:,.0f}/y; auxiliary power ${S['auxiliary_electricity_cost_usd_per_year']:,.0f}/y.",
                  x=.48,y=.225,width=71,fs=8.4)
    paragraph(f,notes,y=.19,width=148,fs=9)
    book.save(f)


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
    for title,url,note in refs:
        f.text(.05,y,title,fontsize=9,color=COL['materials'],url=url,weight='bold')
        f.text(.05,y-.023,note,fontsize=8.1,color=COL['muted']); y-=.056
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
    rows=[['P0','Off','Off','No sale; full cakes + char at $0.04/kg',fmt(C['stages']['P0']['msp'],6),fmt(C['stages']['P0']['gwp'],6)],
        ['P1 = S1 Off','Off','Off','CaCO3 component sold; char $0/kg',fmt(C['stages']['P1']['msp'],6),fmt(C['stages']['P1']['gwp'],6)],
        ['P2 = S1 On','On','Off','Retain P1 commercialization',fmt(C['stages']['P2']['msp'],6),fmt(C['stages']['P2']['gwp'],6)],
        ['P3 = S3 On','On','On','Retain P2; add existing S3 WHR',fmt(C['stages']['P3']['msp'],6),fmt(C['stages']['P3']['gwp'],6)]]
    y=table(f,['Stage','REE','WHR','Cake / char economics','MSP','GWP'],rows,[.15,.07,.07,.43,.14,.14],top=.307,bottom=.13,fs=8.3)
    paragraph(f,'Only P0 adds new disposal assumptions: both full CaCO3 cakes (8,404.08 kg/h) and ATT char (1,136.96 kg/h) incur $0.04/kg. P0 cake disposal is $2,662,413.67/y and char disposal is $360,188.71/y. No new disposal or carbon credit is assigned to att_residue_untracked. Carbon storage treatment is identical across sale/disposal; P0 → P1 GWP change is zero.',y=.126,width=166,fs=8)
    book.save(f)


def build_ledger(E):
    """Boundary rows use positive cost / negative revenue, and net GWP signs."""
    rows=[]
    f=A['factors']
    s3_boundary={r['stream']:r for r in C['boundary']}
    physical={r['stream']:r for r in B['external'] if r['component']=='TOTAL'}
    wastewater={'excess_condensate','u3_dryer_removed_water','liquor_purge'}
    solid={'salt_cake'}
    cake={r['stream']:r for r in B['caco3_cakes']}
    def add(stream,role,flow,price,cost,gwp,method,note,section):
        rows.append(dict(stream=stream,role=role,flow=flow,price=price,annual_cost_usd=cost,
            cost_usd_per_t=cost/ANNUAL_T,gwp_kg_per_t=gwp/DRY*1000,
            method=method,note=note,section=section))
    for ID,r in physical.items():
        st=s3_boundary[ID]; mass=st['kgph']; cost=0.; gwp=0.; price='0 modeled'; method='0 modeled'; note=''
        sec='Feeds' if r['direction']=='input' else 'Products and wastes'
        role=r['category'].replace('_',' ')
        if r['direction']=='input':
            cost=mass*st['price']*HOURS; price=f"${st['price']:.6g}/kg"
            gwp=mass*st['CF']; method=f"{st['CF']:.6g} kg/kg"
            if ID=='att_sargassum_feed': note='Waste feed cut-off; collection/transport excluded; dry fraction 0.237.'
            elif ID in ('lime','scrubber_lime'): note='Wet carbide-lime paste; 55.2 wt% Ca(OH)2; waste cut-off; handling/transport unmodeled.'
            elif ID=='fresh_hcl': note='31 wt% solution; provisional Norwegian EPD proxy, expired Aug. 2026.'
            elif ID=='fresh_oxalic_acid': note='Anhydrous-acid activity; provisional Spanish factor; form uncertain.'
            elif ID=='leachate_naoh': method='Not modeled / excluded'; note='Cost modeled at $0.405/kg; existing LCA has no CF for this stream (omission retained).'
            elif ID=='leach_water': method='Not modeled; zero flow'; note='No LCA CF on REE makeup water; current flow is zero.'
            elif 'air' in ID: price='0 modeled'; method='0 modeled'; note='Ambient air; no upstream burden.'
            elif 'backup_fuel' in ID: note='Inactive placeholder, zero flow; utility gas is listed separately.'
            elif 'water' in ID: method='0.46 kg/m3'; note='Zero fresh flow; internal condensate/recycle supplies process.'
            else: note='Modeled purchased reagent; factors on component/solution basis as stated.'
        elif ID in cake:
            cr=cake[ID]
            # Parent carries physical flow and storage only. Sale/disposal
            # subaccounts below carry economics, so every quantity is counted once.
            gwp=A['storage_kgCO2ph'][ID]
            price='See split below'; method='Stored eligible C × −44.0095'; note='Physical cake parent; cost/revenue booked in subaccounts; assumed permanent storage.'
        elif ID=='h2_product':
            role='H2-rich gas product'; price='No baseline H2 sale'; method='All process GWP on H2'; note=f'H2 component {H2:.5f} kg/h; gas {mass:.5f} kg/h. Figure 3 assigns scenario revenue separately.'
        elif ID=='ree_product':
            cost=-st['price']*mass*HOURS; price='$35/kg REO'; method='No separate LCA credit'; note=f"{st['components'].get('REO',0):.5f} kg/h REO in {mass:.3f} kg/h product; 1.31 wt% grade; saleability provisional."
        elif ID in wastewater:
            price='$0.004/kg disposal'; cost=.004*mass*HOURS; gwp=mass/1000*f['wastewater_treatment']; method='0.38 kg/m3'; note='WWT operating-energy proxy; process CH4/N2O not modeled.'
            if ID=='liquor_purge': note+=' H2SO4 neutralization is a separate activity below.'
        elif ID=='att_char':
            price='$0/kg'; gwp=A['storage_kgCO2ph'][ID]; method='Stored eligible C × −44.0095'; note='Zero modeled disposal fee; permanent storage assumed. Distinct from untracked organics.'
        elif ID=='att_residue_untracked':
            method='Excluded from LCA'; note='Zero baseline cost; physical fate and treatment emissions unknown; no storage credit.'
        elif ID in solid:
            cost=.04*mass*HOURS; price='$0.04/kg disposal'; method='0 (landfill excluded)'; note='No landfill emissions under current boundary; not a measured zero-emission treatment.'
        elif ID=='leach_co2': method='0 biogenic CO2'; note='Biogenic release excluded under existing convention; storage credited only in retained solids.'
        elif ID=='roaster_exhaust': method='Not modeled / excluded'; note='Biogenic CO2 excluded; fossil oxalate-derived direct CO2 not separately modeled; omission retained.'
        elif 'exhaust' in ID: method='0 modeled'; note='Air/water-vapor exhaust; no incremental modeled GHG factor.'
        else: note='Zero-flow emission placeholder; no added cost or emissions.'
        add(ID,role,f'{mass:,.3f} kg/h',price,cost,gwp,method,note,sec)
        if ID in cake:
            cr=cake[ID]
            add(ID+' · CaCO3 sale','Component revenue',f"{cr['sold_caco3_kgph']:,.3f} kg/h",'$100/t CaCO3',-cr['revenue_usd_ph']*HOURS,0.,'Storage on cake parent',
                'Accounting component of parent cake; not another physical output. Full modeled CaCO3 sold; buyer unverified.',sec)
            add(ID+' · non-saleable','Disposal subaccount',f"{cr['disposed_kgph']:,.3f} kg/h",'$0.04/kg',cr['disposal_usd_ph']*HOURS,0.,'0 (landfill excluded)',
                'Accounting remainder includes moisture/impurities; not another physical output.',sec)
    for ID,st in s3_boundary.items():
        if ID not in physical:
            assert ID=='u3_tail_gas' and st['kgph']==0 and st['price']==0 and st['CF']==0
            add(ID,'Inactive PSA placeholder','0.000 kg/h','$0/kg',0.,0.,'0; inactive / excluded',
                'PSA is disabled. The empty inlet placeholder is omitted from the reference physical boundary; listed here for completeness.',
                'Feeds')
    acid=A['h2so4_kgph']
    add('Purge neutralization H2SO4','Off-flowsheet reagent',f'{acid:,.3f} kg/h','$0.0948/kg',acid*.0948*HOURS,acid*f['H2SO4'],'0.04447 kg/kg',
        'Aggregate alkalinity calculation; internal F2 wash recycle is not separately discharged/neutralized.','Utilities and adjustments')
    # Preserve the model decomposition: base steam utility plus explicit S3
    # avoidance adjustment. Do not apply another factor to post-WHR steam.
    by_item=lambda name:sum(r['USD_per_yr'] for r in TEA if r['item']==name)
    lc=lambda name:sum(r['kgCO2e_per_kg_H2'] for r in LCA if r['contributor']==name)*H2
    fuel_MJph=E['fuel']*DRY
    gas_cost=by_item('Utility: natural_gas')+by_item('Natural gas: price fuel = duty / 0.90 (adjustment to BioSTEAM agent cost)')
    add('Direct-fired natural gas','Fuel LHV (U2 + RO1)',f'{fuel_MJph/3.6:,.2f} kW',f'${gas_cost/HOURS/fuel_MJph:.6f}/MJ',gas_cost,
        lc('Natural gas U2: combustion')+lc('Natural gas U2: upstream supply'),'0.056 + 0.0098 kg/MJ',
        'Existing U2 LCA label also includes roaster firing. Duty / 90% efficiency; not gas-agent mass.','Utilities and adjustments')
    add('LP steam · inherited utility account','S1 steam before S3',f"{S['baseline_steam_kW']:,.2f} kW",f"${by_item('Utility: low_pressure_steam')/HOURS/S['baseline_steam_kW']:.6f}/kWh heat",
        by_item('Utility: low_pressure_steam'),lc('Natural gas boiler (LP steam): combustion')+lc('Natural gas boiler (LP steam): upstream supply'),
        '(0.056 + 0.0098)/0.80 kg/MJ',f"S3 remaining steam = {S['remaining_steam_average_kW']:,.2f} kW; subtract explicit WHR adjustment below. Boiler fuel is not costed again.",'Utilities and adjustments')
    add('Electricity · process units','Purchased electricity',f"{A['power_kW']:,.2f} kWh/h",f"${A['power_price']:.4f}/kWh",by_item('Electricity: modeled units'),lc('Electricity: process units'),'0.449 kg/kWh',
        'Modeled compressor, dryers, filters, leach/roaster and other unit power.','Utilities and adjustments')
    cw=U['Cooling water: circulation']*DRY
    add('Cooling water · circulation','Utility account',f'{cw:,.2f} kg/h',f"${by_item('Utility: cooling_water')/HOURS/cw:.7f}/kg",by_item('Utility: cooling_water'),lc('Electricity: cooling tower and CW pumps'),
        f"{U['Electricity: cooling tower and CW pumps (estimate)']*DRY:.2f} kWh/h × 0.449",
        'Cooling auxiliaries included in CW price and CW LCA; do not add their electricity a second time.','Utilities and adjustments')
    add('Industrial WHR · recovered steam','H1 + H3 physical supply',f"{S['used_average_kW']:,.2f} kW",'$0/MWh',0,0,'0 kg/MWh host heat',
        'Zero host burden/cost cut-off; installed WHR capital and auxiliary power appear separately.','Utilities and adjustments')
    add('Industrial WHR · avoided utility','Aggregate adjustment',f"{S['avoided_boiler_fuel_average_kW']:,.2f} kW fuel avoided",'Avoided steam cost',-S['avoided_cost_usd_per_year'],-S['avoided_emissions_kg_per_hour'],
        'Avoided NG: steam / 0.80',
        'Subtract once from inherited steam cost/emissions; physical heat supply above has zero assigned burden.','Utilities and adjustments')
    add('Industrial WHR · auxiliary power','Purchased electricity',f"{S['auxiliary_average_kW']:,.2f} kWh/h",f"${A['power_price']:.4f}/kWh",S['auxiliary_electricity_cost_usd_per_year'],S['auxiliary_emissions_kg_per_hour'],'0.449 kg/kWh',
        '1% of useful recovered steam; additional to process and CW auxiliaries.','Utilities and adjustments')
    add('Fixed operating cost','Aggregate operating cost','4% of S3 FCI / year','Existing TEA',ECON['fixed_usd_per_year'],0,'No separate modeled LCA',
        'Includes incremental WHR fixed cost; capital embodied GWP is outside current LCA.','Utilities and adjustments')
    add('Annualized capital','Screening capital cost',f"CRF {ECON['capital_recovery_factor']:.8f}",'FCI × CRF',ECON['screening_capital_usd_per_year'],0,'No separate modeled LCA',
        f"S3 FCI ${ECON['FCI_usd']:,.2f}; includes WHR installed allowance ${S['incremental_capex_usd']:,.2f}. Not added to DCF MSP components.",'Utilities and adjustments')
    # Every external physical stream is represented, including zero-flow rows.
    assert set(physical)<=set(r['stream'] for r in rows)
    check('Complete ledger treatment cost',sum(r['annual_cost_usd'] for r in rows),ECON['net_treatment_cost_usd_per_year'],atol=.01)
    check('Complete ledger GWP',sum(r['gwp_kg_per_t'] for r in rows),C['stages']['P3']['gwp']*YIELD)
    return rows


def ledger_pages(book,rows):
    for section in ['Feeds','Products and wastes','Utilities and adjustments']:
        selected=[r for r in rows if r['section']==section]
        # Eight entries/page leaves generous room for unambiguous boundary notes.
        for start in range(0,len(selected),8):
            chunk=selected[start:start+8]
            f=book.new('Supporting stream ledger · '+section.lower(),subtitle=f"S3 REE On · entries {start+1}–{start+len(chunk)} of {len(selected)} · cost (+), sales revenue (−), GWP credits (−)")
            values=[]
            for r in chunk:
                values.append([r['stream']+'\n'+r['role'],r['flow'],r['price'],fmt(r['annual_cost_usd']/1000,3),
                    fmt(r['cost_usd_per_t'],3),r['method'],fmt(r['gwp_kg_per_t'],3)])
            end=table(f,['Stream / role','Flow','Price / fee','kUSD/y','USD/t dry','GWP factor / method','kg CO2e/t dry'],values,
                [.22,.15,.14,.10,.09,.19,.11],top=.816,bottom=.37,fs=8.2)
            y=min(.355,end-.028)
            for j,r in enumerate(chunk):
                text=r['stream']+': '+r['note']
                txt=wrap(text,151)
                f.text(.05,y,txt,fontsize=8.1,va='top',linespacing=1.35,color=COL['muted'])
                y-=(txt.count('\n')+1)*8.1*1.35/612+.009
            if y<.075: raise ValueError('Ledger notes overflow '+section+str(start))
            book.save(f)


def reconciliation_page(book,rows,E):
    f=book.new('Supporting ledger · reconciliation and boundaries',subtitle='All totals below use S3 REE On; baseline treatment accounting excludes H2 selling revenue')
    gross=ECON['gross_opex_usd_per_year']; cap=ECON['screening_capital_usd_per_year']
    caco=-ECON['caco3_revenue_usd_per_year']; reo=-ECON['reo_revenue_usd_per_year']
    gpos=sum(r['gwp_kg_per_t'] for r in rows if r['gwp_kg_per_t']>0)
    gneg=sum(r['gwp_kg_per_t'] for r in rows if r['gwp_kg_per_t']<0)
    econrows=[[label,fmt(v/1000,3),fmt(v/ANNUAL_T,3)] for label,v in [
        ('Gross operating costs, net of WHR utility savings',gross),('Annualized screening capital',cap),
        ('CaCO3 sales credit',caco),('REE sales credit',reo),('Net treatment cost, before H2 revenue',gross+cap+caco+reo)]]
    y=table(f,['Economic reconciliation','kUSD/year','USD/t dry'],econrows,[.65,.18,.17],top=.81,bottom=.55,fs=9)
    gwprows=[['Positive modeled GWP',fmt(gpos,4),fmt(gpos/YIELD,6)],
        ['Existing storage + WHR utility credits',fmt(gneg,4),fmt(gneg/YIELD,6)],
        ['Net ATT GWP, before H2 displacement',fmt(gpos+gneg,4),fmt((gpos+gneg)/YIELD,6)]]
    y=table(f,['Environmental reconciliation','kg CO2e/t dry','kg CO2e/kg H2'],gwprows,[.65,.18,.17],top=y-.04,bottom=.36,fs=9)
    notes=[
        'Zero modeled: free waste feed/lime, zero-fee ATT char, ambient air and zero-flow utility placeholders. A zero modeled cost does not establish a zero real-world treatment burden.',
        'Not modeled / unknown: product purification and marketability, untracked-organic fate, collection/transport, certain reagent and direct waste emissions. The REE leach NaOH stream is costed but has no CF in the existing LCA; roaster oxalate-derived direct CO2 is not separately counted.',
        'Excluded by current boundary: landfill activity emissions (factor zero), beach-decomposition counterfactual, plant/WHR capital embodied GWP, host-system heat burden. Stored eligible biogenic carbon is credited under assumed permanence for sold cakes and ATT char.',
        'Internal flows: recycled NaOH, condensate and F2 wash liquor are not charged as fresh purchases or extra boundary wastes. CaCO3 component/remainder entries are bookkeeping splits of physical parent cakes. Steam and its boiler fuel are never counted twice.',
        'S3 uncertainty: H1/H3 availability and independence are unverified; H3 800→40 °C follows the existing literature interpretation despite a conflicting table. WHR allowance $500/kW, 20 °C approach, 90% transfer effectiveness and 1% auxiliary power remain screening inputs.'
    ]
    ypos=y-.035
    for note in notes:
        txt=wrap(note,157)
        f.text(.05,ypos,txt,fontsize=8.3,va='top',linespacing=1.35,color=COL['muted'])
        ypos-=(txt.count('\n')+1)*8.3*1.35/612+.014
    if ypos<.075: raise ValueError('Reconciliation notes overflow')
    book.save(f)


def validate(E,ledger):
    check('S3 MSP vs user reference',C['stages']['P3']['msp'],1.496439,atol=.0000005)
    check('S3 GWP vs user reference',C['stages']['P3']['gwp'],7.355818,atol=.0000005)
    check('H2 component vs reference',H2,372.92463,atol=.000005)
    check('Dry feed vs reference',DRY,5029.17)
    wet_feed=next(r for r in C['boundary'] if r['stream']=='att_sargassum_feed')
    check('Total dry mass includes ash',DRY,wet_feed['kgph']-wet_feed['components']['Water'])
    assert wet_feed['components']['Ash']>0
    check('WHR vs reference kW',S['used_average_kW'],12536.38,atol=.005)
    check('Treatment cost vs reference',ECON['net_treatment_cost_usd_per_year']/ANNUAL_T,104.56,atol=.005)
    for stage,scenario,ree in [('P1','S1',False),('P2','S1',True),('P3','S3',True)]:
        r=next(x for x in R['tables']['scenario_comparison'] if x['scenario']==scenario and x['ree_enabled']==ree)
        check(stage+' MSP reference',C['stages'][stage]['msp'],r['hydrogen_msp_usd_per_kg'])
        check(stage+' GWP reference',C['stages'][stage]['gwp'],r['net_gwp_kg_co2e']/r['hydrogen_kg'])
    check('P0 GWP unchanged from P1',C['stages']['P0']['gwp'],C['stages']['P1']['gwp'])
    check('P0 full cake fee',C['stages']['P0']['cake_disposal_usd_per_year'],8404.083542266439*.04*HOURS)
    check('P0 char fee',C['stages']['P0']['char_disposal_usd_per_year'],1136.9593256279366*.04*HOURS)
    check('P0 untracked residue price unchanged',C['stages']['P0']['untracked_price'],0)
    off=next(r for r in R['ree_tea']['cases'] if r['scenario']=='S1' and not r['ree_enabled'])
    off_products=R['details']['False']['base']['products']
    expected_delta=(off['caco3_revenue_usd_per_year']+off_products['caco3_component_kgph']*.04*HOURS+
                    C['stages']['P0']['char_disposal_usd_per_year'])/(H2*HOURS)
    check('P0 adds only lost cake sales and new disposal',C['stages']['P0']['delta_msp_from_P1'],expected_delta,atol=5e-8)
    check('Cost ledger before capital/coproducts',sum(r['annual_cost_usd'] for r in ledger if r['stream']!='Annualized capital')+
        ECON['coproduct_revenue_usd_per_year'],ECON['gross_opex_usd_per_year'],atol=.01)
    for k,v in C['provenance']['input_sha256'].items():
        assert hashlib.sha256((REPO/k).read_bytes()).hexdigest()==v,k
    report=Path(C['provenance']['reference'])/'ATT_S1_S2_S3_Comprehensive_Report.html'
    assert hashlib.sha256(report.read_bytes()).hexdigest()==C['provenance']['reference_html_sha256']


def main():
    E=energy(); dcf=dcf_groups(); lca=lca_groups(); ledger=build_ledger(E)
    validate(E,ledger)
    with PdfPages(PDF,metadata={'Title':'ATT Advisor Meeting Figures — November 12, 2026',
            'Author':'ATT research model','Subject':'S3 REE On; TEA, LCA, heat recovery, treatment sensitivities and stream ledger'}) as pdf:
        book=Book(pdf)
        cover(book,E)
        energy_figure(book,E)
        energy_accounting(book,E)
        contribution_page(book,'Figure 2A · Discounted cash-flow MSP breakdown',dcf,C['stages']['P3']['msp'],'USD/kg H2',
            'Each operating contribution uses the actual startup profile and discount factors divided by discounted H2 sales. Capital and net financing comprise fixed capital + debt service − loan proceeds; taxes and working capital use their actual DCF columns. WHR capital and fixed costs remain inside their corresponding groups; avoided heat and auxiliary electricity are explicit. No annualized-screening residual is presented as DCF capital. Sum differs from the solver by only 2.02 × 10⁻8 USD/kg H2.', 'dcf')
        contribution_page(book,'Figure 2B · Carbon intensity breakdown',lca,C['stages']['P3']['gwp'],'kg CO2e/kg H2',
            'Inherited fuel emissions precede the separately displayed S3 avoided-boiler adjustment. Natural gas includes combustion and upstream supply, using the current LHV efficiencies once. Storage credits assume permanence for eligible feed-derived cake/char carbon. HCl and oxalic-acid factors are provisional. Landfill emissions, untracked-residue treatment and beach-decomposition benefits remain excluded. The host waste heat has zero assigned burden.', 'lca')
        benchmark_assumptions(book)
        for b,index in zip(BENCHMARKS,['A','B','C']): treatment_page(book,b,index)
        waterfall_page(book)
        ledger_pages(book,ledger)
        reconciliation_page(book,ledger,E)
    results=dict(pdf=str(PDF),pages=book.pages,validation=CHECKS,energy=E,
        benchmarks=BENCHMARKS,benchmark_results=[dict(b,cost=sum(v for _,v,_ in treatment_components(b)[0]),
            gwp=sum(v for _,v,_ in treatment_components(b)[1])) for b in BENCHMARKS],ledger=ledger,
        stages=C['stages'],source_protection=C['provenance'])
    (OUT/'figure_data_and_validation.json').write_text(json.dumps(results,indent=2),encoding='utf8')
    print(json.dumps(dict(pdf=str(PDF),pages=book.page,checks=len(CHECKS),eroi_s3=E['eroi_s3'],
        benchmarks=results['benchmark_results']),indent=2))


if __name__=='__main__': main()
