# -*- coding: utf-8 -*-
{
    "name": "Standard RUC",
    "summary": """
        Cambia las traducciones de los formularios y reportes y les asigna el nombre RUC,
         en algunos casos los pone como requeridos""",
    "description": """
        Cambia las traducciones de los formularios y reportes y les asigna el nombre RUC,
         en algunos casos los pone como requeridos
    """,
    "author": "Interfaces S.A.",
    "website": "http://www.interfaces.com.py",
    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/odoo/addons/base/module/module_data.xml
    # for the full list
    "category": "Localizaciones",
    "version": "20240506.1",
    "license": "LGPL-3",
    # any module necessary for this one to work correctly
    "depends": ["base"],
    # always loaded
    "data": [
        "data/data.xml",
        "views/views.xml",
    ],
    "catalogo_tipo_entrada": "Hijo",
    "catalogo_padre": "loc_fiscal_itf_v01",
}
