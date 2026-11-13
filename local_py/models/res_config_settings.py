# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    """Expone la licencia del producto y la configuración por plantilla en Ajustes.

    Los campos viven en `res.company`; acá se exponen como `related` para poder
    dibujarlos en los bloques de Ajustes. Esta pantalla queda siempre
    disponible, con o sin licencia válida."""
    _inherit = 'res.config.settings'

    local_py_licencia_uuid = fields.Char(
        related='company_id.local_py_licencia_uuid', readonly=True)
    local_py_licencia_codigo = fields.Text(
        related='company_id.local_py_licencia_codigo', readonly=False)
    local_py_licencia_cliente = fields.Char(
        related='company_id.local_py_licencia_cliente', readonly=True)
    local_py_licencia_vencimiento = fields.Date(
        related='company_id.local_py_licencia_vencimiento', readonly=True)
    local_py_licencia_estado = fields.Selection(
        related='company_id.local_py_licencia_estado', readonly=True)

    # -- Configuración por plantilla Excel -----------------------------
    local_py_plantilla_estado = fields.Selection(
        related='company_id.local_py_plantilla_id.state')
    local_py_plantilla_archivo = fields.Char(
        related='company_id.local_py_plantilla_id.nombre_archivo')
    local_py_plantilla_log = fields.Text(
        related='company_id.local_py_plantilla_id.log')

    def action_local_py_descargar_plantilla(self):
        """Genera el Excel de configuración (con valores de ejemplo) y lo descarga."""
        self.ensure_one()
        nombre = 'Plantilla_Configuracion_local_py.xlsx'
        contenido = self.env['local_py.plantilla']._contenido_plantilla_ejemplo(self.company_id)
        Adjunto = self.env['ir.attachment'].sudo()
        Adjunto.search([('name', '=', nombre), ('res_model', '=', 'res.company'),
                        ('res_id', '=', self.company_id.id)]).unlink()
        adjunto = Adjunto.create({
            'name': nombre, 'raw': contenido, 'res_model': 'res.company',
            'res_id': self.company_id.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})
        return {'type': 'ir.actions.act_url', 'target': 'self',
                'url': '/web/content/%s?download=true' % adjunto.id}

    def action_local_py_abrir_carga_plantilla(self):
        self.ensure_one()
        asistente = self.env['local_py.plantilla.wizard'].create(
            {'company_id': self.company_id.id})
        return asistente._accion_abrir()

    def action_local_py_aplicar_plantilla(self):
        """Aplica la configuración de la plantilla validada de esta empresa."""
        self.ensure_one()
        plantilla = self.company_id.local_py_plantilla_id
        if not plantilla:
            raise UserError(_("Todavía no se cargó ninguna plantilla de configuración."))
        informe = plantilla.aplicar()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _("Configuración aplicada"),
                'message': _("Se aplicó la configuración de la plantilla:\n%s", informe),
                'type': 'success', 'sticky': True,
            },
        }
