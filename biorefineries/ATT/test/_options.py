"""Test helper: the CaCO3-sales option of ATT S1.

The baseline of ATT S1 disposes the CaCO3 cakes (tea.yaml caco3_sales.enabled: false) and credits all landfilled
carbon, including the residue (att_lca.yaml carbonate_storage_accounting: inherited, credit_char_carbon: true). The
sales accounting and the conservative carbon accounting remain available as an option; the tests of that option run
inside ``sales_option()``.
"""
import contextlib

from biorefineries.ATT.analyses import lca
from biorefineries.ATT.analyses import tea as tea_mod


@contextlib.contextmanager
def sales_option(conservative=True):
    """CaCO3 sales on (tea.yaml caco3_sales) and, if ``conservative``, the conservative carbon accounting."""
    sales, storage = tea_mod._T["caco3_sales"], lca._LCA["carbon_storage"]
    old = (sales["enabled"], storage["carbonate_storage_accounting"], storage["credit_char_carbon"])
    sales["enabled"] = True
    if conservative:
        storage["carbonate_storage_accounting"], storage["credit_char_carbon"] = "conservative", False
    try:
        yield
    finally:
        sales["enabled"], storage["carbonate_storage_accounting"], storage["credit_char_carbon"] = old
