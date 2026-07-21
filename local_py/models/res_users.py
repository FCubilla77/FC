# -*- coding: utf-8 -*-

from odoo import models, api


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list):
        """El contacto (res.partner) asociado a un Usuario nuevo no debe
        exigir 'Empresa relacionada'. Odoo crea ese contacto de forma
        implícita (antes de que un context flag en este create() llegue a
        aplicarse), por eso lo creamos nosotros mismos de antemano, ya
        marcado, y se lo entregamos armado a super().create() vía
        'partner_id'. Si el vals ya trae un partner_id (por ejemplo, un
        alta programática que reutiliza un contacto existente), no se toca
        nada."""
        Partner = self.env['res.partner']
        for vals in vals_list:
            if not vals.get('partner_id'):
                partner = Partner.with_context(
                    l10n_py_partner_from_user_or_employee=True,
                ).create({
                    'name': vals.get('name') or vals.get('login') or 'Usuario',
                    'email': vals.get('email'),
                    'company_id': vals.get('company_id', False),
                })
                vals['partner_id'] = partner.id
        return super().create(vals_list)
