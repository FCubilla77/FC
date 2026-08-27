# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.local_py_libro_report import fmt_pyg, fmt_moneda


class LocalPyReporteReciboWizard(models.TransientModel):
    _name = 'local_py.reporte_recibo.wizard'
    _description = 'Asistente Reporte de Recibo'

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company,
    )
    fecha_desde = fields.Date(string='Fecha desde', required=True)
    fecha_hasta = fields.Date(string='Fecha hasta', required=True)
    currency_ids = fields.Many2many('res.currency', string='Moneda', help='Vacío = todas.')
    partner_ids = fields.Many2many('res.partner', string='Cliente', help='Vacío = todos.')
    filtro_borrador = fields.Boolean(string='Borrador', default=True)
    filtro_en_proceso = fields.Boolean(string='En Proceso', default=True)
    filtro_confirmado = fields.Boolean(string='Confirmado', default=True)
    filtro_anulado = fields.Boolean(string='Anulado', default=True)
    incluir_anulados = fields.Boolean(
        string='Incluir Recibos Anulados', default=True,
        help='Interruptor general: si está destildado, los Recibos Anulados nunca '
             'aparecen, sin importar lo tildado en Estados. Aparecen solo a efectos de '
             'control numérico de la secuencia, sin sumar valores a ningún total.',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        res.setdefault('fecha_desde', today.replace(day=1))
        res.setdefault('fecha_hasta', today)
        return res

    def _estados_seleccionados(self):
        self.ensure_one()
        mapa = [
            ('borrador', self.filtro_borrador),
            ('en_proceso', self.filtro_en_proceso),
            ('confirmado', self.filtro_confirmado),
            ('anulado', self.filtro_anulado),
        ]
        estados = [estado for estado, activo in mapa if activo]
        if not estados:
            raise UserError('Seleccione al menos un Estado para poder generar el Reporte.')
        return estados

    def _armar_render_context(self):
        self.ensure_one()
        builder = self.env['local_py.libro_report.builder']
        rows, resumen = builder._build_reporte_recibo_rows(
            self.company_id, self.fecha_desde, self.fecha_hasta, self.currency_ids, self.partner_ids,
            self.incluir_anulados, self._estados_seleccionados(),
        )
        return {
            'company': self.company_id,
            'fecha_desde': self.fecha_desde,
            'fecha_hasta': self.fecha_hasta,
            'rows': rows,
            'resumen': resumen,
            'fmt_pyg': fmt_pyg,
            'fmt_moneda': fmt_moneda,
        }

    def action_ver_reporte(self):
        self.ensure_one()
        render_context = self._armar_render_context()
        report_action = self.env.ref('local_py.action_report_recibo_listado')
        html_content, _ = report_action.with_context(
            local_py_libro_render_data=render_context
        )._render_qweb_html(report_action.report_name, [self.company_id.id])

        import base64
        attachment = self.env['ir.attachment'].create({
            'name': 'Informe de Recibos (vista de control).html',
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

    def action_descargar_pdf(self):
        self.ensure_one()
        render_context = self._armar_render_context()
        report_action = self.env.ref('local_py.action_report_recibo_listado')
        pdf_content, _ = report_action.with_context(
            local_py_libro_render_data=render_context
        )._render_qweb_pdf(report_action.report_name, [self.company_id.id])

        import base64
        attachment = self.env['ir.attachment'].create({
            'name': 'Informe_de_Recibos_%s_%s.pdf' % (
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
