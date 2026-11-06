# -*- coding: utf-8 -*-
from odoo import models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _fe_py_recepcion_cubre(self, lineas):
        """True si cada línea de la recepción tiene en esta orden una línea propia
        (distinta) del mismo producto."""
        self.ensure_one()
        usadas = self.env['purchase.order.line']
        for linea in lineas:
            candidata = self.order_line.filtered(
                lambda pl: not pl.display_type and pl.product_id == linea.producto_id
                and pl not in usadas)[:1]
            if not candidata:
                return False
            usadas |= candidata
        return bool(lineas)
