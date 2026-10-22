# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    tllr_fc_usar_compras = fields.Boolean(
        string="Integración con Compras", default=True,
        help="Activo: compra directa de repuestos y servicios tercerizados desde la OT. "
             "Desactivado: no se muestran ni funcionan. Las compras ya vinculadas no se modifican.")
