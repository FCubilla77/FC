# -*- coding: utf-8 -*-
{
    "name": "Control RUT",
    "summary": """
        Ajustes en formularios y reportes asignando el nombre RUT,
         en algunos casos es un dato requerido...!!!""",
    "description": """
        Ajustes en formularios y reportes asignando el nombre RUT,
         en algunos casos es un dato requerido...!!!
    """,
    "author": ": F_C_",
    "website": "http://www.www.com.py",
    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/odoo/addons/base/module/module_data.xml
    # for the full list
    "category": "Localización",
    "version": "20260201.1",
    "license": "LGPL-3",
    # any module necessary for this one to work correctly
    "depends": ["base"],
    # always loaded
    "data": [
        "data/data.xml",
        "views/views.xml",
    ],
    "catalogo_tipo": "H",
    "catalogo_superior": "localizacion",
}
