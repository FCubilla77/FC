# -*- coding: utf-8 -*-

from odoo import api, fields, models


class LocalPyStockValorizadoWizard(models.TransientModel):
    _name = 'local_py.stock_valorizado.wizard'
    _description = 'Asistente Movimiento de Stock Valorizado'

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company,
    )
    fecha_desde = fields.Date(string='Fecha desde', required=True)
    fecha_hasta = fields.Date(string='Fecha hasta', required=True)
    product_ids = fields.Many2many(
        'product.product', string='Productos',
        help='Dejar vacío para incluir todos los productos.',
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
        rows = builder._build_stock_valorizado_rows(
            self.company_id, self.fecha_desde, self.fecha_hasta, self.product_ids,
        )
        paginas = builder._paginar_simple(rows)
        render_context = {
            'company': self.company_id,
            'fecha_desde': self.fecha_desde,
            'fecha_hasta': self.fecha_hasta,
            'paginas': paginas,
            'pagina_inicial': 1,
            'total_paginas_libro': len(paginas) or 1,
            'rubrica': self.env['local_py.rubrica'],
        }
        report_action = self.env.ref('local_py.action_report_stock_valorizado_html')
        html_content, _ = report_action.with_context(
            local_py_libro_render_data=render_context
        )._render_qweb_html(report_action.report_name, [self.company_id.id])

        import base64
        attachment = self.env['ir.attachment'].create({
            'name': 'Movimiento de Stock Valorizado (vista de control).html',
            'type': 'binary',
            'datas': base64.b64encode(html_content),
            'mimetype': 'text/html',
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=false' % attachment.id,
            'target': 'new',
        }
