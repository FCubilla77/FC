# -*- coding: utf-8 -*-
{
    "name": "FE_Py Recepción de Facturas",
    "summary": """
        Recepción de facturas electrónicas de proveedores: lee el XML del
        Documento Electrónico, lo carga en una cabecera y un detalle para
        verificar, asignar productos y generar la factura de proveedor""",
    "description": """
        Recepción de facturas electrónicas (SIFEN) de proveedores.

        El XML llega por correo o lo carga el usuario. Cada archivo crea una
        recepción (cabecera y detalle) y el proceso automático la lleva hasta
        la factura, nota de crédito o nota de débito de proveedor: en borrador
        o, si la compañía y el proveedor lo permiten y se cumplen los
        criterios, publicada. Lo que no se puede resolver solo queda para que
        el usuario lo revise.

        El XML lo emite y firma el proveedor: este módulo solo lo LEE y
        guarda sus datos (incluido el CDC, que carga en los campos de
        local_py >= 2026.19.017). No genera ni valida CDC, firma digital ni
        esquema, y no consulta a SIFEN.

        Es independiente de FE_Py (emisión) y no modifica archivos de
        local_py: toda extensión sobre sus modelos es por herencia. La
        vinculación con cotizaciones (Compras) está en el módulo puente
        fe_py_recepcion_purchase, que se instala solo si Compras está
        instalado.

        Licencia OPL-1: requiere un código de licencia emitido por FC_Py
        para la base de datos (Ajustes > Configuración FE_Py Recepción).
    """,
    "author": "FC_Py",
    "website": "http://www.www.com.py",
    "category": "Localización",
    "version": "2026.19.011",
    "license": "OPL-1",
    "application": False,
    "installable": True,
    "depends": ["account", "local_py"],
    "external_dependencies": {
        "python": ["lxml", "cryptography"],
    },
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "wizard/fe_py_recepcion_cargar_wizard_views.xml",
        "views/fe_py_recepcion_equivalencia_views.xml",
        "views/fe_py_recepcion_documento_views.xml",
        "views/account_move_views.xml",
        "views/res_partner_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "pre_init_hook": "pre_init_hook",
    "post_init_hook": "post_init_hook",
}
