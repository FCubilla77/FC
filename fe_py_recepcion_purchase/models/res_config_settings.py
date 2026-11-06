# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fe_py_recepcion_vincular_compras = fields.Boolean(
        related='company_id.fe_py_recepcion_vincular_compras', readonly=False)
