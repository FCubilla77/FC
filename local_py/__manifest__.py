# -*- coding: utf-8 -*-
{
    "name": "Local_Py",
    "summary": """
        Localización para Paraguay: validación de RUT, campos Timbrado y
        Nro. Documento en diarios y facturas, Tipo Fiscal, Libro Ventas y Libro Compras,
        permisos contables automáticos y configuración de precios con impuestos incluidos""",
    "description": """
        Localización para Paraguay: validación de RUT, campos Timbrado y
        Nro. Documento en diarios y facturas, Tipo Fiscal, Libro Ventas y Libro Compras,
        permisos contables automáticos para productos, categorías, clientes y proveedores,
        y configuración de "Impuestos incluidos" en precios.

        El plan de cuentas, grupos de cuenta, impuestos predeterminados, moneda de
        compañía y país fiscal pasaron al módulo l10n_py (paquete nativo de
        Localización Fiscal Paraguay). Este módulo se encarga de todo lo que ese
        paquete no cubre.
    """,
    "author": "FC_Py",
    "website": "http://www.www.com.py",
    "category": "Localización",
    "version": "2026.018",
    "license": "LGPL-3",
    "depends": ["base", "account"],
    "data": [
        "security/ir.model.access.csv",
        "data/data.xml",
        "data/account_groups_data.xml",
        "data/local_py_tipo_fiscal_data.xml",
        "views/res_partner_views.xml",
        "views/local_py_tipo_fiscal_views.xml",
        "views/account_journal_views.xml",
        "views/account_move_views.xml",
        "views/libro_ventas_wizard_views.xml",
        "views/libro_compras_wizard_views.xml",
        "views/config_paraguay_wizard_views.xml",
        "views/local_py_plan_cuentas_report_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "catalogo_tipo": "H",
    "catalogo_superior": "localizacion",
}
