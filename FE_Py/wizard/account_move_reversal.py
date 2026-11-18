# -*- coding: utf-8 -*-
from odoo import api, models


class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    @api.depends('move_ids')
    def _compute_available_journal_ids(self):
        """Odoo restringe el diario ofrecido acá; se amplía a los que tengan Tipo
        Fiscal == 'Nota de Credito' (la física, por nombre exacto) — sin
        contemplar 'Nota de Credito Electronica', que no existía cuando se
        escribió ese filtro. Se agrega acá, sin tocar el archivo de
        el Tipo de Documento Electrónico propio, para que el wizard nativo también
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
                    ('fe_py_tipo_documento_id.codigo', '=', '5'),
                ])
                record.available_journal_ids |= extra
