# -*- coding: utf-8 -*-
import re

from odoo import models, fields, api, exceptions

TIMBRADO_MAX = 999999999
NRO_DOCUMENTO_PATTERN = re.compile(r'^[0-9-]*$')

# Tipos de movimiento de venta: factura de cliente y nota de crédito de cliente
SALE_MOVE_TYPES = ('out_invoice', 'out_refund')


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_py_timbrado = fields.Integer(
        string='Timbrado',
        help='Se completa automáticamente con el valor del diario. Puede ajustarse si es necesario. '
             'Aplica únicamente a factura de venta y nota de crédito de venta.',
    )
    l10n_py_nro_documento = fields.Char(
        string='Nro. Documento',
        size=15,
        help='Se completa automáticamente con el valor del diario. Puede ajustarse si es necesario. '
             'Aplica únicamente a factura de venta y nota de crédito de venta.',
    )

    @api.onchange('journal_id')
    def _onchange_journal_id_l10n_py(self):
        for move in self:
            if move.journal_id and move.move_type in SALE_MOVE_TYPES:
                move.l10n_py_timbrado = move.journal_id.l10n_py_timbrado
                move.l10n_py_nro_documento = move.journal_id.l10n_py_nro_documento

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            journal_id = vals.get('journal_id')
            move_type = vals.get('move_type')
            if journal_id and move_type in SALE_MOVE_TYPES:
                journal = self.env['account.journal'].browse(journal_id)
                vals.setdefault('l10n_py_timbrado', journal.l10n_py_timbrado)
                vals.setdefault('l10n_py_nro_documento', journal.l10n_py_nro_documento)
        return super().create(vals_list)

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

    @api.constrains('l10n_py_nro_documento', 'move_type', 'state')
    def _check_l10n_py_nro_documento_unique(self):
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
