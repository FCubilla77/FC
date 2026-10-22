# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    tllr_fc_puede_tercerizarse = fields.Boolean(
        string="Puede tercerizarse",
        help="El servicio puede encargarse a un proveedor externo desde la OT.")
