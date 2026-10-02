# -*- coding: utf-8 -*-
{
    "name": "Paraguay - Contabilidad",
    "version": "19.0.2026.0014",
    "category": "Accounting/Localizations/Account Charts",
    "license": "LGPL-3",
    "author": "FC_Py",
    "summary": "Paquete de Localización Fiscal Paraguay: plan de cuentas, grupos, "
               "impuestos, posiciones fiscales, plazos de pago, permisos "
               "contables, diario de banco de ejemplo, valores de compañía "
               "por defecto (account.chart.template), Balance General x "
               "Grupos de Cuentas y Cierre/Apertura de Ejercicio",
    "description": """
        Localización Fiscal / Paquete: Paraguay
        =========================================
        Este módulo implementa el mecanismo nativo de Odoo de Paquete de
        Localización Fiscal (account.chart.template) para Paraguay. Ver
        static/description/index.html para el detalle completo y la guía
        de configuración posterior a la instalación.

        Todo lo que no corresponde al paquete nativo de Localización Fiscal
        (validaciones de RUT, Timbrado/Nro. Documento, Tipo Fiscal, reportes
        Libro Ventas/Compras, etc.) se mantiene en el módulo local_py.
    """,
    "depends": ["base", "account"],
    "data": [
        "security/ir.model.access.csv",
        "data/account_account_tag_data.xml",
        "data/account_groups_data.xml",
        "data/account_group_menu_data.xml",
        "report/report_balance_general.xml",
        "views/balance_general_views.xml",
        "views/cierre_ejercicio_views.xml",
    ],
    "installable": True,
    "auto_install": False,
}
