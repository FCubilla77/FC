# -*- coding: utf-8 -*-
{
    "name": "Taller",
    "summary": """
        Gestión de taller mecánico: recepción de vehículos, órdenes de trabajo,
        repuestos, horas de personal, control de calidad, facturación y entrega""",
    "description": """
        Módulo vertical de gestión de taller mecánico para Odoo 19.

        Registra los trabajos realizados a vehículos, con los repuestos, insumos,
        herramientas y horas de personal consumidos por cada Orden de Trabajo,
        con trazabilidad desde la recepción hasta la entrega, incluyendo
        presupuesto, facturación, costos y rentabilidad.

        Es un único módulo (tllr_fc) que se desarrolla por fases. No depende de
        l10n_py, local_py ni loc_fiscal_itf.
    """,
    "author": "FC_Py",
    "website": "http://www.www.com.py",
    "category": "Servicios/Taller",
    "version": "2026.19.002",
    "license": "LGPL-3",
    "application": True,
    "installable": True,
    "depends": [
        "base",
        "mail",
        "contacts",
        "product",
        "stock",
        "stock_account",
        "purchase",
        "purchase_stock",
        "account",
        "sale",
        "hr",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "security/ir_rule.xml",
        "views/report_paperformat.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "post_init_hook": "post_init_hook",
    "catalogo_tipo": "P",
    "catalogo_superior": "",
}
