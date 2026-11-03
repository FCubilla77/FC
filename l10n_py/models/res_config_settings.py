# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_py_licencia_uuid = fields.Char(
        related='company_id.l10n_py_licencia_uuid', readonly=True)
    l10n_py_licencia_codigo = fields.Text(
        related='company_id.l10n_py_licencia_codigo', readonly=False)
    l10n_py_licencia_cliente = fields.Char(
        related='company_id.l10n_py_licencia_cliente', readonly=True)
    l10n_py_licencia_vencimiento = fields.Date(
        related='company_id.l10n_py_licencia_vencimiento', readonly=True)
    l10n_py_licencia_estado = fields.Selection(
        related='company_id.l10n_py_licencia_estado', readonly=True)
