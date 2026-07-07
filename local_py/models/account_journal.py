# -*- coding: utf-8 -*-
import re

from odoo import models, fields, api, exceptions

# Máximo permitido para un campo de 9 dígitos (999.999.999)
TIMBRADO_MAX = 999999999

# Solo se permiten números y el carácter '-'
NRO_DOCUMENTO_PATTERN = re.compile(r'^[0-9-]*$')


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    l10n_py_timbrado = fields.Integer(
        string='Timbrado',
        help='Número de timbrado asignado por la SET (hasta 9 dígitos, sin decimales, sin negativos). '
             'Aplica únicamente a diarios de venta.',
    )
    l10n_py_nro_documento = fields.Char(
        string='Nro. Documento',
        size=15,
        help='Número de documento/resolución. Solo admite números y el carácter "-" (máximo 15 caracteres). '
             'Aplica únicamente a diarios de venta.',
    )

    @api.constrains('l10n_py_timbrado')
    def _check_l10n_py_timbrado(self):
        for journal in self:
            if journal.l10n_py_timbrado and journal.l10n_py_timbrado < 0:
                raise exceptions.ValidationError(
                    'El campo Timbrado no admite valores negativos.'
                )
            if journal.l10n_py_timbrado and journal.l10n_py_timbrado > TIMBRADO_MAX:
                raise exceptions.ValidationError(
                    'El campo Timbrado admite un máximo de 9 dígitos.'
                )

    @api.constrains('l10n_py_nro_documento')
    def _check_l10n_py_nro_documento(self):
        for journal in self:
            if journal.l10n_py_nro_documento and not NRO_DOCUMENTO_PATTERN.match(journal.l10n_py_nro_documento):
                raise exceptions.ValidationError(
                    'El campo Nro. Documento solo admite números y el carácter "-".'
                )

    @api.constrains('l10n_py_timbrado', 'l10n_py_nro_documento', 'type')
    def _check_l10n_py_only_sale_journal(self):
        for journal in self:
            if journal.type != 'sale' and (journal.l10n_py_timbrado or journal.l10n_py_nro_documento):
                raise exceptions.ValidationError(
                    'Los campos Timbrado y Nro. Documento solo aplican a diarios de venta.'
                )
