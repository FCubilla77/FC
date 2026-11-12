# -*- coding: utf-8 -*-
import base64

from odoo import _, fields, models
from odoo.exceptions import UserError


class L10nPyPlantillaWizard(models.TransientModel):
    _name = 'l10n_py.plantilla.wizard'
    _description = 'Cargar y validar la plantilla Excel del plan de cuentas'

    company_id = fields.Many2one('res.company', string='Compañía', required=True,
                                 default=lambda self: self.env.company)
    archivo = fields.Binary(string='Archivo Excel (.xlsx)')
    nombre_archivo = fields.Char()
    resultado = fields.Text(string='Resultado', readonly=True)
    estado = fields.Selection([
        ('error', 'Con errores'), ('validada', 'Validada, lista para cargar'),
    ], readonly=True)

    def _accion_abrir(self):
        return {
            'type': 'ir.actions.act_window', 'name': _('Plantilla del plan de cuentas (Excel)'),
            'res_model': self._name, 'res_id': self.id, 'view_mode': 'form', 'target': 'new',
        }

    def action_validar(self):
        """Valida y guarda el archivo.

        Sin errores: cierra la ventana y confirma con un aviso que la plantilla quedó
        guardada. Con errores: la ventana queda abierta con el detalle (y dice que la
        plantilla NO se guardó como válida), para poder corregir el Excel y volver a subirlo."""
        self.ensure_one()
        if not self.archivo:
            raise UserError(_("Seleccione el archivo Excel (.xlsx) de la plantilla."))
        plantilla = self.env['l10n_py.plantilla']._validar_y_guardar(
            self.company_id, self.nombre_archivo, base64.b64decode(self.archivo))
        if plantilla.state == 'error':
            self.write({'resultado': plantilla.log, 'estado': plantilla.state})
            return self._accion_abrir()
        mensaje = _(
            "La plantilla «%(archivo)s» se validó y quedó guardada (%(avisos)s avisos). "
            "Ahora seleccione el paquete «Paraguay» en Ajustes > Facturación > "
            "Localización Fiscal para cargar el plan.",
            archivo=plantilla.nombre_archivo or '', avisos=plantilla.cantidad_avisos)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _("Plantilla validada y guardada"), 'message': mensaje,
                'type': 'success', 'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
