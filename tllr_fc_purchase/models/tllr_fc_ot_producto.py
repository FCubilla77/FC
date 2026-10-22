# -*- coding: utf-8 -*-
from odoo import fields, models


class TllrFcOtProducto(models.Model):
    _inherit = 'tllr_fc.ot.producto'

    origen_compra_id = fields.Many2one(
        'purchase.order', string="Compra directa", readonly=True, copy=False,
        ondelete='set null', help="Compra directa de la que proviene el repuesto.")
