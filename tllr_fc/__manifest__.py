# -*- coding: utf-8 -*-
{
    "name": "Taller",
    "summary": """
        Gestión de taller mecánico: recepción de vehículos, órdenes de trabajo,
        repuestos, horas de personal, control de calidad, facturación y entrega""",
    "description": """
        Módulo vertical de gestión de taller mecánico para Odoo 19.

        Registra los trabajos realizados a vehículos, con los repuestos, insumos,
        herramientas y horas de personal consumidos por cada Orden de Trabajo,
        con trazabilidad desde la recepción hasta la entrega, incluyendo
        presupuesto, facturación, costos y rentabilidad.

        Módulo núcleo (tllr_fc). Las integraciones con Ventas y Compras se
        incorporan mediante módulos puente opcionales. No depende de hr,
        l10n_py, local_py ni loc_fiscal_itf.
    """,
    "author": "FC_Py",
    "website": "http://www.www.com.py",
    "category": "Servicios/Taller",
    "version": "2026.19.023",
    "license": "LGPL-3",
    "application": True,
    "installable": True,
    "depends": [
        "base",
        "mail",
        "contacts",
        "product",
        "stock",
        "stock_account",
        "account",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "security/ir_rule.xml",
        "data/tllr_fc_item_data.xml",
        "data/tllr_fc_funcion_data.xml",
        "data/tllr_fc_motivo_data.xml",
        "data/mail_template_data.xml",
        "views/report_paperformat.xml",
        "views/report_layout.xml",
        "views/tllr_fc_marca_views.xml",
        "views/tllr_fc_vehiculo_views.xml",
        "views/tllr_fc_funcion_views.xml",
        "views/tllr_fc_personal_views.xml",
        "views/tllr_fc_puesto_views.xml",
        "views/product_template_views.xml",
        "views/res_partner_views.xml",
        "views/tllr_fc_turno_views.xml",
        "views/tllr_fc_recepcion_views.xml",
        "views/tllr_fc_recepcion_report.xml",
        "views/tllr_fc_reportes.xml",
        "views/tllr_fc_ajuste_costo_views.xml",
        "views/tllr_fc_ot_views.xml",
        "views/tllr_fc_control_calidad_views.xml",
        "views/tllr_fc_entrega_views.xml",
        "views/tllr_fc_wizard_views.xml",
        "views/res_config_settings_views.xml",
        "views/account_stock_views.xml",
        "views/tllr_fc_reportes_gestion.xml",
        "views/tllr_fc_reportes_nuevos.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "tllr_fc/static/src/scss/tablero.scss",
            "tllr_fc/static/src/views/turno_calendar/turno_calendar.js",
            "tllr_fc/static/src/views/turno_calendar/turno_calendar.xml",
            "tllr_fc/static/src/views/rentabilidad_list/rentabilidad_list.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "catalogo_tipo": "P",
    "catalogo_superior": "",
}
