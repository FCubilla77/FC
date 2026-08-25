# -*- coding: utf-8 -*-

from odoo import fields, models


class LocalPyReciboSaldoFavorWizard(models.TransientModel):
    _name = 'local_py.recibo.saldo_favor_wizard'
    _description = 'Decisión sobre el sobrante entre Medios de Cobro y Facturas'

    recibo_id = fields.Many2one('local_py.recibo', required=True)
    diferencia = fields.Monetary(related='recibo_id.diferencia', currency_field='currency_id', readonly=True)
    currency_id = fields.Many2one(related='recibo_id.currency_id', readonly=True)
    decision = fields.Selection(
        [
            ('corregir', 'Corregir importes (no avanza, ajusto Facturas o Medios a mano)'),
            ('saldo_favor', 'Dejar como Saldo a Favor del Cliente'),
        ],
        string='¿Qué hacemos con el sobrante?', default='corregir', required=True,
    )

    def action_confirmar(self):
        self.ensure_one()
        if self.decision == 'saldo_favor':
            self.recibo_id.permite_saldo_a_favor = True
            self.recibo_id.action_marcar_en_proceso()
        return {'type': 'ir.actions.act_window_close'}
