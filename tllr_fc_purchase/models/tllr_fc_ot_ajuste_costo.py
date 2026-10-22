# -*- coding: utf-8 -*-
from odoo import fields, models


class TllrFcOtAjusteCosto(models.Model):
    _inherit = 'tllr_fc.ot.ajuste_costo'

    origen_compra_id = fields.Many2one(
        'purchase.order', string="Compra de origen", readonly=True, copy=False,
        ondelete='set null', help="Compra cuya factura de proveedor tardía originó el ajuste.")
