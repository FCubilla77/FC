# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCity(models.Model):
    _inherit = 'res.city'

    local_py_code = fields.Integer(string='Código')
    local_py_district_id = fields.Many2one(
        'local_py.district', string='Distrito', domain="[('state_id', '=', state_id)]",
    )
