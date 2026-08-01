# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class LocalPyChequeraCheque(models.Model):
    _name = 'local_py.chequera.cheque'
    _description = 'Cheque (emitido / anulado / reutilizable)'
    _order = 'numero'

    chequera_id = fields.Many2one('local_py.chequera', string='Chequera', required=True, ondelete='cascade')
    numero = fields.Integer(string='Número', required=True)
    estado = fields.Selection(
        [('emitido', 'Emitido'), ('anulado', 'Anulado'), ('reutilizable', 'Reutilizable')],
        string='Estado', default='emitido', required=True, copy=False,
    )
    fecha_emision = fields.Date(string='Fecha Emisión')
    motivo_anulacion = fields.Char(string='Motivo')
    payment_id = fields.Many2one(
        'account.payment', string='Pago', readonly=True, copy=False,
        help='Pago para el cual se emitió originalmente este número de cheque.',
    )
    orden_pago_medio_id = fields.Many2one(
        'local_py.orden_pago.medio', string='Medio de Pago origen', readonly=True, copy=False,
    )

    _numero_chequera_uniq = models.Constraint(
        'unique(chequera_id, numero)',
        'Ese número ya existe para esta Chequera.',
    )

    def action_anular(self):
        """Anula un cheque puntual (dañado, perdido, etc.) sin tocar la
        Orden de Pago ni el pago que lo generó — ambos siguen intactos,
        solo se invalida este número físico de cheque."""
        for cheque in self:
            if cheque.estado == 'anulado':
                raise UserError('El cheque %s ya está anulado.' % cheque.numero)
            cheque.estado = 'anulado'

    def action_marcar_reutilizable(self):
        for cheque in self:
            cheque.estado = 'reutilizable'
