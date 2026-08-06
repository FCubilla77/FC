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
    fecha_vencimiento = fields.Date(related='orden_pago_medio_id.fecha_vencimiento', string='Fecha Venc.')
    motivo_anulacion = fields.Char(string='Motivo')
    payment_ids = fields.Many2many(
        'account.payment', string='Pagos', compute='_compute_payment_ids',
        help='Todos los Pagos generados por la misma fila de Medios de este cheque — '
             'normalmente es uno solo, pero puede ser más de uno si el cheque tuvo que '
             'repartirse entre varias facturas (mismo cheque físico, varios Pagos internos '
             'para que la conciliación quede exacta contra cada factura).',
    )
    importe = fields.Monetary(
        string='Importe', compute='_compute_importe', currency_field='moneda_pago_id',
        help='Suma de todos los Pagos de este cheque — coincide con el valor real del '
             'cheque físico, incluso cuando tuvo que repartirse en más de un Pago interno.',
    )
    moneda_pago_id = fields.Many2one(related='payment_id.currency_id', string='Moneda (para importe)')
    proveedor = fields.Many2one(related='payment_id.partner_id', string='Proveedor')
    payment_id = fields.Many2one(
        'account.payment', string='Pago', readonly=True, copy=False,
        help='Pago principal para el cual se emitió originalmente este número de cheque '
             '(si el cheque se repartió en más de un Pago, ver el campo "Pagos" para '
             'verlos todos).',
    )
    orden_pago_medio_id = fields.Many2one(
        'local_py.orden_pago.medio', string='Medio de Pago origen', readonly=True, copy=False,
    )
    orden_pago_id = fields.Many2one(
        related='orden_pago_medio_id.orden_pago_id', string='Orden de Pago',
    )

    @api.depends('orden_pago_medio_id.payment_ids')
    def _compute_payment_ids(self):
        for cheque in self:
            cheque.payment_ids = cheque.orden_pago_medio_id.payment_ids

    @api.depends('payment_ids.amount')
    def _compute_importe(self):
        for cheque in self:
            cheque.importe = sum(cheque.payment_ids.mapped('amount'))

    _numero_chequera_uniq = models.Constraint(
        'unique(chequera_id, numero)',
        'Ese número ya existe para esta Chequera.',
    )

    def _compute_display_name(self):
        for cheque in self:
            partes = [
                cheque.chequera_id.bank_id.name or '',
                'N° %s' % str(cheque.numero).zfill(8),
            ]
            if cheque.payment_id:
                partes.append(cheque.payment_id.currency_id.symbol + ' ' + str(cheque.importe))
            if cheque.fecha_emision:
                partes.append(cheque.fecha_emision.strftime('%d/%m/%Y'))
            cheque.display_name = ' - '.join(p for p in partes if p)

    @api.model_create_multi
    def create(self, vals_list):
        cheques = super().create(vals_list)
        for cheque in cheques:
            chequera = cheque.chequera_id
            if cheque.numero > chequera.ultimo_numero_utilizado:
                chequera.ultimo_numero_utilizado = cheque.numero
        return cheques

    def unlink(self):
        raise UserError(
            'No se puede eliminar un Cheque (para no dejar huecos en la numeración). '
            'Use "Anular" en su lugar.'
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
