# -*- coding: utf-8 -*-
from odoo import models, fields, api

# Tipos de comprobante (código Tabla 4 DNIT) para los que, en COMPRAS, los 3
# montos por tasa de IVA se informan en 0 y solo se completa el Monto Total.
COMPRAS_MONTOS_EN_CERO_CODES = ('101', '104', '105', '112')

# Código de Tipo de Comprobante "Factura": la Condición de Venta/Compra solo
# se informa para este tipo; en el resto de los tipos va vacía.
CODIGO_FACTURA = '109'

# Códigos de Tipo de Comprobante para los que corresponde informar el
# comprobante asociado (Nota de Crédito / Nota de Débito).
CODIGOS_NOTA_CREDITO_DEBITO = ('110', '111')

CONDICION_CODE_MAP = {'contado': '1', 'credito': '2'}


class AccountMoveMarangatu(models.Model):
    _inherit = 'account.move'

    l10n_py_mkt_codigo_tipo_registro = fields.Char(
        string='Código Tipo de Registro', compute='_compute_l10n_py_mkt_fields',
    )
    l10n_py_mkt_codigo_tipo_identificacion = fields.Char(
        string='Código Tipo de Identificación', compute='_compute_l10n_py_mkt_fields',
    )
    l10n_py_mkt_numero_identificacion = fields.Char(
        string='Número de Identificación', compute='_compute_l10n_py_mkt_fields',
    )
    l10n_py_mkt_nombre_razon_social = fields.Char(
        string='Nombre o Razón Social', compute='_compute_l10n_py_mkt_fields',
    )
    l10n_py_mkt_codigo_tipo_comprobante = fields.Char(
        string='Código Tipo de Comprobante', compute='_compute_l10n_py_mkt_fields',
    )
    l10n_py_mkt_monto_gravado_10 = fields.Monetary(
        string='Monto Gravado 10% (IVA incluido)', compute='_compute_l10n_py_mkt_fields',
        currency_field='currency_id',
    )
    l10n_py_mkt_monto_gravado_5 = fields.Monetary(
        string='Monto Gravado 5% (IVA incluido)', compute='_compute_l10n_py_mkt_fields',
        currency_field='currency_id',
    )
    l10n_py_mkt_monto_exento = fields.Monetary(
        string='Monto no Gravado o Exento', compute='_compute_l10n_py_mkt_fields',
        currency_field='currency_id',
    )
    l10n_py_mkt_codigo_condicion = fields.Char(
        string='Código Condición de Venta/Compra', compute='_compute_l10n_py_mkt_fields',
    )
    l10n_py_mkt_moneda_extranjera = fields.Char(
        string='Operación en Moneda Extranjera', compute='_compute_l10n_py_mkt_fields',
    )
    l10n_py_mkt_imputa_iva = fields.Char(string='Imputa al IVA', compute='_compute_l10n_py_mkt_fields')
    l10n_py_mkt_imputa_ire = fields.Char(string='Imputa al IRE', compute='_compute_l10n_py_mkt_fields')
    l10n_py_mkt_imputa_irp_rsp = fields.Char(string='Imputa al IRP-RSP', compute='_compute_l10n_py_mkt_fields')
    l10n_py_mkt_no_imputa = fields.Char(string='No Imputa', compute='_compute_l10n_py_mkt_fields')
    l10n_py_mkt_timbrado_comprobante_asociado = fields.Char(
        string='Timbrado Comprobante Asociado', compute='_compute_l10n_py_mkt_fields',
    )

    @api.depends(
        'move_type', 'partner_id', 'partner_id.vat',
        'partner_id.l10n_py_tipo_identificacion_fiscal_id',
        'partner_id.l10n_py_tipo_identificacion_fiscal_id.code',
        'local_py_tipo_fiscal_id', 'local_py_tipo_fiscal_id.code',
        'currency_id', 'company_id.currency_id',
        'invoice_payment_term_id', 'invoice_payment_term_id.l10n_py_condicion',
        'invoice_line_ids.tax_ids', 'invoice_line_ids.price_total',
        'invoice_line_ids.display_type', 'l10n_py_imputacion_tributaria_ids',
        'reversed_entry_id', 'reversed_entry_id.l10n_py_timbrado',
    )
    def _compute_l10n_py_mkt_fields(self):
        imputacion_codes = {
            'local_py.imputacion_iva': 'l10n_py_mkt_imputa_iva',
            'local_py.imputacion_ire': 'l10n_py_mkt_imputa_ire',
            'local_py.imputacion_irp_rsp': 'l10n_py_mkt_imputa_irp_rsp',
            'local_py.imputacion_no_imputa': 'l10n_py_mkt_no_imputa',
        }
        imputacion_records = {
            xml_id: self.env.ref(xml_id, raise_if_not_found=False)
            for xml_id in imputacion_codes
        }
        for move in self:
            is_sale = move.move_type in ('out_invoice', 'out_refund')
            is_purchase = move.move_type in ('in_invoice', 'in_refund')

            move.l10n_py_mkt_codigo_tipo_registro = '1' if is_sale else ('2' if is_purchase else False)

            tipo_id = move.partner_id.l10n_py_tipo_identificacion_fiscal_id
            move.l10n_py_mkt_codigo_tipo_identificacion = tipo_id.code if tipo_id else False
            if tipo_id and tipo_id.code == '11' and move.partner_id.vat:
                # RUC: se informa sin el dígito verificador (formato NNNNNNN-D)
                move.l10n_py_mkt_numero_identificacion = move.partner_id.vat.split('-')[0]
            else:
                move.l10n_py_mkt_numero_identificacion = move.partner_id.vat or False
            move.l10n_py_mkt_nombre_razon_social = move.partner_id.name or False

            tipo_fiscal = move.local_py_tipo_fiscal_id
            codigo_comprobante = tipo_fiscal.code if tipo_fiscal else False
            move.l10n_py_mkt_codigo_tipo_comprobante = codigo_comprobante

            montos = move._l10n_py_mkt_montos_por_tasa()
            if is_purchase and codigo_comprobante in COMPRAS_MONTOS_EN_CERO_CODES:
                move.l10n_py_mkt_monto_gravado_10 = 0.0
                move.l10n_py_mkt_monto_gravado_5 = 0.0
                move.l10n_py_mkt_monto_exento = 0.0
            else:
                move.l10n_py_mkt_monto_gravado_10 = montos['10']
                move.l10n_py_mkt_monto_gravado_5 = montos['5']
                move.l10n_py_mkt_monto_exento = montos['exento']

            if codigo_comprobante == CODIGO_FACTURA:
                condicion = move.invoice_payment_term_id.l10n_py_condicion
                move.l10n_py_mkt_codigo_condicion = CONDICION_CODE_MAP.get(condicion, False)
            else:
                move.l10n_py_mkt_codigo_condicion = False

            company_currency = move.company_id.currency_id
            move.l10n_py_mkt_moneda_extranjera = 'S' if (move.currency_id and move.currency_id != company_currency) else 'N'

            tags = move.l10n_py_imputacion_tributaria_ids
            for xml_id, field_name in imputacion_codes.items():
                record = imputacion_records.get(xml_id)
                move[field_name] = 'S' if (record and record in tags) else 'N'

            if codigo_comprobante in CODIGOS_NOTA_CREDITO_DEBITO and move.reversed_entry_id:
                move.l10n_py_mkt_timbrado_comprobante_asociado = (
                    ('%08d' % move.reversed_entry_id.l10n_py_timbrado)
                    if move.reversed_entry_id.l10n_py_timbrado else False
                )
            else:
                move.l10n_py_mkt_timbrado_comprobante_asociado = False

    def _l10n_py_mkt_montos_por_tasa(self):
        """Suma el importe (con IVA incluido) de las líneas de factura,
        agrupado por tasa de IVA: 10%, 5% o exento/no gravado. Cada línea se
        clasifica por la tasa más alta entre los impuestos aplicados."""
        self.ensure_one()
        montos = {'10': 0.0, '5': 0.0, 'exento': 0.0}
        lines = self.invoice_line_ids.filtered(
            lambda l: l.display_type not in ('line_section', 'line_note')
        )
        for line in lines:
            rates = line.tax_ids.mapped('amount')
            if any(abs(r - 10) < 0.001 for r in rates):
                montos['10'] += line.price_total
            elif any(abs(r - 5) < 0.001 for r in rates):
                montos['5'] += line.price_total
            else:
                montos['exento'] += line.price_total
        return montos

    def l10n_py_mkt_row_values(self):
        """Devuelve la fila completa (lista de strings), en el orden exacto
        de la Especificación Técnica de Marangatu (DNIT, RG 90/2021), lista
        para escribir en el archivo CSV/TXT de importación. Aplica las
        reglas de formato oficiales (fecha dd/mm/aaaa, montos como enteros,
        blanqueo de Condición de Venta salvo Factura, etc.)."""
        self.ensure_one()
        is_sale = self.move_type in ('out_invoice', 'out_refund')
        fecha = self.invoice_date.strftime('%d/%m/%Y') if self.invoice_date else ''
        timbrado = ('%08d' % self.l10n_py_timbrado) if self.l10n_py_timbrado else ''
        montos = [
            str(int(round(self.l10n_py_mkt_monto_gravado_10 or 0))),
            str(int(round(self.l10n_py_mkt_monto_gravado_5 or 0))),
            str(int(round(self.l10n_py_mkt_monto_exento or 0))),
            str(int(round(self.amount_total or 0))),
        ]
        common_tail = [
            self.l10n_py_mkt_codigo_condicion or '',
            self.l10n_py_mkt_moneda_extranjera or 'N',
            self.l10n_py_mkt_imputa_iva or 'N',
            self.l10n_py_mkt_imputa_ire or 'N',
            self.l10n_py_mkt_imputa_irp_rsp or 'N',
        ]
        asociado = [
            self.l10n_py_nro_documento_asociado or '',
            self.l10n_py_mkt_timbrado_comprobante_asociado or '',
        ]
        if is_sale:
            return [
                self.l10n_py_mkt_codigo_tipo_registro or '1',
                self.l10n_py_mkt_codigo_tipo_identificacion or '',
                self.l10n_py_mkt_numero_identificacion or '',
                self.l10n_py_mkt_nombre_razon_social or '',
                self.l10n_py_mkt_codigo_tipo_comprobante or '',
                fecha,
                timbrado,
                self.l10n_py_nro_documento or '',
                *montos,
                *common_tail,
                *asociado,
            ]
        return [
            self.l10n_py_mkt_codigo_tipo_registro or '2',
            self.l10n_py_mkt_codigo_tipo_identificacion or '',
            self.l10n_py_mkt_numero_identificacion or '',
            self.l10n_py_mkt_nombre_razon_social or '',
            self.l10n_py_mkt_codigo_tipo_comprobante or '',
            fecha,
            timbrado,
            self.l10n_py_nro_documento or '',
            *montos,
            *common_tail,
            self.l10n_py_mkt_no_imputa or 'N',
            *asociado,
        ]
