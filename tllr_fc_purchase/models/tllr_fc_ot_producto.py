# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.tools import float_compare


class TllrFcOtProducto(models.Model):
    _inherit = 'tllr_fc.ot.producto'

    origen_compra_id = fields.Many2one(
        'purchase.order', string="Compra directa", readonly=True, copy=False,
        ondelete='set null', help="Compra directa de la que proviene el repuesto.")

    def _tllr_fc_sugerencia_compra(self):
        """Con Compras activo indica la compra directa y las compras pendientes de recibir."""
        self.ensure_one()
        if not self.ot_id._tllr_fc_compras_activas():
            return super()._tllr_fc_sugerencia_compra()
        lineas = self.env['purchase.order.line'].sudo().search([
            ('product_id', '=', self.product_id.id),
            ('order_id.state', '=', 'purchase'),
            ('company_id', '=', self.ot_id.company_id.id),
        ])
        redondeo = self.product_id.uom_id.rounding or 0.001
        pendientes = lineas.filtered(lambda l: float_compare(
            l.product_qty, l.qty_received, precision_rounding=redondeo) > 0)
        texto = "Realizá una compra directa desde la OT"
        if pendientes:
            detalle = ", ".join(
                "%s (%s)" % (l.order_id.name, round(l.product_qty - l.qty_received, 3))
                for l in pendientes[:5])
            return texto + " o recepcioná las compras pendientes: %s." % detalle
        return texto + " o recepcioná las compras que estén pendientes."
