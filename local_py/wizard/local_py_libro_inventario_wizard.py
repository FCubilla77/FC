# -*- coding: utf-8 -*-

from odoo import api, fields, models


class LocalPyLibroInventarioWizard(models.TransientModel):
    _name = 'local_py.libro_inventario.wizard'
    _description = 'Asistente Libro Inventario de Cuentas'

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company,
    )
    fecha = fields.Date(string='Fecha', required=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        res.setdefault('fecha', fields.Date.context_today(self))
        return res

    def _get_config(self):
        return self.env['local_py.configuracion_localizacion'].search(
            [('company_id', '=', self.company_id.id)], limit=1
        )

    def action_ver_reporte(self):
        self.ensure_one()
        builder = self.env['local_py.libro_report.builder']
        config = self._get_config()
        rows = builder._build_inventario_rows(self.company_id, self.fecha, config)
        paginas = builder._paginar_simple(rows)
        render_context = {
            'company': self.company_id,
            'fecha_desde': self.fecha.replace(month=1, day=1),
            'fecha_hasta': self.fecha,
            'paginas': paginas,
            'pagina_inicial': 1,
            'total_paginas_libro': len(paginas) or 1,
            'rubrica': self.env['local_py.rubrica'],
        }
        report_action = self.env.ref('local_py.action_report_libro_inventario_html')
        html_content, _ = report_action.with_context(
            local_py_libro_render_data=render_context
        )._render_qweb_html(report_action.report_name, [self.company_id.id])

        import base64
        data_uri = 'data:text/html;base64,%s' % base64.b64encode(html_content).decode()
        return {
            'type': 'ir.actions.act_url',
            'url': data_uri,
            'target': 'new',
        }

    def action_descargar_pdf(self):
        self.ensure_one()
        builder = self.env['local_py.libro_report.builder']
        config = self._get_config()
        fecha_desde = self.fecha.replace(month=1, day=1)
        generacion = builder._generar_oficial(
            'inventario', self.company_id, fecha_desde, self.fecha, config=config,
        )
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/local_py.rubrica.generacion/%s/pdf_file/%s?download=true'
                   % (generacion.id, generacion.pdf_filename),
            'target': 'self',
        }
