# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.local_py_libro_report import fmt_pyg, fmt_moneda


class LocalPyReporteRetencionesWizard(models.TransientModel):
    _name = 'local_py.reporte_retenciones.wizard'
    _description = 'Asistente Reporte de Retenciones'

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company,
    )
    fecha_desde = fields.Date(string='Fecha desde', required=True)
    fecha_hasta = fields.Date(string='Fecha hasta', required=True)
    partner_ids = fields.Many2many('res.partner', string='Contacto', help='Vacío = todos.')

    incluir_emitidas = fields.Boolean(string='Retenciones Emitidas', default=True)
    filtro_emitida_pendiente = fields.Boolean(string='Pendiente', default=True)
    filtro_emitida_json_generado = fields.Boolean(string='JSON Generado', default=True)
    filtro_emitida_levantada = fields.Boolean(string='Levantada', default=True)
    filtro_emitida_anulada = fields.Boolean(string='Anulada', default=True)

    incluir_recibidas = fields.Boolean(string='Retenciones Recibidas', default=True)
    filtro_recibida_a_confirmar = fields.Boolean(string='A Confirmar', default=True)
    filtro_recibida_confirmada = fields.Boolean(string='Confirmada', default=True)
    filtro_recibida_anulada = fields.Boolean(string='Anulada', default=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        res.setdefault('fecha_desde', today.replace(day=1))
        res.setdefault('fecha_hasta', today)
        return res

    def _estados_emitida_seleccionados(self):
        self.ensure_one()
        mapa = [
            ('pendiente', self.filtro_emitida_pendiente),
            ('json_generado', self.filtro_emitida_json_generado),
            ('levantada', self.filtro_emitida_levantada),
            ('anulada', self.filtro_emitida_anulada),
        ]
        return [estado for estado, activo in mapa if activo]

    def _estados_recibida_seleccionados(self):
        self.ensure_one()
        mapa = [
            ('a_confirmar', self.filtro_recibida_a_confirmar),
            ('confirmada', self.filtro_recibida_confirmada),
            ('anulada', self.filtro_recibida_anulada),
        ]
        return [estado for estado, activo in mapa if activo]

    def _validar_filtros(self):
        self.ensure_one()
        if not self.incluir_emitidas and not self.incluir_recibidas:
            raise UserError('Tilde al menos "Retenciones Emitidas" o "Retenciones Recibidas".')
        if self.incluir_emitidas and not self._estados_emitida_seleccionados():
            raise UserError('Seleccione al menos un Estado de Retenciones Emitidas.')
        if self.incluir_recibidas and not self._estados_recibida_seleccionados():
            raise UserError('Seleccione al menos un Estado de Retenciones Recibidas.')

    def _armar_render_context(self):
        self.ensure_one()
        self._validar_filtros()
        builder = self.env['local_py.libro_report.builder']
        rows = builder._build_reporte_retenciones_rows(
            self.company_id, self.fecha_desde, self.fecha_hasta, self.partner_ids,
            self.incluir_emitidas, self._estados_emitida_seleccionados(),
            self.incluir_recibidas, self._estados_recibida_seleccionados(),
        )
        return {
            'company': self.company_id,
            'fecha_desde': self.fecha_desde,
            'fecha_hasta': self.fecha_hasta,
            'rows': rows,
            'fmt_pyg': fmt_pyg,
            'fmt_moneda': fmt_moneda,
        }

    def action_ver_reporte(self):
        self.ensure_one()
        render_context = self._armar_render_context()
        report_action = self.env.ref('local_py.action_report_retenciones_listado')
        html_content, _ = report_action.with_context(
            local_py_libro_render_data=render_context
        )._render_qweb_html(report_action.report_name, [self.company_id.id])

        import base64
        attachment = self.env['ir.attachment'].create({
            'name': 'Informe de Retenciones (vista de control).html',
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
        report_action = self.env.ref('local_py.action_report_retenciones_listado')
        pdf_content, _ = report_action.with_context(
            local_py_libro_render_data=render_context
        )._render_qweb_pdf(report_action.report_name, [self.company_id.id])

        import base64
        attachment = self.env['ir.attachment'].create({
            'name': 'Informe_de_Retenciones_%s_%s.pdf' % (
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
