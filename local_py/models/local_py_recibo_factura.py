# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class LocalPyReciboFactura(models.Model):
    _name = 'local_py.recibo.factura'
    _description = 'Factura/Cuota a cobrar en un Recibo'

    def _compute_display_name(self):
        for linea in self:
            linea.display_name = (
                linea.move_line_id.move_id.l10n_py_nro_documento
                or linea.move_line_id.move_id.name
                or ''
            )

    recibo_id = fields.Many2one('local_py.recibo', string='Recibo', required=True, ondelete='cascade')
    move_line_id = fields.Many2one(
        'account.move.line', string='Factura/Cuota', required=True,
        help='La línea contable de deuda del Cliente (una factura sin cuotas tiene una '
             'sola línea; una factura con varios vencimientos tiene una línea por cada '
             'cuota).',
    )
    move_id = fields.Many2one(related='move_line_id.move_id', string='Factura')
    nro_documento_factura = fields.Char(related='move_id.l10n_py_nro_documento', string='Nro. Documento')
    fecha_factura = fields.Date(related='move_id.invoice_date', string='Fecha Factura')
    cuota = fields.Char(related='move_line_id.name', string='Cuota')
    fecha_vencimiento = fields.Date(related='move_line_id.date_maturity', string='Vencimiento')

    currency_id = fields.Many2one(related='move_line_id.currency_id', string='Moneda Factura')
    header_currency_id = fields.Many2one(related='recibo_id.currency_id', string='Moneda Cabecera')
    misma_moneda = fields.Boolean(compute='_compute_misma_moneda')

    total_original = fields.Monetary(
        string='Total Original', compute='_compute_montos', currency_field='currency_id',
    )
    saldo_pendiente = fields.Monetary(
        string='Saldo Pendiente', compute='_compute_montos', currency_field='currency_id',
    )
    importe_a_cobrar = fields.Monetary(string='Importe a Cobrar', currency_field='currency_id')
    retencion_importe = fields.Monetary(
        string='Importe Retención', currency_field='currency_id',
        help='Cuánto de esta Factura/Cuota retiene el Cliente al pagar — informado por '
             'el Cliente, no calculado por el sistema. Se descuenta del Importe a '
             'Cobrar; no puede superarlo. Al Confirmar el Recibo genera un registro de '
             'Retención Recibida y su asiento a la Cuenta "Retenido a Confirmar".',
    )
    retencion_valor_convertido = fields.Monetary(
        string='Retención (Moneda Cabecera)', compute='_compute_conversion',
        currency_field='header_currency_id',
    )
    retencion_recibida_id = fields.Many2one(
        'local_py.retencion_recibida', string='Retención Recibida generada', readonly=True, copy=False,
    )

    cotizacion = fields.Float(
        string='Cotización', digits=(16, 6),
        help='Cuántas unidades de la Moneda de la Cabecera equivalen a 1 unidad de la '
             'Moneda de la Factura, a la Fecha del Recibo. Se completa sola con la tasa '
             'que ya tiene cargada Odoo, pero se puede corregir a mano para esta '
             'operación puntual.',
    )
    cotizacion_manual = fields.Boolean(string='Cotización editada a mano', default=False)
    valor_convertido = fields.Monetary(
        string='Valor a Cobrar (Moneda Cabecera)', compute='_compute_conversion',
        currency_field='header_currency_id',
    )

    @api.depends('currency_id', 'header_currency_id')
    def _compute_misma_moneda(self):
        for linea in self:
            linea.misma_moneda = linea.currency_id == linea.header_currency_id

    @api.depends('move_line_id.amount_currency', 'move_line_id.amount_residual_currency',
                 'move_line_id.balance', 'move_line_id.amount_residual')
    def _compute_montos(self):
        for linea in self:
            if linea.move_line_id.currency_id:
                linea.total_original = abs(linea.move_line_id.amount_currency)
                linea.saldo_pendiente = abs(linea.move_line_id.amount_residual_currency)
            else:
                linea.total_original = abs(linea.move_line_id.balance)
                linea.saldo_pendiente = abs(linea.move_line_id.amount_residual)

    @api.depends('importe_a_cobrar', 'retencion_importe', 'cotizacion')
    def _compute_conversion(self):
        for linea in self:
            linea.valor_convertido = linea.importe_a_cobrar * (linea.cotizacion or 0.0)
            linea.retencion_valor_convertido = linea.retencion_importe * (linea.cotizacion or 0.0)

    @api.onchange('cotizacion')
    def _onchange_cotizacion(self):
        self.cotizacion_manual = True

    def _set_cotizacion_default(self, fecha):
        """Completa la Cotización con la tasa que ya tiene cargada Odoo,
        para la Moneda de la Factura contra la Moneda de la Cabecera, a la
        fecha indicada. No pisa una cotización que el usuario ya haya
        editado a mano."""
        for linea in self:
            if linea.cotizacion_manual:
                continue
            if linea.currency_id == linea.header_currency_id:
                linea.cotizacion = 1.0
                continue
            linea.cotizacion = self.env['res.currency']._get_conversion_rate(
                from_currency=linea.currency_id,
                to_currency=linea.header_currency_id,
                company=linea.recibo_id.company_id,
                date=fecha,
            )

    @api.constrains('importe_a_cobrar', 'saldo_pendiente')
    def _check_importe_a_cobrar(self):
        for linea in self:
            if linea.importe_a_cobrar <= 0:
                raise ValidationError('El importe a cobrar de cada factura/cuota debe ser mayor a cero.')
            if linea.currency_id.compare_amounts(linea.importe_a_cobrar, linea.saldo_pendiente) > 0:
                raise ValidationError(
                    'El importe a cobrar de "%s" no puede ser mayor a su saldo pendiente (%s).'
                    % (linea.move_id.name or '', linea.saldo_pendiente)
                )

    @api.constrains('retencion_importe', 'importe_a_cobrar')
    def _check_retencion_importe(self):
        for linea in self:
            if linea.retencion_importe < 0:
                raise ValidationError('El Importe Retención no puede ser negativo.')
            if linea.currency_id.compare_amounts(linea.retencion_importe, linea.importe_a_cobrar) > 0:
                raise ValidationError(
                    'El Importe Retención de "%s" no puede ser mayor a su Importe a Cobrar (%s).'
                    % (linea.move_id.name or '', linea.importe_a_cobrar)
                )
