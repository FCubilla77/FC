# -*- coding: utf-8 -*-
{
    "name": "Local_Py",
    "summary": """
        Localización para Paraguay: validación de RUT, campos Timbrado y
        Nro. Documento en diarios y facturas, Tipo Fiscal, Libro Ventas y Libro Compras""",
    "description": """
        Localización para Paraguay: validación de RUT, campos Timbrado y
        Nro. Documento en diarios y facturas, Tipo Fiscal, Libro Ventas y Libro Compras
    """,
    "author": "FC_Py",
    "website": "http://www.www.com.py",
    "category": "Localización",
    "version": "2026.010",
    "license": "LGPL-3",
    "depends": ["base", "account"],
    "data": [
        "security/ir.model.access.csv",
        "data/data.xml",
        "data/account_tax_group_data.xml",
        "data/res_currency_data.xml",
        "data/l10n_py_tipo_fiscal_data.xml",
        "views/res_partner_views.xml",
        "views/l10n_py_tipo_fiscal_views.xml",
        "views/account_journal_views.xml",
        "views/account_move_views.xml",
        "views/libro_ventas_wizard_views.xml",
        "views/libro_compras_wizard_views.xml",
        "views/config_paraguay_wizard_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "catalogo_tipo": "H",
    "catalogo_superior": "localizacion",
}
