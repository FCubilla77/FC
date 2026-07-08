# -*- coding: utf-8 -*-
import re

from odoo import models, fields, api, exceptions

TIMBRADO_MAX = 999999999
NRO_DOCUMENTO_PATTERN = re.compile(r'^[0-9-]*$')

# Formato esperado del Nro. Documento: 001-001-0000001 (3 + 3 + 7 dígitos)
NRO_DOCUMENTO_SEQ_PATTERN = re.compile(r'^(\d{3}-\d{3}-)(\d{7})$')

# Tipos de movimiento de venta: factura de cliente y nota de crédito de cliente
SALE_MOVE_TYPES = ('out_invoice', 'out_refund')

# Tipos de movimiento de compra: factura de proveedor y nota de crédito de proveedor
PURCHASE_MOVE_TYPES = ('in_invoice', 'in_refund')


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_py_timbrado = fields.Integer(
        string='Timbrado',
        help='En factura/nota de crédito de venta se completa automáticamente desde el diario. '
             'En factura/nota de crédito de proveedor se carga manualmente.',
    )
    l10n_py_nro_documento = fields.Char(
        string='Nro. Documento',
        size=15,
        help='En factura/nota de crédito de venta se propone automáticamente en base al último '
             'número utilizado para el diario (formato 001-001-0000001). '
             'En factura/nota de crédito de proveedor se carga manualmente.',
    )
    l10n_py_tipo_fiscal_id = fields.Many2one(
        'l10n_py.tipo_fiscal',
        string='Tipo Fiscal',
        related='journal_id.l10n_py_tipo_fiscal_id',
        store=True,
        readonly=True,
        help='Tipo Fiscal configurado en el diario de esta factura/nota de crédito.',
    )

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

    @api.onchange('journal_id')
    def _onchange_journal_id_l10n_py(self):
        # El autocompletado solo aplica al lado de venta. En factura/nota de
        # crédito de proveedor, el usuario carga los valores manualmente.
        for move in self:
            if move.journal_id and move.move_type in SALE_MOVE_TYPES:
                move.l10n_py_timbrado = move.journal_id.l10n_py_timbrado
                move.l10n_py_nro_documento = move._get_next_l10n_py_nro_documento(
                    move.journal_id, move.move_type
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            journal_id = vals.get('journal_id')
            move_type = vals.get('move_type')
            if journal_id and move_type in SALE_MOVE_TYPES:
                journal = self.env['account.journal'].browse(journal_id)
                vals.setdefault('l10n_py_timbrado', journal.l10n_py_timbrado)
                if not vals.get('l10n_py_nro_documento'):
                    vals['l10n_py_nro_documento'] = self._get_next_l10n_py_nro_documento(
                        journal, move_type
                    )
        return super().create(vals_list)

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
                    'El campo Timbrado admite un máximo de 9 dígitos.'
                )

    @api.constrains('l10n_py_nro_documento')
    def _check_l10n_py_nro_documento(self):
        for move in self:
            if move.l10n_py_nro_documento and not NRO_DOCUMENTO_PATTERN.match(move.l10n_py_nro_documento):
                raise exceptions.ValidationError(
                    'El campo Nro. Documento solo admite números y el carácter "-".'
                )

    # ------------------------------------------------------------------
    # Unicidad - lado venta: por Nro. Documento, separado por move_type
    # ------------------------------------------------------------------
    @api.constrains('l10n_py_nro_documento', 'move_type', 'state')
    def _check_l10n_py_nro_documento_unique_sale(self):
        for move in self:
            if move.l10n_py_nro_documento and move.move_type in SALE_MOVE_TYPES:
                domain = [
                    ('id', '!=', move.id),
                    ('l10n_py_nro_documento', '=', move.l10n_py_nro_documento),
                    ('move_type', '=', move.move_type),
                    ('state', '!=', 'cancel'),
                    ('company_id', '=', move.company_id.id),
                ]
                if self.search_count(domain):
                    label = 'factura de venta' if move.move_type == 'out_invoice' else 'nota de crédito de venta'
                    raise exceptions.ValidationError(
                        'Ya existe otra %s con el mismo Nro. Documento: %s'
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
