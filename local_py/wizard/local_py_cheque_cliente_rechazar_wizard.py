# -*- coding: utf-8 -*-

from odoo import fields, models


class LocalPyChequeClienteRechazarWizard(models.TransientModel):
    _name = 'local_py.cheque_cliente.rechazar_wizard'
    _description = 'Motivo de Rechazo de un Cheque de Cliente'

    cheque_id = fields.Many2one('local_py.cheque_cliente', required=True)
    fecha = fields.Date(string='Fecha de Rechazo', default=fields.Date.context_today, required=True)
    motivo = fields.Char(string='Motivo de Rechazo', required=True)

    def action_confirmar(self):
        self.ensure_one()
        self.cheque_id.action_rechazar(self.motivo, self.fecha)
        return {'type': 'ir.actions.act_window_close'}
