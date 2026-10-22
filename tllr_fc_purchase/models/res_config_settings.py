# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    tllr_fc_usar_compras = fields.Boolean(
        related='company_id.tllr_fc_usar_compras', readonly=False)
