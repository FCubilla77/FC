# -*- coding: utf-8 -*-

from odoo import models

from .local_py_numero_a_letras import numero_a_letras
from .local_py_libro_report import fmt_pyg, fmt_moneda


class ReportImpresionCheques(models.AbstractModel):
    _name = 'report.local_py.report_impresion_cheques_document'
    _description = 'Reporte Impresión de Cheques'

    def _get_report_values(self, docids, data=None):
        cheques = self.env['local_py.chequera.cheque'].browse(docids)
        paginas = [cheques[i:i + 3] for i in range(0, len(cheques), 3)] or [cheques]
        return {
            'doc_ids': docids,
            'doc_model': 'local_py.chequera.cheque',
            'docs': cheques,
            'paginas': paginas,
            'numero_a_letras': numero_a_letras,
            'fmt_pyg': fmt_pyg,
            'fmt_moneda': fmt_moneda,
        }
