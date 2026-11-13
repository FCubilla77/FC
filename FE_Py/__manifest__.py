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

        Este módulo no modifica archivos de local_py: toda extensión sobre
        sus modelos (account.move, account.journal, res.company,
        local_py.tipo_fiscal) se agrega por herencia desde FE_Py, y
        todo elemento propio se identifica con el prefijo fe_py.
    """,
    "author": "FC_Py",
    "website": "http://www.www.com.py",
    "category": "Localización",
    "version": "2026.19.012",
    "license": "LGPL-3",
    "depends": ["local_py"],
    "external_dependencies": {
        "python": ["lxml", "cryptography", "signxml", "qrcode"],
    },
    "data": [
        "security/ir.model.access.csv",
        # -- Datos de catálogos DNIT --------------------------------------
        "data/fe_py_catalogos_data.xml",
        "data/fe_py_unidad_medida_data.xml",
        "data/fe_py_tipo_fiscal_data.xml",
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
        # -- Campos sobre modelos de local_py ----------------------------
        "views/fe_py_tipo_fiscal_views.xml",
        "views/fe_py_tipo_identificacion_fiscal_views.xml",
        "views/fe_py_documento_anulado_views.xml",
        # -- Documento Electrónico, Log y Eventos ------------------------
        "views/fe_py_documento_electronico_views.xml",
        "views/fe_py_documento_electronico_log_views.xml",
        "views/fe_py_evento_views.xml",
    ],
    "post_init_hook": "post_init_hook",
}
