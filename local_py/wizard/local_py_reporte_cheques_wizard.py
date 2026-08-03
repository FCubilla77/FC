# -*- coding: utf-8 -*-

from odoo import api, fields, models

from ..models.local_py_libro_report import fmt_pyg


class LocalPyReporteChequesWizard(models.TransientModel):
    _name = 'local_py.reporte_cheques.wizard'
    _description = 'Asistente Reporte de Cheques Emitidos'

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company,
    )
    fecha_desde = fields.Date(string='Fecha desde', required=True)
    fecha_hasta = fields.Date(string='Fecha hasta', required=True)
    chequera_ids = fields.Many2many(
        'local_py.chequera', string='Chequera',
        domain="[('company_id', '=', company_id)]", help='Vacío = todas.',
    )

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
        rows = builder._build_reporte_cheques_rows(
            self.company_id, self.fecha_desde, self.fecha_hasta, self.chequera_ids,
        )
        render_context = {
            'company': self.company_id,
            'fecha_desde': self.fecha_desde,
            'fecha_hasta': self.fecha_hasta,
            'rows': rows,
            'chequera_ids': self.chequera_ids,
            'fmt_pyg': fmt_pyg,
        }
        report_action = self.env.ref('local_py.action_report_cheques_listado')
        pdf_content, _ = report_action.with_context(
            local_py_libro_render_data=render_context
        )._render_qweb_pdf(report_action.report_name, [self.company_id.id])

        import base64
        attachment = self.env['ir.attachment'].create({
            'name': 'Informe_Cheques_%s_%s.pdf' % (
                self.fecha_desde.strftime('%Y%m%d'), self.fecha_hasta.strftime('%Y%m%d'),
            ),
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'mimetype': 'application/pdf',
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }
