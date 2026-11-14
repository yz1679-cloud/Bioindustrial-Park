"""Report-only revision: saved values in; vector PDF and rendered previews out.

Run with ../../.venv/Scripts/python.exe from biorefineries/ATT.
Never imports BioSTEAM or evaluates TEA/LCA; existing helpers only aggregate
already saved component values. Original files are read only.
"""
from pathlib import Path
import hashlib
import json
import math
import sys
import textwrap

OUT = Path(__file__).resolve().parent
ATT = OUT.parents[1]
SOURCE = OUT / 'ATT_Advisor_Meeting_Figures.pdf'
DEST = OUT / 'ATT_Advisor_Meeting_Figures_Revised_10p.pdf'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protected_files():
    # Include local pre-existing user edits; compare to this session, not HEAD.
    paths = [p for p in ATT.rglob('*') if p.is_file()
             and not {'outputs', '__pycache__', '.pytest_cache'}.intersection(p.relative_to(ATT).parts)]
    paths += [p for p in OUT.iterdir() if p.is_file()
              and p.name in {'ATT_Advisor_Meeting_Figures.pdf', 'controlled_results.json',
                             'figure_data_and_validation.json', 'generate_figures.py',
                             'collect_meeting_data.py', 'verify_pdf.py'}]
    return {str(p): sha(p) for p in paths}


BEFORE = protected_files()

import pymupdf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle

# The existing module's main() is guarded; import reads saved JSON/HTML only.
import generate_figures as original

DATA = json.loads((OUT / 'figure_data_and_validation.json').read_text(encoding='utf-8'))
INK, MUTED, LINE, WASH = '#233746', '#5E6C76', '#D8E0E5', '#F2F5F7'
CHECKS = []


def check(name, condition, **details):
    CHECKS.append(dict(check=name, status='PASS' if condition else 'FAIL', **details))
    if not condition:
        raise AssertionError(CHECKS[-1])


def close(name, actual, expected, atol=1e-12):
    check(name, math.isclose(actual, expected, rel_tol=0, abs_tol=atol),
          actual=actual, expected=expected, tolerance=atol)


def note(fig, text, x, y, width, fs=9.5):
    fig.text(x, y, '\n'.join(textwrap.wrap(text, width, break_long_words=False)),
             fontsize=fs, va='top', color=MUTED, linespacing=1.35)


def new_page(book, number, title, subtitle):
    book.page = number - 1
    return book.new(title, subtitle=subtitle)


def leg_entry(fig, x, y, label, color, fs=10.6):
    fig.add_artist(Rectangle((x, y-.006), .014, .016, transform=fig.transFigure,
                             facecolor=color, edgecolor='none'))
    fig.text(x+.022, y+.001, label, fontsize=fs, va='center')


def stacked(ax, items, factor=1, negative_hatches=False):
    pos = neg = 0.0
    span = sum(abs(v * factor) for _, v, _ in items)
    for i, (name, value, color) in enumerate(items):
        v = value * factor
        bottom = pos if v >= 0 else neg
        hatch = ('///', '\\\\', 'xx')[i % 3] if v < 0 and negative_hatches else None
        ax.bar(0, v, .66, bottom=bottom, color=color, edgecolor='white',
               linewidth=.8, hatch=hatch, zorder=3)
        # Keep interior labels only if the segment has room at final page size.
        if abs(v) / span >= .065:
            rgb = matplotlib.colors.to_rgb(color)
            lum = .2126*rgb[0] + .7152*rgb[1] + .0722*rgb[2]
            ax.text(0, bottom+v/2, f'{v:.1f}' if factor != 1 else f'{v:.2f}',
                    ha='center', va='center', fontsize=11.5,
                    color='white' if lum < .53 else INK, weight='bold')
        if v >= 0:
            pos += v
        else:
            neg += v
    return pos, neg


