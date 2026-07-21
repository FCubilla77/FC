# -*- coding: utf-8 -*-
from odoo import models, api


class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    @api.depends('move_ids')
    def _compute_available_journal_ids(self):
        super()._compute_available_journal_ids()
        for record in self:
            if not record.move_ids:
                continue
            move_types = set(record.move_ids.mapped('move_type'))
            if move_types == {'out_invoice'}:
                # Nota de crédito de cliente: solo diarios de venta con
                # Tipo Fiscal 'Nota de Credito'.
                record.available_journal_ids = record.available_journal_ids.filtered(
                    lambda j: j.type == 'sale' and j.local_py_tipo_fiscal_id.name == 'Nota de Credito'
                )
            elif move_types == {'in_invoice'}:
                # Reembolso (nota de crédito) de proveedor: solo diarios de
                # compra con Tipo Fiscal 'Nota de Credito'.
                record.available_journal_ids = record.available_journal_ids.filtered(
                    lambda j: j.type == 'purchase' and j.local_py_tipo_fiscal_id.name == 'Nota de Credito'
                )
