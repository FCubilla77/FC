# -*- coding: utf-8 -*-
{
    "name": "Paraguay - Contabilidad",
    "version": "19.0.2026.0007",
    "category": "Accounting/Localizations/Account Charts",
    "license": "LGPL-3",
    "author": "FC_Py",
    "summary": "Paquete de Localización Fiscal Paraguay: plan de cuentas, grupos, "
               "impuestos y valores de compañía por defecto (account.chart.template)",
    "description": """
        Localización Fiscal / Paquete: Paraguay
        =========================================
        Este módulo implementa el mecanismo nativo de Odoo de Paquete de
        Localización Fiscal (account.chart.template) para Paraguay:

        - Plan de cuentas: 215 cuentas imputables (account.account)
        - 135 grupos de cuenta (account.group), incluyendo las 7 raíces de
          nivel 1 (Activo, Pasivo, Patrimonio Neto, Ingresos, Costos,
          Otros Ingresos, Gastos)
        - 6 impuestos (account.tax): IVA 10%, IVA 5% y Exentas, para
          Ventas y Compras, con sus líneas de reparto
        - 3 grupos de impuestos (account.tax.group)
        - Valores de compañía por defecto: cuentas por cobrar/pagar,
          moneda PYG, prefijos de cuentas de banco y caja, cuenta de
          transferencias internas, cuenta de diferencia de cambio y
          cuenta de redondeo
        - 2 posiciones fiscales (account.fiscal.position): Exterior y
          Diplomático, de selección manual (no automáticas, sin
          restricción de país), que reemplazan IVA 10%/5% Ventas por
          Exentas Ventas
        - 2 tags de cuenta (account.account.tag): IVA Crédito Fiscal e
          IVA Débito Fiscal
        - 6 plazos de pago (account.payment.term): Contado, 15/30/45/60
          días, y 30-60-90 días (3 cuotas)

        Todo lo que no corresponde al paquete nativo de Localización Fiscal
        (validaciones de RUT, Timbrado/Nro. Documento, Tipo Fiscal, reportes
        Libro Ventas/Compras, etc.) se mantiene en el módulo local_py.
    """,
    "depends": ["base", "account"],
    "data": [
        "data/account_account_tag_data.xml",
    ],
    "installable": True,
    "auto_install": False,
}
