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
        local_py.tipo_fiscal) se agrega por herencia desde FE_Py.
    """,
    "author": "FC_Py",
    "website": "http://www.www.com.py",
    "category": "Localización",
    "version": "2026.03.001",
    "license": "LGPL-3",
    "depends": ["local_py"],
    "external_dependencies": {
        "python": ["lxml", "cryptography", "signxml", "qrcode"],
    },
    "data": [
        "security/ir.model.access.csv",
        "data/fe_py_catalogos_data.xml",
        "data/fe_py_unidad_medida_data.xml",
        "data/local_py_tipo_fiscal_data.xml",
        "data/fe_py_sequence_data.xml",
        "data/fe_py_cron_data.xml",
        "report/fe_py_report_paperformat.xml",
        "report/fe_py_report_kude_template.xml",
        "views/fe_py_menu_views.xml",
        "views/fe_py_catalogos_views.xml",
        "views/fe_py_configuracion_views.xml",
        "views/fe_py_campos_existentes_views.xml",
        "views/account_journal_views.xml",
        "views/account_move_views.xml",
        "views/local_py_tipo_fiscal_views.xml",
        "views/res_partner_views.xml",
        "views/fe_py_documento_electronico_views.xml",
        "views/fe_py_documento_electronico_log_views.xml",
        "views/fe_py_evento_views.xml",
    ],
    "post_init_hook": "post_init_hook",
}
