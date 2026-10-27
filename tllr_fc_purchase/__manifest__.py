# -*- coding: utf-8 -*-
{
    "name": "Taller - Integración con Compras",
    "summary": """
        Puente entre el Módulo Taller y Compras: compra directa de repuestos, servicios
        tercerizados, reserva al recibir y ajuste por facturas de proveedor tardías""",
    "description": """
        Módulo puente del Módulo Taller (tllr_fc). Se instala solo cuando están
        instalados el Taller y Compras; el ajuste «Integración con Compras» lo activa
        o desactiva.

        - Compra directa de repuestos desde la OT (una compra, una OT).
        - Al recibir la mercadería, el repuesto queda reservado a la OT y el sobrante libre.
        - Servicios tercerizados: la orden de compra del servicio y su costo real en la OT.
        - Facturas de proveedor tardías: ajuste de costo automático en la OT ya terminada.

        El núcleo (tllr_fc) no depende de este módulo.
    """,
    "author": "FC_Py",
    "website": "http://www.www.com.py",
    "category": "Servicios/Taller",
    "version": "2026.19.029",
    "license": "LGPL-3",
    "application": False,
    "installable": True,
    "auto_install": False,
    "depends": ["tllr_fc", "purchase", "purchase_stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
        "views/product_template_views.xml",
        "views/purchase_order_views.xml",
        "views/tllr_fc_ot_views.xml",
        "wizard/tllr_fc_wizard_compra_directa_views.xml",
        "views/menus.xml",
    ],
}
