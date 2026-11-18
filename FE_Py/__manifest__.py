# -*- coding: utf-8 -*-
{
    "name": "FE_Py",
    "summary": """
        Facturación Electrónica Paraguay (SIFEN): generación de CDC, firma
        electrónica, envío y consulta de Documentos Electrónicos, eventos
        (Cancelación/Inutilización), KuDE y registro de operaciones""",
    "description": """
        Integración con el Sistema Integrado de Facturación Electrónica
        Nacional (SIFEN) de la DNIT — Paraguay.

        Cubre, sobre Factura de Cliente, Nota de Crédito de Cliente y Nota
        de Débito de Cliente: generación del CDC y del XML del Documento
        Electrónico, firma electrónica (certificado propio del
        contribuyente), envío y consulta por el Web Service Sincrónico de
        SIFEN, eventos de Cancelación e Inutilización, generación del KuDE
        (representación gráfica con código QR) y registro completo del
        historial de operaciones (envíos, respuestas y estados), tanto por
        comprobante como en una ventana unificada de log.

        Este módulo es autosuficiente: no depende de ninguna localización.
        Los códigos de SIFEN los define en sus propios catálogos, y los
        datos fiscales que administra otro módulo (timbrado, numeración y
        vigencia del timbrado) los toma del campo que se le indique en el
        Mapeo de Datos, sea cual sea el módulo que los provea.

        Numera los Diarios que emiten Documentos Electrónicos, con su
        propia tabla de Documentos Anulados. Los Diarios de timbrado
        físico los sigue numerando la localización, con la suya: son
        conjuntos disjuntos y ninguno de los dos consulta al otro.

        Todo elemento propio se identifica con el prefijo fe_py.
    """,
    "author": "FC_Py",
    "website": "http://www.www.com.py",
    "category": "Localización",
    "version": "2026.19.017",
    "license": "OPL-1",
    "depends": ["account"],
    "external_dependencies": {
        "python": ["lxml", "cryptography", "signxml", "qrcode"],
    },
    "data": [
        "security/ir.model.access.csv",
        # -- Datos de catálogos DNIT --------------------------------------
        "data/fe_py_catalogos_data.xml",
        "data/fe_py_unidad_medida_data.xml",
        "data/fe_py_tipo_documento_data.xml",
        "data/fe_py_tipo_identificacion_data.xml",
        "data/fe_py_sequence_data.xml",
        "data/fe_py_cron_data.xml",
        # -- Reporte KuDE -------------------------------------------------
        "report/fe_py_report_paperformat.xml",
        "report/fe_py_report_kude_template.xml",
        # -- Menú (debe cargarse antes de las vistas que cuelgan de él) ---
        "views/fe_py_menu_views.xml",
        # -- Configuración y catálogos propios ---------------------------
        "views/fe_py_catalogos_views.xml",
        "views/fe_py_configuracion_views.xml",
        # -- Campos sobre modelos nativos de Odoo ------------------------
        "views/account_tax_views.xml",
        "views/res_currency_views.xml",
        "views/account_payment_term_views.xml",
        "views/product_template_views.xml",
        "views/product_product_views.xml",
        "views/uom_uom_views.xml",
        "views/account_journal_views.xml",
        "views/account_move_views.xml",
        "views/res_partner_views.xml",
        # -- Mapeo de Datos y Documentos Anulados ------------------------
        "views/fe_py_mapeo_views.xml",
        "views/fe_py_documento_anulado_views.xml",
        # -- Documento Electrónico, Log y Eventos ------------------------
        "views/fe_py_documento_electronico_views.xml",
        "views/fe_py_documento_electronico_log_views.xml",
        "views/fe_py_evento_views.xml",
        # -- Licencia del producto (OPL-1) -------------------------------
        "views/res_config_settings_views.xml",
    ],
    "post_init_hook": "post_init_hook",
}
