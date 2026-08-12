# -*- coding: utf-8 -*-

from odoo import fields, models


class LocalPyOrdenPagoSaldoFavorWizard(models.TransientModel):
    _name = 'local_py.orden_pago.saldo_favor_wizard'
    _description = 'Decisión sobre el sobrante entre Medios de Pago y Facturas'

    orden_pago_id = fields.Many2one('local_py.orden_pago', required=True)
    diferencia = fields.Monetary(related='orden_pago_id.diferencia', currency_field='currency_id', readonly=True)
    currency_id = fields.Many2one(related='orden_pago_id.currency_id', readonly=True)
    decision = fields.Selection(
        [
            ('corregir', 'Corregir importes (no avanza, ajusto Facturas o Medios a mano)'),
            ('saldo_favor', 'Dejar como Saldo a Favor del Proveedor'),
        ],
        string='¿Qué hacemos con el sobrante?', default='corregir', required=True,
    )

    def action_confirmar(self):
        self.ensure_one()
        if self.decision == 'saldo_favor':
            self.orden_pago_id.permite_saldo_a_favor = True
            self.orden_pago_id.action_marcar_en_proceso()
        return {'type': 'ir.actions.act_window_close'}
