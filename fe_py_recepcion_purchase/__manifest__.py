# -*- coding: utf-8 -*-
{
    "name": "FE_Py Recepción de Facturas - Compras",
    "summary": """
        Vincula las facturas electrónicas recibidas con las cotizaciones
        (órdenes de compra) de Compras""",
    "description": """
        Módulo puente de fe_py_recepcion: se instala solo cuando están
        instalados fe_py_recepcion y Compras.

        Permite asignar una cotización a la recepción y una línea de la
        cotización a cada línea del XML. Al confirmar, la factura de
        proveedor queda vinculada con la cotización como si se hubiera
        cargado a mano desde Odoo: la factura toma el precio y la cantidad
        del XML, y las líneas sin vincular se permiten.

        Se activa o desactiva con la opción "Vincular con cotizaciones" de
        la configuración de recepción. No modifica fe_py_recepcion ni
        local_py: todo es por herencia.
    """,
    "author": "FC_Py",
    "website": "http://www.www.com.py",
    "category": "Localización",
    "version": "2026.19.001",
    "license": "LGPL-3",
    "application": False,
    "installable": True,
    "auto_install": True,
    "depends": ["fe_py_recepcion", "purchase"],
    "data": [
        "views/fe_py_recepcion_configuracion_views.xml",
        "views/fe_py_recepcion_documento_views.xml",
    ],
}
