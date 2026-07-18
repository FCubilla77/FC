# -*- coding: utf-8 -*-
import re

from odoo import models, fields, api, exceptions

TIMBRADO_MAX = 99999999
NRO_DOCUMENTO_PATTERN = re.compile(r'^[0-9-]*$')

# Formato esperado del Nro. Documento: 001-001-0000001 (3 + 3 + 7 dígitos)
NRO_DOCUMENTO_SEQ_PATTERN = re.compile(r'^(\d{3}-\d{3}-)(\d{7})$')

# Tipos de movimiento de venta: factura de cliente y nota de crédito de cliente
SALE_MOVE_TYPES = ('out_invoice', 'out_refund')

# Tipos de movimiento de compra: factura de proveedor y nota de crédito de proveedor
PURCHASE_MOVE_TYPES = ('in_invoice', 'in_refund')

# Notas de crédito (venta y compra), usado para el signo en los reportes Libro Ventas/Compras
REFUND_MOVE_TYPES = ('out_refund', 'in_refund')

# Tipos de movimiento sobre los que aplica la obligatoriedad de Timbrado,
# Nro. Documento y Tipo Fiscal: facturas y notas de crédito, tanto de
# clientes como de proveedores.
REQUIRED_FISCAL_MOVE_TYPES = SALE_MOVE_TYPES + PURCHASE_MOVE_TYPES


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_py_timbrado = fields.Integer(
        string='Timbrado',
        copy=False,
        help='En factura/nota de crédito de venta se completa automáticamente desde el diario. '
             'En factura/nota de crédito de proveedor se carga manualmente.',
    )
    l10n_py_nro_documento = fields.Char(
        string='Nro. Documento',
        size=15,
        copy=False,
        help='En factura/nota de crédito de venta se propone automáticamente en base al último '
             'número utilizado para el diario (formato 001-001-0000001). '
             'En factura/nota de crédito de proveedor se carga manualmente.',
    )
    local_py_tipo_fiscal_id = fields.Many2one(
        'local_py.tipo_fiscal',
        string='Tipo Fiscal',
        copy=False,
        help='En factura/nota de crédito de venta se completa automáticamente desde el diario. '
             'En factura/nota de crédito de proveedor se selecciona manualmente.',
    )
    # Campo auxiliar de solo lectura, usado en el reporte Libro Ventas.
    l10n_py_partner_vat = fields.Char(
        string='RUT del cliente',
        related='partner_id.vat',
        store=False,
    )

    l10n_py_imputacion_tributaria_ids = fields.Many2many(
        'local_py.imputacion_tributaria',
        string='Imputación Tributaria',
        help='A qué obligación(es) tributaria(s) se imputa este comprobante '
             '(IVA, IRE, IRP-RSP). "No Imputa" no puede combinarse con las '
             'otras opciones.',
    )

    # El campo nativo reversed_entry_id es readonly=True a nivel de modelo
    # (Odoo lo llena automáticamente solo desde el asistente "Añadir Nota de
    # Crédito"). Se libera acá para que, cuando la Nota de Crédito se cree
    # directamente desde cero (sin ese asistente), el usuario pueda
    # completarlo a mano — ver _check_l10n_py_comprobante_asociado más abajo,
    # que lo exige antes de poder confirmar.
    reversed_entry_id = fields.Many2one(readonly=False)

    l10n_py_nro_documento_asociado = fields.Char(
        string='Nro. Documento Comprobante Asociado',
        related='reversed_entry_id.l10n_py_nro_documento',
        readonly=True,
        store=False,
    )

    @api.onchange('l10n_py_imputacion_tributaria_ids')
    def _onchange_l10n_py_imputacion_tributaria_ids(self):
        no_imputa = self.env.ref('local_py.imputacion_no_imputa', raise_if_not_found=False)
        if not no_imputa:
            return
        for move in self:
            current = move.l10n_py_imputacion_tributaria_ids
            previous = move._origin.l10n_py_imputacion_tributaria_ids
            added = current - previous
            if no_imputa in added:
                move.l10n_py_imputacion_tributaria_ids = current.filtered(lambda t: t.id == no_imputa.id)
            elif no_imputa in current and (current - no_imputa):
                move.l10n_py_imputacion_tributaria_ids = current - no_imputa

    @api.constrains('l10n_py_imputacion_tributaria_ids')
    def _check_l10n_py_imputacion_tributaria_exclusiva(self):
        no_imputa = self.env.ref('local_py.imputacion_no_imputa', raise_if_not_found=False)
        if not no_imputa:
            return
        for move in self:
            tags = move.l10n_py_imputacion_tributaria_ids
            if no_imputa in tags and len(tags) > 1:
                raise exceptions.ValidationError(
                    '"No Imputa" no puede combinarse con IVA, IRE o IRP-RSP en la misma operación.'
                )

    # ------------------------------------------------------------------
    # Comprobante asociado: toda Nota de Crédito (cliente o proveedor) debe
    # estar asociada a una factura. Si se creó con el asistente de Odoo, ya
    # queda asociada automáticamente (reversed_entry_id); si se creó desde
    # cero, se exige completarla a mano antes de confirmar.
    # ------------------------------------------------------------------
    @api.constrains('reversed_entry_id', 'move_type', 'state')
    def _check_l10n_py_comprobante_asociado(self):
        for move in self:
            if move.move_type in REFUND_MOVE_TYPES and move.state == 'posted' and not move.reversed_entry_id:
                raise exceptions.ValidationError(
                    'No se puede confirmar la nota de crédito sin indicar el Comprobante Asociado '
                    '(la factura de origen).'
                )

    # ------------------------------------------------------------------
    # Campos con signo para los reportes Libro Ventas / Libro Compras.
    # Las notas de crédito se muestran en negativo para que resten en los
    # totales del reporte. Son de uso exclusivo para dichos reportes: no
    # afectan los importes reales de la factura/nota de crédito.
    # ------------------------------------------------------------------
    l10n_py_amount_untaxed_signed = fields.Monetary(
        string='Importe sin impuesto',
        compute='_compute_l10n_py_amounts_signed',
        currency_field='currency_id',
        store=True,
        help='Importe sin impuesto para los reportes Libro Ventas/Libro Compras. '
             'En notas de crédito se muestra en negativo, solo a efectos de '
             'visualización y totalización en dichos reportes.',
    )
    l10n_py_amount_total_signed = fields.Monetary(
        string='Importe Total',
        compute='_compute_l10n_py_amounts_signed',
        currency_field='currency_id',
        store=True,
        help='Importe total para los reportes Libro Ventas/Libro Compras. '
             'En notas de crédito se muestra en negativo, solo a efectos de '
             'visualización y totalización en dichos reportes.',
    )

    @api.depends('amount_untaxed', 'amount_total', 'move_type')
    def _compute_l10n_py_amounts_signed(self):
        for move in self:
            sign = -1 if move.move_type in REFUND_MOVE_TYPES else 1
            move.l10n_py_amount_untaxed_signed = sign * move.amount_untaxed
            move.l10n_py_amount_total_signed = sign * move.amount_total

    # ------------------------------------------------------------------
    # Numeración secuencial del Nro. Documento (solo lado venta)
    # ------------------------------------------------------------------
    @staticmethod
    def _increment_l10n_py_nro_documento(value):
        """Incrementa en 1 solo la última sección (7 dígitos) del Nro. Documento,
        manteniendo intactas las dos primeras secciones (establecimiento y punto)."""
        if not value:
            return value
        match = NRO_DOCUMENTO_SEQ_PATTERN.match(value)
        if not match:
            return value
        prefix, seq = match.groups()
        next_seq = int(seq) + 1
        return '%s%07d' % (prefix, next_seq)

    def _get_next_l10n_py_nro_documento(self, journal, move_type):
        """Busca la última factura/nota de crédito de venta ya utilizada para el
        mismo diario y tipo de operación, y propone el siguiente número
        correlativo. Si todavía no hay ninguna, usa el valor configurado en el
        diario como punto de partida."""
        last_move = self.search([
            ('journal_id', '=', journal.id),
            ('move_type', '=', move_type),
            ('l10n_py_nro_documento', '!=', False),
        ], order='id desc', limit=1)
        if last_move:
            return self._increment_l10n_py_nro_documento(last_move.l10n_py_nro_documento)
        return journal.l10n_py_nro_documento

    @api.model
    def _get_suitable_journal_ids(self, move_type, company=False):
        """Restringe los diarios ofrecidos en el campo Diario de la factura,
        además del filtro estándar de Odoo por tipo (venta/compra):
          - Factura de cliente: solo diarios de venta con Tipo Fiscal
            'Factura', 'Factura Electronica' o 'Nota de Debito' (la Nota de
            Débito de cliente usa la misma pantalla de Factura).
          - Nota de crédito de cliente: solo diarios de venta con Tipo Fiscal
            'Nota de Credito'.
        No se toca el comportamiento para compras (el usuario elige el Tipo
        Fiscal manualmente en la factura de proveedor, no en el diario)."""
        journals = super()._get_suitable_journal_ids(move_type, company)
        if move_type == 'out_invoice':
            journals = journals.filtered(
                lambda j: j.local_py_tipo_fiscal_id.name in ('Factura', 'Factura Electronica', 'Nota de Debito')
            )
        elif move_type == 'out_refund':
            journals = journals.filtered(
                lambda j: j.local_py_tipo_fiscal_id.name == 'Nota de Credito'
            )
        return journals

    @api.onchange('journal_id')
    def _onchange_journal_id_l10n_py(self):
        # El autocompletado solo aplica al lado de venta (Timbrado, Nro.
        # Documento y Tipo Fiscal se toman del diario). En factura/nota de
        # crédito de proveedor, el usuario carga los tres valores manualmente.
        for move in self:
            if move.journal_id and move.move_type in SALE_MOVE_TYPES:
                move.l10n_py_timbrado = move.journal_id.l10n_py_timbrado
                move.l10n_py_nro_documento = move._get_next_l10n_py_nro_documento(
                    move.journal_id, move.move_type
                )
                move.local_py_tipo_fiscal_id = move.journal_id.local_py_tipo_fiscal_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            journal_id = vals.get('journal_id')
            move_type = vals.get('move_type')
            if journal_id and move_type in SALE_MOVE_TYPES:
                journal = self.env['account.journal'].browse(journal_id)
                vals.setdefault('l10n_py_timbrado', journal.l10n_py_timbrado)
                vals.setdefault('local_py_tipo_fiscal_id', journal.local_py_tipo_fiscal_id.id)
                if not vals.get('l10n_py_nro_documento'):
                    vals['l10n_py_nro_documento'] = self._get_next_l10n_py_nro_documento(
                        journal, move_type
                    )
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Obligatoriedad de Timbrado, Nro. Documento y Tipo Fiscal al confirmar
    # (facturas y notas de crédito, clientes y proveedores). Al igual que el
    # resto de las validaciones de este módulo, se exige recién al pasar a
    # 'posted', no al guardar en borrador, para no trabar la carga incremental
    # del comprobante.
    # ------------------------------------------------------------------
    @api.constrains('l10n_py_timbrado', 'l10n_py_nro_documento', 'local_py_tipo_fiscal_id', 'move_type', 'state')
    def _check_l10n_py_required_fiscal_fields(self):
        for move in self:
            if move.move_type in REQUIRED_FISCAL_MOVE_TYPES and move.state == 'posted':
                missing = []
                if not move.l10n_py_timbrado:
                    missing.append('Timbrado')
                if not move.l10n_py_nro_documento:
                    missing.append('Nro. Documento')
                if not move.local_py_tipo_fiscal_id:
                    missing.append('Tipo Fiscal')
                if missing:
                    raise exceptions.ValidationError(
                        'No se puede confirmar el comprobante sin completar: %s.'
                        % ', '.join(missing)
                    )

    # ------------------------------------------------------------------
    # Validaciones de formato (aplican a venta y a proveedor)
    # ------------------------------------------------------------------
    @api.constrains('l10n_py_timbrado')
    def _check_l10n_py_timbrado(self):
        for move in self:
            if move.l10n_py_timbrado and move.l10n_py_timbrado < 0:
                raise exceptions.ValidationError(
                    'El campo Timbrado no admite valores negativos.'
                )
            if move.l10n_py_timbrado and move.l10n_py_timbrado > TIMBRADO_MAX:
                raise exceptions.ValidationError(
                    'El campo Timbrado admite un máximo de 8 dígitos.'
                )

    @api.constrains('l10n_py_nro_documento')
    def _check_l10n_py_nro_documento(self):
        for move in self:
            if move.l10n_py_nro_documento and not NRO_DOCUMENTO_PATTERN.match(move.l10n_py_nro_documento):
                raise exceptions.ValidationError(
                    'El campo Nro. Documento solo admite números y el carácter "-".'
                )

    # ------------------------------------------------------------------
    # Unicidad - lado venta: por Nro. Documento, separado por move_type.
    # Al igual que en proveedor, solo se valida al CONFIRMAR (state='posted'),
    # no al guardar en borrador.
    # ------------------------------------------------------------------
    @api.constrains('l10n_py_nro_documento', 'move_type', 'state')
    def _check_l10n_py_nro_documento_unique_sale(self):
        for move in self:
            if (
                move.move_type in SALE_MOVE_TYPES
                and move.state == 'posted'
                and move.l10n_py_nro_documento
            ):
                domain = [
                    ('id', '!=', move.id),
                    ('l10n_py_nro_documento', '=', move.l10n_py_nro_documento),
                    ('move_type', '=', move.move_type),
                    ('state', '=', 'posted'),
                    ('company_id', '=', move.company_id.id),
                ]
                if self.search_count(domain):
                    label = 'factura de venta' if move.move_type == 'out_invoice' else 'nota de crédito de venta'
                    raise exceptions.ValidationError(
                        'Ya existe otra %s confirmada con el mismo Nro. Documento: %s'
                        % (label, move.l10n_py_nro_documento)
                    )

    # ------------------------------------------------------------------
    # Unicidad - lado proveedor: por proveedor + Timbrado + Nro. Documento,
    # solo entre facturas/notas de crédito CONFIRMADAS, separado por move_type
    # ------------------------------------------------------------------
    @api.constrains('l10n_py_timbrado', 'l10n_py_nro_documento', 'move_type', 'state', 'partner_id')
    def _check_l10n_py_duplicate_purchase(self):
        for move in self:
            if (
                move.move_type in PURCHASE_MOVE_TYPES
                and move.state == 'posted'
                and move.partner_id
                and move.l10n_py_timbrado
                and move.l10n_py_nro_documento
            ):
                domain = [
                    ('id', '!=', move.id),
                    ('move_type', '=', move.move_type),
                    ('state', '=', 'posted'),
                    ('partner_id', '=', move.partner_id.id),
                    ('l10n_py_timbrado', '=', move.l10n_py_timbrado),
                    ('l10n_py_nro_documento', '=', move.l10n_py_nro_documento),
                    ('company_id', '=', move.company_id.id),
                ]
                if self.search_count(domain):
                    label = 'factura de proveedor' if move.move_type == 'in_invoice' else 'nota de crédito de proveedor'
                    raise exceptions.ValidationError(
                        'Ya existe otra %s confirmada con el mismo proveedor, Timbrado y Nro. Documento.'
                        % label
                    )

    # ------------------------------------------------------------------
    # Validación de vencimiento del timbrado (lado venta)
    # ------------------------------------------------------------------
    @api.constrains('invoice_date', 'journal_id')
    def _check_l10n_py_venc_timbrado(self):
        for move in self:
            if (
                move.move_type in SALE_MOVE_TYPES
                and move.invoice_date
                and move.journal_id.l10n_py_venc_timbrado
                and move.invoice_date > move.journal_id.l10n_py_venc_timbrado
            ):
                raise exceptions.ValidationError(
                    'La fecha del documento supera la fecha de vencimiento del timbrado'
                )
