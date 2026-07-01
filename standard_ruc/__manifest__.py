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
    "author": "www",
    "website": "http://www.www.com.py",
    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/odoo/addons/base/module/module_data.xml
    # for the full list
    "category": "Local",
    "version": "20260101.1",
    "license": "LGPL-3",
    # any module necessary for this one to work correctly
    "depends": ["base"],
    # always loaded
    "data": [
        "data/data.xml",
        "views/views.xml",
    ],
    "catalogo_tipo": "H",
    "catalogo_superior": "Local_",
}
