# -*- coding: utf-8 -*-

from odoo import fields, models


class LocalPyOrdenPagoDeshacerWizard(models.TransientModel):
    _name = 'local_py.orden_pago.deshacer_wizard'
    _description = 'Decisión sobre cheques ya impresos al deshacer una confirmación'

    orden_pago_id = fields.Many2one('local_py.orden_pago', required=True)
    cheque_ids = fields.Many2many(
        'local_py.chequera.cheque', relation='local_py_deshacer_wizard_cheque_rel',
        string='Cheques ya impresos',
    )
    decision = fields.Selection(
        [('reutilizable', 'Reutilizar (el número queda disponible para otra Orden de Pago)'),
         ('anulado', 'Anular (se registra como cheque anulado)')],
        string='¿Qué hacer con estos cheques?', default='reutilizable', required=True,
    )

    def action_confirmar(self):
        self.ensure_one()
        self.cheque_ids.write({'estado': self.decision})
        self.orden_pago_id._deshacer_confirmacion_efectivo()
        return {'type': 'ir.actions.act_window_close'}
