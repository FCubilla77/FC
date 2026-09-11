# -*- coding: utf-8 -*-
{
    "name": "Paraguay - Contabilidad",
    "version": "19.0.2026.0011",
    "category": "Accounting/Localizations/Account Charts",
    "license": "LGPL-3",
    "author": "FC_Py",
    "summary": "Paquete de Localización Fiscal Paraguay: plan de cuentas, grupos, "
               "impuestos, posiciones fiscales, plazos de pago, permisos "
               "contables y valores de compañía por defecto (account.chart.template)",
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
        "data/account_account_tag_data.xml",
        "data/account_groups_data.xml",
    ],
    "installable": True,
    "auto_install": False,
}
