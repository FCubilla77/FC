# -*- coding: utf-8 -*-
from odoo import models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        resultado = super()._action_done()
        self._tllr_fc_reservar_compras_recibidas()
        return resultado

    def _tllr_fc_reservar_compras_recibidas(self):
        """Al recibir una compra de la OT, lo recibido se reserva a la OT (el resto queda libre)."""
        for picking in self.filtered(lambda p: p.state == 'done'):
            compra = picking.purchase_id.sudo()
            ot = compra.tllr_fc_ot_id
            if (not ot or compra.tllr_fc_tipo != 'directa'
                    or not ot.company_id.tllr_fc_usar_compras
                    or ot.state not in ('espera', 'proceso')):
                continue
            productos = picking.move_ids.filtered(lambda m: m.state == 'done').product_id
            lineas = ot.sudo().producto_ids.filtered(lambda l: l.product_id in productos)
            if lineas:
                lineas.with_context(tllr_fc_permitir_write=True)._tllr_fc_sincronizar_stock()
                ot.message_post(body="Compra %s recibida: se reservó a la OT lo recibido de %s." % (
                    compra.name, ', '.join(productos.mapped('display_name'))))
