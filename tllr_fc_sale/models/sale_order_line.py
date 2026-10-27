# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    tllr_fc_origen = fields.Selection(
        [('manual', "Manual"), ('ot', "Desde la OT")], string="Origen", default='manual',
        required=True, copy=False,
        help="«Desde la OT»: línea que genera y actualiza la orden de trabajo. "
             "«Manual»: línea cargada a mano, que la actualización desde la OT no modifica.")

    def _tllr_fc_es_almacenable_manual(self):
        self.ensure_one()
        return (self.tllr_fc_origen != 'ot' and not self.display_type
                and self.product_id.type == 'consu' and self.product_id.is_storable)

    def _tllr_fc_verificar_almacenable_manual(self):
        """En un presupuesto de una OT los productos almacenables se cargan desde la OT."""
        if self.env.context.get('tllr_fc_desde_ot'):
            return
        for linea in self:
            if linea.order_id.tllr_fc_ot_id and linea._tllr_fc_es_almacenable_manual():
                raise UserError(
                    "Este presupuesto proviene de la orden de trabajo %s. Los productos "
                    "almacenables (%s) se cargan desde la orden de trabajo."
                    % (linea.order_id.tllr_fc_ot_id.name, linea.product_id.display_name))

    @api.model_create_multi
    def create(self, vals_list):
        lineas = super().create(vals_list)
        lineas._tllr_fc_verificar_almacenable_manual()
        return lineas

    def write(self, vals):
        resultado = super().write(vals)
        if {'product_id', 'product_uom_qty', 'order_id'} & set(vals):
            self._tllr_fc_verificar_almacenable_manual()
        return resultado

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
