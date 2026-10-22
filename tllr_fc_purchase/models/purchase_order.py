# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    tllr_fc_ot_id = fields.Many2one(
        'tllr_fc.ot', string="OT de taller", copy=False, readonly=True,
        index='btree_not_null', ondelete='restrict', tracking=True,
        help="Orden de trabajo de referencia. Una compra se vincula a una sola OT.")
    tllr_fc_tipo = fields.Selection([
        ('directa', "Compra directa de repuestos"),
        ('tercerizado', "Servicio tercerizado"),
    ], string="Tipo (taller)", copy=False, readonly=True)

    @api.constrains('tllr_fc_ot_id', 'tllr_fc_tipo')
    def _check_tllr_fc_tipo(self):
        for compra in self:
            if compra.tllr_fc_ot_id and not compra.tllr_fc_tipo:
                raise ValidationError("Indicá el tipo de compra del taller (directa o tercerizado).")


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    tllr_fc_ot_servicio_id = fields.Many2one(
        'tllr_fc.ot.servicio', string="Servicio tercerizado (OT)", copy=False,
        index='btree_not_null', ondelete='set null')
