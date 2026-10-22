# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    tllr_fc_usar_ventas = fields.Boolean(
        string="Integración con Ventas", default=True,
        help="Activo: las OT de cliente generan presupuesto y pedido de venta y se facturan desde "
             "el pedido. Desactivado: se factura directo desde Contabilidad (las OT que ya "
             "tienen presupuesto siguen facturándose desde su pedido).")