def energy_values():
    e = DATA['energy']
    req = {k: v for k, v, _ in e['requirements']}
    supply = {k: v for k, v, _ in e['supply_s3']}
    major = ['Drying D0/D2/D3', 'ATT reactor U2', 'NaOH evaporation EC1', 'Causticization C1']
    demand = [(k, req[k], c) for k, c in zip(major, ['#0072B2', '#D55E00', '#7B3294', '#E6AB02'])]
    minor = {k: v for k, v in req.items() if k not in major}
    minor['WHR auxiliary power'] = e['aux']
    demand.append(('Other demand (heat + electricity)', math.fsum(minor.values()), '#717B83'))
    whr = supply['H1 recovered heat to process'] + supply['H3 recovered heat to process']
    delivered = [
        ('Fired heat to process', supply['Fired heat to process'], '#D55E00'),
        ('Boiler steam to process', supply['Boiler steam to process'], '#CC79A7'),
        ('Internal HXN heat', supply['Internal HXN heat'], '#0072B2'),
        ('Waste Heat Recovery', whr, '#009E73'),
        ('Purchased electricity (incl. WHR auxiliary)', supply['Purchased electricity'] + supply['WHR auxiliary power'], '#E6AB02'),
    ]
    close('H1 + H3 aggregated before rounding', whr, math.fsum(v for k, v in supply.items() if k.startswith(('H1 ', 'H3 '))))
    close('Other demand preserves minor components', demand[-1][1], math.fsum(minor.values()))
    close('Demand grouping preserves S3', math.fsum(v for _, v, _ in demand), math.fsum(req.values()) + e['aux'])
    close('Supply grouping preserves S3', math.fsum(v for _, v, _ in delivered), math.fsum(supply.values()))
    factor = original.DRY / original.H2
    for name, items in [('demand', demand), ('supply', delivered)]:
        total = math.fsum(v for _, v, _ in items)
        close(f'{name} dry-feed total', total, 27.45, .005)
        close(f'{name} hydrogen total', total*factor, 370.13, .005)
    return demand, delivered, factor, minor


def energy_page(book, demand, supply, factor):
    fig = new_page(book, 2, 'Figure 1 · Heat duty and energy supply',
                   'Process-heat accounting plane: useful heat transferred to the process + delivered electrical energy')
    total = math.fsum(v for _, v, _ in demand)
    for i, (fac, unit, title) in enumerate([
        (factor, 'MJ/kg H2 produced', 'A  Hydrogen basis'),
        (1, 'MJ/kg dry Sargassum treated', 'B  Dry-feed basis')]):
        ax = fig.add_axes([.09+i*.465, .425, .375, .365])
        for x, items in enumerate([demand, supply]):
            # Translate the single-bar helper to each of the two positions.
            pos = 0
            for name, v, color in items:
                value = v*fac
                ax.bar(x, value, .56, bottom=pos, color=color, edgecolor='white', linewidth=.8, zorder=3)
                if v/total >= .075:
                    rgb = matplotlib.colors.to_rgb(color)
                    lum = .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2]
                    ax.text(x, pos+value/2, f'{value:.1f}' if i == 0 else f'{value:.2f}',
                            fontsize=12, ha='center', va='center', weight='bold',
                            color='white' if lum < .53 else INK)
                pos += value
            ax.text(x, pos+total*fac*.025, f'{pos:.2f}', fontsize=13, ha='center', weight='bold')
        original.style(ax, unit)
        ax.set_ylabel(unit, fontsize=11)
        ax.set_xticks([0, 1], ['Demand S3', 'Supply S3'], fontsize=12)
        ax.set_xlim(-.6, 1.6)
        ax.set_ylim(0, total*fac*1.13)
        ax.tick_params(axis='y', labelsize=11)
        ax.set_title(title, loc='left', fontsize=13, pad=16)
    # One common legend area, two physically distinct columns shared by both panels.
    fig.add_artist(Rectangle((.047, .183), .906, .171, transform=fig.transFigure,
                             facecolor=WASH, edgecolor='none', zorder=0))
    for x, heading, items in [(.062, 'DEMAND', demand), (.51, 'SUPPLY', supply)]:
        fig.text(x, .331, heading, fontsize=10, weight='bold', color=MUTED)
        for j, (label, _, color) in enumerate(items):
            leg_entry(fig, x, .306-j*.024, label, color)
    note(fig, 'S3 supply and demand close on both bases. Other demand includes minor gas/REE process heat and unit, gas-processing, cooling and WHR auxiliary power. H1 + H3 are summed as Waste Heat Recovery at the process-heat plane. Internal HXN is counted once; purchased electricity includes WHR auxiliary power once. Fuel input, utility losses and EROI assumptions remain on the next page. Cooling duty is rejected heat.',
         .05, .157, 157, 9)
    book.save(fig)


def contribution_values():
    d = {k: v for k, v, _ in original.dcf_groups()}
    l = {k: v for k, v, _ in original.lca_groups()}
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
    close('Other costs from full-precision components', other_cost, .084495, .0000005)
    close('Other emissions from full-precision components', other_emissions, .205426, .0000005)
    close('Net natural gas displayed contribution', net_ng, 8.565449, .0000005)
    close('MSP grouping preserves original sum', math.fsum(v for _, v, _ in dcf), math.fsum(d.values()))
    close('MSP unchanged within original solver residual', math.fsum(v for _, v, _ in dcf), DATA['stages']['P3']['msp'], 5e-8)
    close('Net MSP at requested display precision', DATA['stages']['P3']['msp'], 1.496439, .0000005)
    close('GWP grouping and once-only WHR adjustment', math.fsum(v for _, v, _ in lca), math.fsum(l.values()))
    close('GWP unchanged', math.fsum(v for _, v, _ in lca), DATA['stages']['P3']['gwp'])
    close('Net GWP at requested display precision', math.fsum(v for _, v, _ in lca), 7.355818, .0000005)
    close('Upstream natural gas untouched', lca[1][1], l['Upstream natural gas'])
    close('Storage credit untouched', lca[-1][1], l['Biogenic carbon storage'])
    close('Zero host heat contribution retained in boundary', l['WHR host heat burden'], 0)
    return dcf, lca, {'original_dcf': d, 'original_lca': l, 'other_emissions_members': other_names}


