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

    tllr_fc_devolucion_de_id = fields.Many2one(
        'stock.move', string="Consumo devuelto (taller)", copy=False,
        index='btree_not_null', ondelete='set null',
        help="Consumo de una OT que esta devolución deshace.")

    def _action_done(self, cancel_backorder=False):
        movimientos = super()._action_done(cancel_backorder=cancel_backorder)
        lineas = movimientos.filtered('tllr_fc_traslado_producto_id').tllr_fc_traslado_producto_id
        if lineas and not self.env.context.get('tllr_fc_sin_sincronizar'):
            # Con el traslado validado, lo recibido en el puesto queda reservado para la OT.
            lineas.sudo()._tllr_fc_sincronizar_stock()
        return movimientos

    def _create_account_move(self):
        """El asiento de valoración de una OT queda identificado con su orden de trabajo."""
        asientos = super()._create_account_move()
        for asiento in asientos:
            movimientos = self.filtered(lambda m: m.account_move_id == asiento)
            ots = movimientos.mapped(lambda m: m.tllr_fc_ot_id or m.picking_id.tllr_fc_ot_id)
            if len(ots) == 1:
                es_traslado = all(m.picking_id.tllr_fc_ot_id for m in movimientos)
                asiento.sudo().write({
                    'tllr_fc_ot_id': ots.id,
                    'tllr_fc_tipo_asiento': 'traslado' if es_traslado else 'consumo',
                })
        return asientos
