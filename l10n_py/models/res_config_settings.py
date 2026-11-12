# -*- coding: utf-8 -*-
import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_py_licencia_uuid = fields.Char(
        related='company_id.l10n_py_licencia_uuid', readonly=True)
    l10n_py_licencia_codigo = fields.Text(
        related='company_id.l10n_py_licencia_codigo', readonly=False)
    l10n_py_licencia_cliente = fields.Char(
        related='company_id.l10n_py_licencia_cliente', readonly=True)
    l10n_py_licencia_vencimiento = fields.Date(
        related='company_id.l10n_py_licencia_vencimiento', readonly=True)
    l10n_py_licencia_estado = fields.Selection(
        related='company_id.l10n_py_licencia_estado', readonly=True)

    l10n_py_cuenta_resultado_ejercicio_id = fields.Many2one(
        related='company_id.l10n_py_cuenta_resultado_ejercicio_id', readonly=False)

    l10n_py_modo_plan = fields.Selection(related='company_id.l10n_py_modo_plan', readonly=False)
    l10n_py_plan_cargado = fields.Boolean(compute='_compute_l10n_py_plan_cargado')
    l10n_py_plantilla_estado = fields.Selection(related='company_id.l10n_py_plantilla_id.state')
    l10n_py_plantilla_archivo = fields.Char(related='company_id.l10n_py_plantilla_id.nombre_archivo')
    l10n_py_plantilla_log = fields.Text(related='company_id.l10n_py_plantilla_id.log')

    @api.depends('company_id.chart_template')
    def _compute_l10n_py_plan_cargado(self):
        for settings in self:
            settings.l10n_py_plan_cargado = settings.company_id.chart_template == 'py'

    def action_l10n_py_descargar_plantilla(self):
        """Genera el Excel con el plan estándar como ejemplo y lo descarga."""
        self.ensure_one()
        nombre = 'Plantilla_Plan_de_Cuentas_Paraguay.xlsx'
        contenido = self.env['l10n_py.plantilla']._contenido_plantilla_estandar()
        Adjunto = self.env['ir.attachment'].sudo()
        Adjunto.search([('name', '=', nombre), ('res_model', '=', 'res.company'),
                        ('res_id', '=', self.company_id.id)]).unlink()
        adjunto = Adjunto.create({
            'name': nombre, 'raw': contenido, 'res_model': 'res.company',
            'res_id': self.company_id.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})
        return {'type': 'ir.actions.act_url', 'target': 'self',
                'url': '/web/content/%s?download=true' % adjunto.id}

    def action_l10n_py_abrir_carga_plantilla(self):
        self.ensure_one()
        asistente = self.env['l10n_py.plantilla.wizard'].create({'company_id': self.company_id.id})
        return asistente._accion_abrir()
