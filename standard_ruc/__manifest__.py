# -*- coding: utf-8 -*-
{
    "name": "Standard RUC",
    "summary": """
        Cambia los formularios y reportes asignando el nombre RUT,
         en algunos casos es un dato requerido""",
    "description": """
        Cambia los formularios y reportes asignando el nombre RUT,
         en algunos casos es un dato requerido
    """,
    "author": ": FC_",
    "website": "http://www.www.com.py",
    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/odoo/addons/base/module/module_data.xml
    # for the full list
    "category": "Local",
    "version": "20260101.2",
    "license": "LGPL-3",
    # any module necessary for this one to work correctly
    "depends": ["base"],
    # always loaded
    "data": [
        "data/data.xml",
        "views/views.xml",
    ],
    "catalogo_tipo": "H",
    "catalogo_superior": "local",
}
