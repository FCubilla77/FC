# -*- coding: utf-8 -*-
import re

from odoo import models, fields, api, exceptions

# Máximo permitido para un campo de 8 dígitos (99.999.999)
TIMBRADO_MAX = 99999999

# Solo se permiten números y el carácter '-'
NRO_DOCUMENTO_PATTERN = re.compile(r'^[0-9-]*$')


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    l10n_py_timbrado = fields.Integer(
        string='Timbrado',
        help='Número de timbrado asignado por la SET (hasta 8 dígitos, sin decimales, sin negativos). '
             'Aplica únicamente a diarios de venta.',
    )
    l10n_py_nro_documento = fields.Char(
        string='Nro. Documento',
        size=15,
        help='Número de documento/resolución. Solo admite números y el carácter "-" (máximo 15 caracteres). '
             'Aplica únicamente a diarios de venta.',
    )
    l10n_py_venc_timbrado = fields.Date(
        string='Venc. Timbrado',
        help='Fecha de vencimiento del timbrado. Las facturas de venta con fecha posterior '
             'a esta no podrán guardarse. Aplica únicamente a diarios de venta.',
    )
    local_py_tipo_fiscal_id = fields.Many2one(
        'local_py.tipo_fiscal',
        string='Tipo Fiscal',
        help='Tipo de comprobante fiscal asociado a este diario. Aplica a diarios de venta y de compra.',
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
                    'El campo Timbrado admite un máximo de 8 dígitos.'
                )

    @api.constrains('l10n_py_nro_documento')
    def _check_l10n_py_nro_documento(self):
        for journal in self:
            if journal.l10n_py_nro_documento and not NRO_DOCUMENTO_PATTERN.match(journal.l10n_py_nro_documento):
                raise exceptions.ValidationError(
                    'El campo Nro. Documento solo admite números y el carácter "-".'
                )

    @api.constrains('l10n_py_timbrado', 'l10n_py_nro_documento', 'l10n_py_venc_timbrado', 'type')
    def _check_l10n_py_only_sale_journal(self):
        for journal in self:
            if journal.type != 'sale' and (
                journal.l10n_py_timbrado
                or journal.l10n_py_nro_documento
                or journal.l10n_py_venc_timbrado
            ):
                raise exceptions.ValidationError(
                    'Los campos Timbrado, Nro. Documento y Venc. Timbrado solo aplican a diarios de venta.'
                )

    @api.constrains('local_py_tipo_fiscal_id', 'type')
    def _check_local_py_tipo_fiscal_journal_type(self):
        for journal in self:
            if journal.type not in ('sale', 'purchase') and journal.local_py_tipo_fiscal_id:
                raise exceptions.ValidationError(
                    'El campo Tipo Fiscal solo aplica a diarios de venta y de compra.'
                )

    @api.constrains('l10n_py_timbrado', 'l10n_py_nro_documento', 'local_py_tipo_fiscal_id', 'type')
    def _check_l10n_py_unique_timbrado_per_tipo_fiscal(self):
        """No pueden existir dos diarios de venta con el mismo Tipo Fiscal que
        compartan el mismo Timbrado y Nro. Documento. Al comparar siempre
        contra el mismo Tipo Fiscal, la validación queda naturalmente separada
        por cada tipo (Factura, Factura Electronica, Nota de Debito,
        Nota de Credito, Autofactura, o cualquier otro que se agregue)."""
        for journal in self:
            if (
                journal.type == 'sale'
                and journal.local_py_tipo_fiscal_id
                and journal.l10n_py_timbrado
                and journal.l10n_py_nro_documento
            ):
                domain = [
                    ('id', '!=', journal.id),
                    ('type', '=', 'sale'),
                    ('local_py_tipo_fiscal_id', '=', journal.local_py_tipo_fiscal_id.id),
                    ('l10n_py_timbrado', '=', journal.l10n_py_timbrado),
                    ('l10n_py_nro_documento', '=', journal.l10n_py_nro_documento),
                    ('company_id', '=', journal.company_id.id),
                ]
                if self.search_count(domain):
                    raise exceptions.ValidationError(
                        'Ya existe otro diario de venta con el mismo Tipo Fiscal (%s), '
                        'Timbrado y Nro. Documento.' % journal.local_py_tipo_fiscal_id.name
                    )
