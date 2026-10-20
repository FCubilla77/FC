# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    tllr_fc_ot_id = fields.Many2one(
        'tllr_fc.ot', string="OT de taller", copy=False, readonly=True,
        index='btree_not_null', ondelete='restrict',
        help="Orden de trabajo de taller que originó este comprobante.")
