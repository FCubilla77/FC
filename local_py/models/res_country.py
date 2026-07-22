# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCountry(models.Model):
    _inherit = 'res.country'

    code_alpha3 = fields.Char(string='Código ISO-3166 Alpha-3')
