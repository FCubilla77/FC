# -*- coding: utf-8 -*-

from odoo import models

from odoo.addons.local_py.hooks import configure_paraguay
from odoo.addons.local_py.models.local_py_licencia import local_py_licencia_verificar


class LocalPyConfigParaguayWizard(models.TransientModel):
    _name = 'local_py.config_paraguay.wizard'
    _description = 'Restablecer configuración predeterminada Paraguay'

    def action_confirm(self):
        """El control de licencia va acá y no en el `create`: abrir el asistente
        crea un registro transitorio, así que bloquear la creación impediría
        incluso ver la ventana y el mensaje. La instalación del módulo no se ve
        afectada: el `post_init_hook` corre con el registro aún no listo, que es
        una de las exenciones."""
        self.ensure_one()
        local_py_licencia_verificar(self.env, self.env.company)
        configure_paraguay(self.env)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Configuración Paraguay',
                'message': 'La configuración predeterminada de Paraguay fue restablecida correctamente.',
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
