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
        self.ensure_one()
        if not self.archivo:
            raise UserError(_("Seleccione el archivo Excel (.xlsx) de la plantilla."))
        plantilla = self.env['l10n_py.plantilla']._validar_y_guardar(
            self.company_id, self.nombre_archivo, base64.b64decode(self.archivo))
        self.write({'resultado': plantilla.log, 'estado': plantilla.state})
        return self._accion_abrir()
