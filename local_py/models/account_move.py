# -*- coding: utf-8 -*-
import re

from odoo import models, fields, api, exceptions

TIMBRADO_MAX = 999999999
NRO_DOCUMENTO_PATTERN = re.compile(r'^[0-9-]*$')


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_py_timbrado = fields.Integer(
        string='Timbrado',
        help='Se completa automáticamente con el valor del diario. Puede ajustarse si es necesario.',
    )
    l10n_py_nro_documento = fields.Char(
        string='Nro. Documento',
        size=15,
        help='Se completa automáticamente con el valor del diario. Puede ajustarse si es necesario.',
    )

    @api.onchange('journal_id')
    def _onchange_journal_id_l10n_py(self):
        for move in self:
            if move.journal_id:
                move.l10n_py_timbrado = move.journal_id.l10n_py_timbrado
                move.l10n_py_nro_documento = move.journal_id.l10n_py_nro_documento

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            journal_id = vals.get('journal_id')
            if journal_id:
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
