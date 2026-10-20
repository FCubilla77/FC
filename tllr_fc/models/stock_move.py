# -*- coding: utf-8 -*-
from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    tllr_fc_ot_id = fields.Many2one(
        'tllr_fc.ot', string="Orden de trabajo (taller)", index='btree_not_null',
        copy=False, ondelete='restrict')
    tllr_fc_ot_producto_id = fields.Many2one(
        'tllr_fc.ot.producto', string="Línea de la OT (taller)", index='btree_not_null',
        copy=False, ondelete='cascade')
