# -*- coding: utf-8 -*-

from odoo import fields, models


class LocalPyReciboAnularWizard(models.TransientModel):
    _name = 'local_py.recibo.anular_wizard'
    _description = 'Motivo de Anulación de un Recibo'

    recibo_id = fields.Many2one('local_py.recibo', required=True)
    motivo = fields.Char(string='Motivo de Anulación', required=True)

    def action_confirmar(self):
        self.ensure_one()
        self.recibo_id.action_anular(self.motivo)
        return {'type': 'ir.actions.act_window_close'}
