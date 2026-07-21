# -*- coding: utf-8 -*-

from odoo import models, api


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list):
        """El contacto (res.partner) que Odoo crea automáticamente junto con
        un nuevo Usuario no debe exigir 'Empresa relacionada'. Se marca vía
        contexto para que res.partner.create() lo detecte."""
        return super(
            ResUsers,
            self.with_context(l10n_py_partner_from_user_or_employee=True),
        ).create(vals_list)
