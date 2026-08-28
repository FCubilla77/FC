# -*- coding: utf-8 -*-

from odoo import fields, models


class LocalPyDocumentoAnulado(models.Model):
    _inherit = 'local_py.documento_anulado'

    fe_py_evento_id = fields.Many2one(
        'fe_py.evento', string='Evento SIFEN (FE_Py)', copy=False,
        help='Si este Documento Anulado se generó automáticamente por un '
             'Evento de Inutilización de FE_Py, referencia a ese Evento — '
             'vacío si se cargó a mano o por el asistente propio de local_py.',
    )
