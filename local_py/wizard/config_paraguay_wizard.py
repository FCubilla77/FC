# -*- coding: utf-8 -*-

from odoo import models

from odoo.addons.local_py.hooks import configure_paraguay


class L10nPyConfigParaguayWizard(models.TransientModel):
    _name = 'l10n_py.config_paraguay.wizard'
    _description = 'Restablecer configuración predeterminada Paraguay'

    def action_confirm(self):
        self.ensure_one()
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
