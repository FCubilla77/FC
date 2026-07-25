# -*- coding: utf-8 -*-

from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    l10n_py_comentario = fields.Char(
        related='move_id.l10n_py_comentario', string='Comentario', store=False,
    )
    l10n_py_nro_asiento_libro = fields.Char(
        related='move_id.l10n_py_nro_asiento_libro', string='Nro. Asiento', store=False,
    )
    l10n_py_nro_fiscal = fields.Integer(
        related='move_id.l10n_py_nro_fiscal', string='Nro. Fiscal', store=False,
    )
