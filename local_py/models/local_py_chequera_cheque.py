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
    proveedor_id = fields.Many2one(
        'res.partner', string='Proveedor (registrado)', readonly=True, copy=False,
        help='Proveedor para el cual se emitió este cheque — se guarda de forma '
             'independiente al Pago, así no se pierde si la Orden de Pago que lo generó '
             'se revierte más adelante (el Pago se elimina, pero el Cheque sigue '
             'existiendo, por ejemplo para poder reutilizarlo).',
    )
    moneda_id = fields.Many2one(
        'res.currency', string='Moneda (registrada)', readonly=True, copy=False,
    )
    importe_registrado = fields.Monetary(
        string='Importe (registrado)', currency_field='moneda_id', readonly=True, copy=False,
        help='Importe real del cheque al momento de emitirse — se guarda de forma '
             'independiente a los Pagos, por el mismo motivo que el Proveedor.',
    )
    importe = fields.Monetary(
        string='Importe', compute='_compute_importe', currency_field='moneda_pago_id',
        help='Suma de todos los Pagos de este cheque — coincide con el valor real del '
             'cheque físico, incluso cuando tuvo que repartirse en más de un Pago interno. '
             'Si los Pagos ya no existen (por ejemplo, tras Deshacer Confirmación), muestra '
             'el Importe registrado al emitirse.',
    )
    moneda_pago_id = fields.Many2one(
        'res.currency', string='Moneda (para importe)', compute='_compute_proveedor_moneda',
    )
    proveedor = fields.Many2one(
        'res.partner', string='Proveedor', compute='_compute_proveedor_moneda',
    )
    payment_id = fields.Many2one(
        'account.payment', string='Pago', readonly=True, copy=False,
        help='Pago principal para el cual se emitió originalmente este número de cheque '
             '(si el cheque se repartió en más de un Pago, ver el campo "Pagos" para '
             'verlos todos). Puede quedar vacío si ese Pago se eliminó más adelante (por '
             'ejemplo, al Deshacer Confirmación de su Orden de Pago) — el Proveedor y el '
             'Importe quedan igual disponibles en los campos "registrados".',
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

    @api.depends('payment_ids.amount', 'importe_registrado')
    def _compute_importe(self):
        for cheque in self:
            cheque.importe = sum(cheque.payment_ids.mapped('amount')) if cheque.payment_ids else cheque.importe_registrado

    @api.depends('payment_id.partner_id', 'payment_id.currency_id', 'proveedor_id', 'moneda_id')
    def _compute_proveedor_moneda(self):
        for cheque in self:
            cheque.proveedor = cheque.payment_id.partner_id or cheque.proveedor_id
            cheque.moneda_pago_id = cheque.payment_id.currency_id or cheque.moneda_id

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
            if cheque.moneda_pago_id:
                partes.append(cheque.moneda_pago_id.symbol + ' ' + str(cheque.importe))
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
