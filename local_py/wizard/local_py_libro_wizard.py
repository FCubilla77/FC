# -*- coding: utf-8 -*-

from odoo import api, fields, models


class LocalPyLibroWizard(models.TransientModel):
    _name = 'local_py.libro.wizard'
    _description = 'Asistente Libro Diario / Libro Mayor'

    tipo_libro = fields.Selection(
        [('diario', 'Libro Diario'), ('mayor', 'Libro Mayor')],
        string='Libro', required=True,
    )
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company,
    )
    fecha_desde = fields.Date(string='Fecha desde', required=True)
    fecha_hasta = fields.Date(string='Fecha hasta', required=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        res.setdefault('fecha_desde', today.replace(day=1))
        res.setdefault('fecha_hasta', today)
        return res

    def action_ver_reporte(self):
        self.ensure_one()
        domain = [
            ('move_id.company_id', '=', self.company_id.id),
            ('move_id.state', '=', 'posted'),
            ('move_id.date', '>=', self.fecha_desde),
            ('move_id.date', '<=', self.fecha_hasta),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]
        if self.tipo_libro == 'diario':
            view_id = self.env.ref('local_py.view_move_line_list_libro_diario').id
            group_by = ['move_id']
            name = 'Libro Diario (vista de control)'
        else:
            view_id = self.env.ref('local_py.view_move_line_list_libro_mayor').id
            group_by = ['account_id']
            name = 'Libro Mayor (vista de control)'
        return {
            'name': name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.line',
            'view_mode': 'list',
            'views': [(view_id, 'list')],
            'domain': domain,
            'context': {'group_by': group_by},
        }

    def action_descargar_pdf(self):
        self.ensure_one()
        builder = self.env['local_py.libro_report.builder']
        generacion = builder._generar_oficial(
            self.tipo_libro, self.company_id, self.fecha_desde, self.fecha_hasta,
        )
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/local_py.rubrica.generacion/%s/pdf_file/%s?download=true'
                   % (generacion.id, generacion.pdf_filename),
            'target': 'self',
        }
