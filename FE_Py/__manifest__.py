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
    "version": "2026.01.002",
    "license": "LGPL-3",
    "depends": ["local_py"],
    "data": [
        "security/ir.model.access.csv",
    ],
}
