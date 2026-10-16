# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import UserError


class TllrFcWizardConfirmarAdvertencia(models.TransientModel):
    """Confirmación de advertencias no bloqueantes.

    Ejecuta la acción destino con la bandera `tllr_fc_advertencia_ok`.
    """
    _name = 'tllr_fc.wizard.confirmar_advertencia'
    _description = "Confirmación de advertencia"

    res_model = fields.Char(string="Modelo", required=True)
    res_id = fields.Integer(string="Registro", required=True)
    accion = fields.Char(string="Acción", required=True)
    mensaje = fields.Text(string="Advertencia", readonly=True)

    def action_continuar(self):
        self.ensure_one()
        if not self.res_model.startswith('tllr_fc.') or not self.accion.startswith('action_'):
            raise UserError("La acción solicitada no es válida.")
        registro = self.env[self.res_model].browse(self.res_id).exists()
        if not registro:
            raise UserError("El registro ya no existe.")
        banderas = {
            clave: valor for clave, valor in self.env.context.items()
            if clave.startswith('tllr_fc_')
        }
        banderas['tllr_fc_advertencia_ok'] = True
        return getattr(registro.with_context(**banderas), self.accion)()
