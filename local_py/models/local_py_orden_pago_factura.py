# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class LocalPyOrdenPagoFactura(models.Model):
    _name = 'local_py.orden_pago.factura'
    _description = 'Factura/Cuota a pagar en una Orden de Pago'

    orden_pago_id = fields.Many2one(
        'local_py.orden_pago', string='Orden de Pago', required=True, ondelete='cascade',
    )
    move_line_id = fields.Many2one(
        'account.move.line', string='Factura/Cuota', required=True,
        help='La línea contable de deuda (una factura sin cuotas tiene una sola línea; una '
             'factura con varios vencimientos tiene una línea por cada cuota).',
    )
    move_id = fields.Many2one(related='move_line_id.move_id', string='Factura')
    fecha_factura = fields.Date(related='move_id.invoice_date', string='Fecha Factura')
    cuota = fields.Char(
        related='move_line_id.name', string='Cuota',
        help='Misma etiqueta que tiene esta línea en el apunte contable de la factura '
             '(por ejemplo, "Cuota 1/3" si la factura tiene varios vencimientos).',
    )
    fecha_vencimiento = fields.Date(related='move_line_id.date_maturity', string='Vencimiento')
    total_original = fields.Monetary(
        string='Total Original', compute='_compute_montos', currency_field='currency_id',
    )
    saldo_pendiente = fields.Monetary(
        string='Saldo Pendiente', compute='_compute_montos', currency_field='currency_id',
    )
    currency_id = fields.Many2one(related='orden_pago_id.currency_id')
    importe_a_pagar = fields.Monetary(string='Importe a Pagar', currency_field='currency_id')

    @api.depends('move_line_id.balance', 'move_line_id.amount_residual')
    def _compute_montos(self):
        for linea in self:
            linea.total_original = abs(linea.move_line_id.balance)
            linea.saldo_pendiente = abs(linea.move_line_id.amount_residual)

    @api.constrains('importe_a_pagar', 'saldo_pendiente')
    def _check_importe_a_pagar(self):
        for linea in self:
            if linea.importe_a_pagar <= 0:
                raise ValidationError('El importe a pagar de cada factura/cuota debe ser mayor a cero.')
            if linea.currency_id.compare_amounts(linea.importe_a_pagar, linea.saldo_pendiente) > 0:
                raise ValidationError(
                    'El importe a pagar de "%s" no puede ser mayor a su saldo pendiente (%s).'
                    % (linea.move_id.name or '', linea.saldo_pendiente)
                )
