# -*- coding: utf-8 -*-
{
    "name": "Local_Py",
    "summary": """
        Localización para Paraguay: validación de RUC/RUT, y campos
        Timbrado y Nro. Documento en diarios contables y facturas""",
    "description": """
        Localización para Paraguay: validación de RUC/RUT, y campos
        Timbrado y Nro. Documento en diarios contables y facturas
    """,
    "author": ": F_C_",
    "website": "http://www.www.com.py",
    "category": "Localización",
    "version": "20260707.1",
    "license": "LGPL-3",
    "depends": ["base", "account"],
    "data": [
        "data/data.xml",
        "views/res_partner_views.xml",
        "views/account_journal_views.xml",
        "views/account_move_views.xml",
    ],
    "catalogo_tipo": "H",
    "catalogo_superior": "localizacion",
}
