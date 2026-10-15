"""
ATT (alkaline thermal treatment) analyses.

Submodules are imported explicitly (nothing is imported here, so that
systems/_att_system.py and units/_att.py can use the process-level helpers
without loading the reporting stack):

Process-level helpers (called by the model itself)
    mass_energy      energy accounting; F2 cake wash balance (W2)
    thermodynamics   U2 gas basis/reaction energy; C1 aqueous enthalpy reference
    heat_integration heat-recovery screening, pinch targets, HXR network design

Experimental data (laboratory scale, kept separate from the plant model)
    experiment       UCLA dataset, conversions, workbook verification, lab screening LCA

Full-scale analyses (frozen BioSTEAM model)
    inventory        material/energy inventory, LCI, cost inputs
    tea              minimum H2 selling price (SaBReTEA)
    lca              GWP100 (BioSTEAM impact framework)
    scenarios        gas-yield scenario TEA/LCA comparison

Reporting
    reporting        consolidated results; master documentation package
    final            final results (experimental, screening LCA, plant, comparisons)

Diagnostics (read-only audits)
    validation       1 kg/h mass/energy audit; sodium ledger

Output locations
    paths            default result folders under att_outputs/ (repository root)
"""
