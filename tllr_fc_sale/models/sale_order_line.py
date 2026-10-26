# -*- coding: utf-8 -*-
from odoo import models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _action_launch_stock_rule(self, *, previous_product_uom_qty=False):
        """Los presupuestos y pedidos del taller no generan entregas.

        El stock de repuestos e insumos lo mueve la OT al consumir; una entrega de
        Ventas descontaría el mismo stock por segunda vez y no se actualizaría con
        lo ejecutado.
        """
        lineas = self.filtered(lambda l: not l.order_id._tllr_fc_es_del_taller())
        if not lineas:
            return True
        return super(SaleOrderLine, lineas)._action_launch_stock_rule(
            previous_product_uom_qty=previous_product_uom_qty)
