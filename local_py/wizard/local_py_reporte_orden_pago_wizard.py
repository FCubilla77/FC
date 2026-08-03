# -*- coding: utf-8 -*-

from odoo import api, fields, models

from ..models.local_py_libro_report import fmt_pyg


class LocalPyReporteOrdenPagoWizard(models.TransientModel):
    _name = 'local_py.reporte_orden_pago.wizard'
    _description = 'Asistente Reporte de Orden de Pago'

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company,
    )
    fecha_desde = fields.Date(string='Fecha desde', required=True)
    fecha_hasta = fields.Date(string='Fecha hasta', required=True)
    currency_ids = fields.Many2many('res.currency', string='Moneda', help='Vacío = todas.')
    partner_ids = fields.Many2many('res.partner', string='Proveedor', help='Vacío = todos.')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        res.setdefault('fecha_desde', today.replace(day=1))
        res.setdefault('fecha_hasta', today)
        return res

    def action_ver_reporte(self):
        self.ensure_one()
        builder = self.env['local_py.libro_report.builder']
        rows, resumen = builder._build_reporte_orden_pago_rows(
            self.company_id, self.fecha_desde, self.fecha_hasta, self.currency_ids, self.partner_ids,
        )
        render_context = {
            'company': self.company_id,
            'fecha_desde': self.fecha_desde,
            'fecha_hasta': self.fecha_hasta,
            'rows': rows,
            'resumen': resumen,
            'fmt_pyg': fmt_pyg,
        }
        report_action = self.env.ref('local_py.action_report_orden_pago_listado')
        return report_action.with_context(local_py_libro_render_data=render_context).report_action(
            self.company_id, config=False,
        )
