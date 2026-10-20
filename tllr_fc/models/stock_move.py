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
    tllr_fc_traslado_producto_id = fields.Many2one(
        'tllr_fc.ot.producto', string="Línea de la OT (traslado al puesto)",
        index='btree_not_null', copy=False, ondelete='set null')
    tllr_fc_sentido = fields.Selection(
        [('ida', "Al puesto"), ('vuelta', "Devolución al almacén principal")],
        string="Sentido del traslado (taller)", copy=False)

    def _action_done(self, cancel_backorder=False):
        movimientos = super()._action_done(cancel_backorder=cancel_backorder)
        lineas = movimientos.filtered('tllr_fc_traslado_producto_id').tllr_fc_traslado_producto_id
        if lineas and not self.env.context.get('tllr_fc_sin_sincronizar'):
            # Con el traslado validado, lo recibido en el puesto queda reservado para la OT.
            lineas.sudo()._tllr_fc_sincronizar_stock()
        return movimientos
