# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    tllr_fc_ot_id = fields.Many2one(
        'tllr_fc.ot', string="Orden de trabajo (taller)", index='btree_not_null',
        copy=False, ondelete='restrict')
    tllr_fc_puesto_line_id = fields.Many2one(
        'tllr_fc.ot.puesto', string="Puesto de la OT", copy=False, ondelete='set null')
    tllr_fc_sentido = fields.Selection(
        [('ida', "Al puesto"), ('vuelta', "Devolución al almacén principal")],
        string="Traslado del taller", copy=False,
        help="Traslado interno generado por una orden de trabajo.")