def contribution_table(fig, items, net, unit, row_height):
    x, top, width = .475, .805, .478
    fig.add_artist(Rectangle((x, top-.035), width, .035, transform=fig.transFigure, facecolor=INK))
    fig.text(x+.012, top-.0175, 'Contribution', color='white', fontsize=11, weight='bold', va='center')
    fig.text(x+width-.012, top-.0175, 'Value', color='white', fontsize=11, weight='bold', ha='right', va='center')
    y = top-.035
    for i, (label, value, color) in enumerate(items):
        fig.add_artist(Rectangle((x, y-row_height), width, row_height, transform=fig.transFigure,
                                 facecolor=WASH if i%2 == 0 else 'white', edgecolor='none'))
        fig.add_artist(Rectangle((x+.003, y-row_height+.007), .008, row_height-.014,
                                 transform=fig.transFigure, facecolor=color))
        fig.text(x+.018, y-row_height/2, label, fontsize=10.8, va='center', linespacing=1.15)
        fig.text(x+width-.012, y-row_height/2, f'{value:+.6f}', fontsize=11,
                 va='center', ha='right')
        y -= row_height
    fig.add_artist(Rectangle((x, y-.039), width, .039, transform=fig.transFigure, facecolor=INK))
    fig.text(x+.012, y-.0195, 'NET (sum of components)', fontsize=11, weight='bold', color='white', va='center')
    fig.text(x+width-.012, y-.0195, f'{math.fsum(v for _, v, _ in items):.6f}', fontsize=11.5,
             weight='bold', color='white', va='center', ha='right')
    return y-.039


def contribution_page(book, items, kind):
    dcf = kind == 'dcf'
    number = 4 if dcf else 5
    title = 'Figure 2A · Discounted cash-flow MSP breakdown' if dcf else 'Figure 2B · Carbon intensity breakdown'
    unit = 'USD/kg H2' if dcf else 'kg CO2e/kg H2'
    net = DATA['stages']['P3']['msp' if dcf else 'gwp']
    fig = new_page(book, number, title,
                   'Positive costs and negative economic credits' if dcf else 'Natural-gas contribution includes the existing WHR adjustment; storage remains a separate credit')
    ax = fig.add_axes([.09, .295, .325, .49])
    pos, neg = stacked(ax, items, negative_hatches=True)
    span = pos-neg
    original.style(ax, unit)
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
    bottom = contribution_table(fig, items, net, unit, .035 if dcf else .058)
    if dcf:
        note(fig, 'DCF: 10% IRR; 20 operating years; 21% income tax; MACRS7; 60% debt at 8% for 10 years; working capital = 5% FCI.',
             .475, bottom-.024, 79, 9.2)
        note(fig, f"WHR additions included above: installed capital ${original.S['incremental_capex_usd']:,.0f}; fixed OPEX ${original.S['incremental_foc_usd_per_year']:,.0f}/y; auxiliary power ${original.S['auxiliary_electricity_cost_usd_per_year']:,.0f}/y.",
             .475, bottom-.077, 79, 9.2)
        notes = ('Each operating contribution uses the actual startup profile and discount factors divided by discounted H2 sales. Capital and net financing comprise fixed capital + debt service − loan proceeds; taxes and working capital use their actual DCF columns. WHR capital and fixed costs remain inside their corresponding groups; avoided heat and auxiliary electricity are explicit. Other costs combines taxes / working capital and WHR auxiliary / heat purchase. No annualized-screening residual is presented as DCF capital. The original rounding-level solver/component difference is retained (less than 2.1 × 10⁻8 USD/kg H2).')
        note(fig, notes, .05, .195, 158, 9)
    else:
        note(fig, 'Other emissions combines HCl, oxalic acid, other chemicals / water, waste treatment and WHR auxiliary electricity. Values are aggregated before rounding.',
             .475, bottom-.026, 79, 9.5)
        notes = ('The existing WHR-related natural-gas emissions savings are incorporated once into the displayed natural-gas contribution: 18.519266 − 9.953817 = 8.565449 kg CO2e/kg H2. This is presentation-only netting of the inherited modeled fuel-related emissions credit, not a recalculated direct-combustion emission factor. Upstream natural gas is unchanged. Storage credits assume permanence for eligible feed-derived cake/char carbon. HCl and oxalic-acid factors are provisional. Landfill emissions, untracked-residue treatment and beach-decomposition benefits remain excluded. Host waste heat has zero assigned burden.')
        note(fig, notes, .05, .203, 156, 9.2)
    book.save(fig)


