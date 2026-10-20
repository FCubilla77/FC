# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import AccessError, UserError

GRUPOS = {
    'supervisor': ('tllr_fc.group_supervisor', "supervisor de taller"),
    'administrador': ('tllr_fc.group_administrador', "administrador de taller"),
}


class TllrFcWizardExcepcion(models.TransientModel):
    """Autorización de una excepción por un supervisor (o administrador).

    Valida el grupo de quien autoriza, exige el motivo, lo deja registrado en
    el chatter del registro y ejecuta la acción destino con la bandera
    `tllr_fc_excepcion` en el contexto.
    """
    _name = 'tllr_fc.wizard.excepcion'
    _description = "Autorización de excepción"

    res_model = fields.Char(string="Modelo", required=True)
    res_id = fields.Integer(string="Registro", required=True)
    accion = fields.Char(string="Acción", required=True)
    grupo_requerido = fields.Selection(
        [('supervisor', "Supervisor"), ('administrador', "Administrador")],
        string="Autoriza", required=True, default='supervisor')
    descripcion = fields.Text(string="Qué se autoriza", readonly=True)
    motivo = fields.Text(string="Motivo", required=True)

    def action_autorizar(self):
        self.ensure_one()
        xml_id, nombre = GRUPOS[self.grupo_requerido]
        if not self.env.user.has_group(xml_id):
            raise AccessError(
                "Esta excepción debe autorizarla un %s. Ingresá con un usuario con ese "
                "rol para continuar." % nombre)
        if not self.res_model.startswith('tllr_fc.') or not self.accion.startswith('action_'):
            raise UserError("La acción solicitada no es válida.")
        registro = self.env[self.res_model].browse(self.res_id).exists()
        if not registro:
            raise UserError("El registro ya no existe.")
        if not (self.motivo or '').strip():
            raise UserError("Indicá el motivo de la excepción.")
        # El registro puede no tener chatter (p. ej. una línea): se deja en la OT.
        hilo = registro if hasattr(registro, 'message_post') else getattr(registro, 'ot_id', False)
        if hilo:
            hilo.message_post(body="Excepción autorizada por %s.<br/>%s<br/>Motivo: %s" % (
                self.env.user.name, self.descripcion or '', self.motivo))
        banderas = {
            clave: valor for clave, valor in self.env.context.items()
            if clave.startswith('tllr_fc_')
        }
        banderas['tllr_fc_excepcion'] = True
        banderas['tllr_fc_motivo'] = self.motivo
        return getattr(registro.with_context(**banderas), self.accion)()
