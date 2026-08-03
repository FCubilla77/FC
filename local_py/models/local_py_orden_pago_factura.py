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

    # Moneda propia de la factura (puede ser distinta de la moneda de la cabecera).
    currency_id = fields.Many2one(related='move_line_id.currency_id', string='Moneda Factura')
    header_currency_id = fields.Many2one(related='orden_pago_id.currency_id', string='Moneda Cabecera')
    misma_moneda = fields.Boolean(compute='_compute_misma_moneda')

    total_original = fields.Monetary(
        string='Total Original', compute='_compute_montos', currency_field='currency_id',
    )
    saldo_pendiente = fields.Monetary(
        string='Saldo Pendiente', compute='_compute_montos', currency_field='currency_id',
    )
    importe_a_pagar = fields.Monetary(string='Importe a Pagar', currency_field='currency_id')

    cotizacion = fields.Float(
        string='Cotización', digits=(16, 6),
        help='Cuántas unidades de la Moneda de la Cabecera equivalen a 1 unidad de la '
             'Moneda de la Factura, a la Fecha de la Orden de Pago. Se completa sola con '
             'la tasa que ya tiene cargada Odoo, pero se puede corregir a mano para esta '
             'operación puntual.',
    )
    cotizacion_manual = fields.Boolean(
        string='Cotización editada a mano', default=False,
        help='Si está tildado, no se vuelve a pisar esta cotización al Confirmar — el '
             'usuario ya la corrigió a propósito.',
    )
    valor_convertido = fields.Monetary(
        string='Valor a Pagar (Moneda Cabecera)', compute='_compute_conversion',
        currency_field='header_currency_id',
    )
    diferencia_cambio = fields.Monetary(
        string='Diferencia de Cambio (vista previa)', compute='_compute_conversion',
        currency_field='header_currency_id',
        help='Estimación, comparando la cotización original de la factura contra la '
             'cotización de esta Orden de Pago. El asiento real de diferencia de cambio '
             'lo genera Odoo de forma nativa al Confirmar, con la cotización vigente en '
             'ese momento (puede no coincidir exactamente con esta vista previa).',
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

    @api.depends('importe_a_pagar', 'cotizacion', 'currency_id', 'header_currency_id',
                 'move_line_id.balance', 'move_line_id.amount_currency', 'orden_pago_id.fecha')
    def _compute_conversion(self):
        for linea in self:
            linea.valor_convertido = linea.importe_a_pagar * (linea.cotizacion or 0.0)

            amount_currency = linea.move_line_id.amount_currency
            if amount_currency:
                tasa_original = abs(linea.move_line_id.balance / amount_currency)
            else:
                tasa_original = 1.0
            # tasa_original está en Moneda de la Empresa por unidad de Moneda de la
            # Factura — hay que llevarlo a la Moneda de la Cabecera antes de comparar,
            # para no mezclar unidades distintas en la resta.
            valor_original_moneda_empresa = linea.importe_a_pagar * tasa_original
            company = linea.orden_pago_id.company_id
            moneda_empresa = company.currency_id
            if moneda_empresa and moneda_empresa != linea.header_currency_id:
                fecha = linea.orden_pago_id.fecha or fields.Date.context_today(linea)
                valor_original_cabecera = moneda_empresa._convert(
                    valor_original_moneda_empresa, linea.header_currency_id, company, fecha,
                )
            else:
                valor_original_cabecera = valor_original_moneda_empresa

            linea.diferencia_cambio = linea.valor_convertido - valor_original_cabecera

    @api.onchange('cotizacion')
    def _onchange_cotizacion(self):
        for linea in self:
            linea.cotizacion_manual = True

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
                company=linea.orden_pago_id.company_id,
                date=fecha,
            )

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
