# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class LocalPyOrdenPagoFactura(models.Model):
    _name = 'local_py.orden_pago.factura'
    _description = 'Factura/Cuota a pagar en una Orden de Pago'

    def _compute_display_name(self):
        for linea in self:
            linea.display_name = (
                linea.move_line_id.move_id.l10n_py_nro_documento
                or linea.move_line_id.move_id.name
                or ''
            )

    orden_pago_id = fields.Many2one(
        'local_py.orden_pago', string='Orden de Pago', required=True, ondelete='cascade',
    )
    move_line_id = fields.Many2one(
        'account.move.line', string='Factura/Cuota', required=True,
        help='La línea contable de deuda (una factura sin cuotas tiene una sola línea; una '
             'factura con varios vencimientos tiene una línea por cada cuota).',
    )
    move_id = fields.Many2one(related='move_line_id.move_id', string='Factura')
    nro_documento_factura = fields.Char(related='move_id.l10n_py_nro_documento', string='Nro. Documento')
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
            linea.retencion_iva_estimada = datos['monto_total'] if datos else 0.0

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
    def _bases_iva_por_tasa(self):
        """Mira las líneas reales de la factura (no el total agregado) y
        separa, en la moneda propia de la factura, la Base Imponible y
        el IVA correspondientes a cada tasa (5% y 10%). Los ítems
        Exentos quedan naturalmente afuera de ambos — no tienen una tasa
        de IVA que los incluya."""
        self.ensure_one()
        move = self.move_line_id.move_id
        base_5 = base_10 = iva_5 = iva_10 = 0.0
        lineas_producto = move.line_ids.filtered(lambda l: l.display_type == 'product')
        for linea in lineas_producto:
            tasas = [round(t) for t in linea.tax_ids.mapped('amount')]
            if 10 in tasas:
                base_10 += linea.price_subtotal
            elif 5 in tasas:
                base_5 += linea.price_subtotal
        lineas_impuesto = move.line_ids.filtered(lambda l: l.tax_line_id)
        for linea in lineas_impuesto:
            tasa = round(linea.tax_line_id.amount)
            if tasa == 10:
                iva_10 += abs(linea.amount_currency)
            elif tasa == 5:
                iva_5 += abs(linea.amount_currency)
        return base_5, iva_5, base_10, iva_10

    def _proporcion_pago(self):
        self.ensure_one()
        if not self.total_original:
            return 0.0
        return self.importe_a_pagar / self.total_original

    def _monto_header_a_gs(self, monto_header, fecha):
        """Convierte un monto en Moneda de la Cabecera a Guaraníes (moneda
        de la empresa), a la Cotización de la fecha indicada — redondeado
        con la precisión propia de esa moneda, para no dejar ruido de
        coma flotante en el valor guardado."""
        self.ensure_one()
        company = self.orden_pago_id.company_id
        moneda_empresa = company.currency_id
        if not self.header_currency_id or self.header_currency_id == moneda_empresa:
            return moneda_empresa.round(monto_header)
        return moneda_empresa.round(
            self.header_currency_id._convert(monto_header, moneda_empresa, company, fecha)
        )

    def _total_gravado_proporcional_gs(self):
        """Total Gravado (Base al 5% + Base al 10%, SIN Exentos)
        correspondiente a la porción pagada en este pago parcial,
        convertido a Guaraníes — usado para el control del acumulado
        mensual contra el Valor Imponible Mínimo."""
        self.ensure_one()
        base_5, _iva_5, base_10, _iva_10 = self._bases_iva_por_tasa()
        proporcion = self._proporcion_pago()
        total_gravado_moneda_factura = (base_5 + base_10) * proporcion
        header = total_gravado_moneda_factura * (self.cotizacion or 0.0)
        fecha = self.orden_pago_id.fecha or fields.Date.context_today(self)
        return self._monto_header_a_gs(header, fecha)

    def _retencion_absorcion_calcular(self):
        """Retención con Absorción para proveedores del exterior
        (Concepto IVA distinto de IVA.1): la factura real nunca tiene
        IVA (llega Exenta) — se calcula un IVA "nocional" al 10% sobre
        el importe que se está pagando ahora, solo para determinar
        cuánto retener, y se retiene el 100% de ese IVA nocional. La
        factura en sí no se toca en ningún momento."""
        self.ensure_one()
        fecha = self.orden_pago_id.fecha or fields.Date.context_today(self)
        iva_nocional_factura = self.importe_a_pagar * 0.10
        iva_nocional_header = self.header_currency_id.round(iva_nocional_factura * (self.cotizacion or 0.0))
        monto_header = iva_nocional_header  # Retención del 100% del IVA nocional.
        monto_gs = self._monto_header_a_gs(monto_header, fecha)
        return iva_nocional_header, monto_header, monto_gs

    def _retencion_iva_calcular(self, porcentaje):
        """Devuelve un diccionario con la Retención IVA de esta
        factura/cuota, proporcional al pago parcial, separada por tasa
        (5 y 10), en la Moneda de la Cabecera y su equivalente en
        Guaraníes. El mismo Porcentaje se aplica sobre ambos tramos."""
        self.ensure_one()
        base_5, iva_5, base_10, iva_10 = self._bases_iva_por_tasa()
        proporcion = self._proporcion_pago()
        fecha = self.orden_pago_id.fecha or fields.Date.context_today(self)
        cotizacion = self.cotizacion or 0.0

        resultado = {}
        for tasa, iva_tasa in (('5', iva_5), ('10', iva_10)):
            iva_prop = iva_tasa * proporcion
            iva_header = self.header_currency_id.round(iva_prop * cotizacion)
            monto_header = self.header_currency_id.round(iva_header * (porcentaje / 100.0))
            monto_gs = self._monto_header_a_gs(monto_header, fecha)
            resultado[tasa] = {'base': iva_header, 'monto': monto_header, 'monto_gs': monto_gs}
        return resultado

