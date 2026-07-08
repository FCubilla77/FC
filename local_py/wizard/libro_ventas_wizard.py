# -*- coding: utf-8 -*-

from odoo import models, fields, api


class L10nPyLibroVentasWizard(models.TransientModel):
    _name = 'l10n_py.libro_ventas.wizard'
    _description = 'Asistente Libro Ventas'

    date_from = fields.Date(string='Fecha desde', required=True)
    date_to = fields.Date(string='Fecha hasta', required=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        res.setdefault('date_from', today.replace(day=1))
        res.setdefault('date_to', today)
        return res

    def action_view_report(self):
        self.ensure_one()
        return {
            'name': 'Libro Ventas',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list',
            'views': [(self.env.ref('local_py.view_move_list_libro_ventas').id, 'list')],
            'domain': [
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', self.date_from),
                ('invoice_date', '<=', self.date_to),
            ],
            'context': {'group_by': ['l10n_py_tipo_fiscal_id']},
        }