def verify_pdf():
    original_doc = pymupdf.open(SOURCE)
    doc = pymupdf.open(DEST)
    check('Exactly ten pages', len(doc) == 10, pages=len(doc))
    retained = [1, 3, 6, 7, 8, 9, 10]
    for number in retained:
        a, b = original_doc[number-1], doc[number-1]
        close(f'Page {number} width', b.rect.width, a.rect.width)
        close(f'Page {number} height', b.rect.height, a.rect.height)
        check(f'Page {number} original content stream unchanged', b.read_contents() == a.read_contents())
        check(f'Page {number} text unchanged', b.get_text() == a.get_text())
        check(f'Page {number} pixels unchanged at 144 dpi',
              b.get_pixmap(matrix=pymupdf.Matrix(2, 2)).samples == a.get_pixmap(matrix=pymupdf.Matrix(2, 2)).samples)
    for number in [2, 4, 5]:
        page = doc[number-1]
        check(f'Page {number} original dimensions', page.rect == original_doc[number-1].rect)
        spans = [s for b in page.get_text('dict')['blocks'] if 'lines' in b
                 for line in b['lines'] for s in line['spans']]
        outside = [s['text'] for s in spans if not page.rect.contains(pymupdf.Rect(s['bbox']))]
        check(f'Page {number} text inside page', not outside, outside=outside)
        intrusion = [s['text'] for s in spans if s['bbox'][1] < .929*612 and s['bbox'][3] > .931*612]
        check(f'Page {number} no footer intrusion', not intrusion, intrusion=intrusion)
        check(f'Page {number} no review annotations', not list(page.annots() or []))
        preview = OUT / f'ATT_Advisor_Meeting_Figures_Revised_Page_{number:02}.png'
        page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).save(preview)
    p2, p5 = doc[1].get_text(), doc[4].get_text()
    check('Page 2 has S3 bars only', p2.count('Demand S3') == 2 and p2.count('Supply S3') == 2 and 'WHR off' not in p2)
    check('Page 2 consolidated WHR legend', 'Waste Heat Recovery' in p2 and 'H1 recovered heat to process' not in p2)
    check('Page 5 no standalone avoided-emissions category', 'Industrial WHR avoided emissions' not in p5)
    check('Page 5 net natural gas and unchanged net visible', '8.565449' in p5 and '7.355818' in p5)
    after = protected_files()
    check('No protected files changed, including pre-existing user edits', BEFORE == after,
          protected_file_count=len(BEFORE))
    check('No BioSTEAM import or model execution', 'biosteam' not in sys.modules)
    doc.close()
    original_doc.close()


def main():
    demand, supply, factor, minor = energy_values()
    dcf, lca, components = contribution_values()
    replacement = OUT / 'ATT_Revised_Replacement_Pages.pdf'
    with PdfPages(replacement) as pdf:
        book = original.Book(pdf)
        energy_page(book, demand, supply, factor)
        contribution_page(book, dcf, 'dcf')
        contribution_page(book, lca, 'lca')
    with pymupdf.open(SOURCE) as source, pymupdf.open(replacement) as revised:
        result = pymupdf.open()
        for i in range(10):
            if i in {1: 0, 3: 1, 4: 2}:
                j = {1: 0, 3: 1, 4: 2}[i]
                result.insert_pdf(revised, from_page=j, to_page=j)
            else:
                result.insert_pdf(source, from_page=i, to_page=i)
        result.set_metadata(dict(title='ATT Advisor Meeting Figures — Revised 10-page report',
                                 author='ATT research model', subject='Report-only visualization revision; saved validated results'))
        result.save(DEST, garbage=4, deflate=True)
        result.close()
    verify_pdf()
    report = dict(status='PASS', pdf=str(DEST), pages=10, checks=CHECKS,
                  energy=dict(demand=demand, supply=supply, hydrogen_factor=factor, other_demand_components=minor),
                  dcf=dcf, lca=lca, aggregation_sources=components,
                  msp=DATA['stages']['P3']['msp'], gwp=DATA['stages']['P3']['gwp'],
                  msp_component_sum=math.fsum(v for _, v, _ in dcf),
                  gwp_component_sum=math.fsum(v for _, v, _ in lca),
                  protected_file_sha256=BEFORE, pdf_sha256=sha(DEST))
    (OUT/'revision_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(dict(status='PASS', pdf=str(DEST), pages=10, checks=len(CHECKS),
                         msp=report['msp'], gwp=report['gwp']), indent=2))


if __name__ == '__main__':
    main()
