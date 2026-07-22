# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCity(models.Model):
    _inherit = 'res.city'

    code = fields.Integer(string='Código')
    district_id = fields.Many2one(
        'res.district', string='Distrito', domain="[('state_id', '=', state_id)]",
    )
