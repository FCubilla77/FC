# -*- coding: utf-8 -*-
{
    "name": "Taller - Integración con Ventas",
    "summary": """
        Puente entre el Módulo Taller y Ventas: presupuesto previo, pedido y factura
        generada desde el pedido de venta""",
    "description": """
        Módulo puente del Módulo Taller (tllr_fc). Se instala solo cuando están instalados el Taller y Ventas; el ajuste «Integración con Ventas» lo activa o desactiva.

        - Presupuesto previo elegido en la recepción (el cliente pidió presupuesto).
        - La OT de cliente no inicia sin el presupuesto confirmado (excepción del supervisor).
        - Al cerrar para facturar se crea o actualiza UN solo presupuesto/pedido de la OT,
          se confirma y se factura desde el pedido, con historial en el chatter.
        - Datos del vehículo en la impresión del presupuesto.
        - Ajuste «Integración con Ventas» en Taller › Configuración › Ajustes.

        El núcleo (tllr_fc) no depende de este módulo.
    """,
    "author": "FC_Py",
    "website": "http://www.www.com.py",
    "category": "Servicios/Taller",
    "version": "2026.19.027",
    "license": "LGPL-3",
    "application": False,
    "installable": True,
    "auto_install": False,
    "depends": ["tllr_fc", "sale", "sale_stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
        "views/sale_order_views.xml",
        "views/tllr_fc_recepcion_views.xml",
        "views/tllr_fc_ot_views.xml",
        "views/sale_report.xml",
        "wizard/tllr_fc_sale_wizard_vencido_views.xml",
    ],
}
