# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCountry(models.Model):
    _inherit = 'res.country'

    local_py_code_alpha3 = fields.Char(string='Código ISO-3166 Alpha-3')
