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
    company_currency_id = fields.Many2one(
        related='orden_pago_id.company_id.currency_id', string='Moneda de la Empresa',
    )
    diferencia_cambio = fields.Monetary(
        string='Diferencia de Cambio (vista previa)', compute='_compute_conversion',
        currency_field='company_currency_id',
        help='Estimación en la Moneda de la Empresa — la diferencia de cambio siempre '
             'ocurre ahí, sin importar en qué moneda esté la Orden de Pago (la factura '
             'se contabilizó originalmente contra una cuenta en Moneda de la Empresa, a '
             'una cotización distinta a la de hoy). El asiento real lo genera Odoo de '
             'forma nativa al Confirmar (puede no coincidir centavo a centavo con esta '
             'vista previa).',
    )
    retencion_iva_estimada = fields.Monetary(
        string='Retención IVA (estimada)', compute='_compute_retencion_iva_estimada',
        currency_field='header_currency_id',
        help='Lo que el sistema va a retener de esta Factura al Confirmar, según la '
             'situación actual del Proveedor. Descuéntelo de sus otros Medios de Pago '
             'para que el cuadre no se rompa al Confirmar.',
    )

    @api.depends('importe_a_pagar', 'cotizacion', 'orden_pago_id.factura_ids.importe_a_pagar',
                 'orden_pago_id.partner_id', 'orden_pago_id.fecha', 'orden_pago_id.state')
    def _compute_retencion_iva_estimada(self):
        ordenes_abiertas = self.mapped('orden_pago_id').filtered(lambda o: o.state != 'confirmado')
        evaluaciones = {orden: orden._evaluar_retencion_iva() for orden in ordenes_abiertas}
        for linea in self:
            if linea.orden_pago_id.state == 'confirmado':
                retencion = self.env['local_py.retencion_emitida'].search([
                    ('orden_pago_factura_id', '=', linea.id), ('tipo_retencion', '=', 'iva'),
                ], limit=1)
                linea.retencion_iva_estimada = retencion.monto if retencion else 0.0
                continue
            datos = evaluaciones.get(linea.orden_pago_id, {}).get(linea)
            linea.retencion_iva_estimada = datos[1] if datos else 0.0

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

            company = linea.orden_pago_id.company_id
            moneda_empresa = company.currency_id
            fecha = linea.orden_pago_id.fecha or fields.Date.context_today(linea)

            # La Diferencia de Cambio es siempre un fenómeno en Moneda de la Empresa —
            # la factura se contabilizó originalmente contra una cuenta en esa moneda, a
            # una cotización dada; hoy se paga a otra. Esto es independiente de en qué
            # Moneda esté la Orden de Pago (la Cotización de arriba convierte a la
            # Moneda de la Cabecera, que es un dato distinto).
            amount_currency = linea.move_line_id.amount_currency
            if amount_currency:
                tasa_original_empresa = abs(linea.move_line_id.balance / amount_currency)
            else:
                tasa_original_empresa = 1.0
            valor_original_empresa = linea.importe_a_pagar * tasa_original_empresa

            if linea.currency_id and moneda_empresa and linea.currency_id != moneda_empresa:
                valor_hoy_empresa = linea.currency_id._convert(
                    linea.importe_a_pagar, moneda_empresa, company, fecha,
                )
            else:
                valor_hoy_empresa = linea.importe_a_pagar

            linea.diferencia_cambio = valor_hoy_empresa - valor_original_empresa

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

    # ------------------------------------------------------------------
    # Retención IVA
    # ------------------------------------------------------------------
    def _proporcion_pago(self):
        self.ensure_one()
        if not self.total_original:
            return 0.0
        return self.importe_a_pagar / self.total_original

    def _monto_header_a_gs(self, monto_header, fecha):
        """Convierte un monto en Moneda de la Cabecera a Guaraníes (moneda
        de la empresa), a la Cotización de la fecha indicada."""
        self.ensure_one()
        company = self.orden_pago_id.company_id
        moneda_empresa = company.currency_id
        if not self.header_currency_id or self.header_currency_id == moneda_empresa:
            return monto_header
        return self.header_currency_id._convert(monto_header, moneda_empresa, company, fecha)

    def _imponible_proporcional_gs(self):
        """Valor Imponible (Total factura - IVA) correspondiente a la
        porción pagada en este pago parcial, convertido a Guaraníes —
        usado para el control del acumulado mensual."""
        self.ensure_one()
        move = self.move_line_id.move_id
        proporcion = self._proporcion_pago()
        imponible_moneda_factura = move.amount_untaxed * proporcion
        imponible_header = imponible_moneda_factura * (self.cotizacion or 0.0)
        fecha = self.orden_pago_id.fecha or fields.Date.context_today(self)
        return self._monto_header_a_gs(imponible_header, fecha)

    def _retencion_iva_calcular(self, porcentaje):
        """Devuelve (base_header, monto_header, monto_gs) del IVA a
        retener de esta factura/cuota, proporcional al pago parcial, en
        la Moneda de la Cabecera y su equivalente en Guaraníes."""
        self.ensure_one()
        move = self.move_line_id.move_id
        proporcion = self._proporcion_pago()
        iva_moneda_factura = move.amount_tax * proporcion
        iva_header = iva_moneda_factura * (self.cotizacion or 0.0)
        monto_header = iva_header * (porcentaje / 100.0)
        fecha = self.orden_pago_id.fecha or fields.Date.context_today(self)
        monto_gs = self._monto_header_a_gs(monto_header, fecha)
        return iva_header, monto_header, monto_gs
