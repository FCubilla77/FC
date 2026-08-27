# -*- coding: utf-8 -*-
from odoo import api, models


class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    @api.depends('move_ids')
    def _compute_available_journal_ids(self):
        """local_py restringe el diario ofrecido acá a los que tengan Tipo
        Fiscal == 'Nota de Credito' (la física, por nombre exacto) — sin
        contemplar 'Nota de Credito Electronica', que no existía cuando se
        escribió ese filtro. Se agrega acá, sin tocar el archivo de
        local_py, para que el wizard nativo de Nota de Crédito también
        ofrezca los diarios electrónicos."""
        super()._compute_available_journal_ids()
        for record in self:
            if not record.move_ids:
                continue
            move_types = set(record.move_ids.mapped('move_type'))
            if move_types == {'out_invoice'}:
                extra = self.env['account.journal'].search([
                    ('type', '=', 'sale'),
                    ('company_id', 'in', record.move_ids.company_id.ids),
                    ('local_py_tipo_fiscal_id.name', '=', 'Nota de Credito Electronica'),
                ])
                record.available_journal_ids |= extra
