# -*- coding: utf-8 -*-
from odoo import fields, models


class TllrFcOtServicio(models.Model):
    """Servicio de la OT.

    En la Fase 2 solo guarda los servicios solicitados en la recepción, como
    referencia. La planificación, los precios y el estado de cada servicio se
    agregan en la Fase 3.
    """
    _name = 'tllr_fc.ot.servicio'
    _description = "Servicio de la orden de trabajo"
    _order = 'id'

    ot_id = fields.Many2one(
        'tllr_fc.ot', string="OT", required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one(
        'product.product', string="Servicio", required=True,
        domain="[('type', '=', 'service')]", ondelete='restrict')
    descripcion = fields.Char(string="Observación")
    cantidad = fields.Float(string="Cantidad", default=1.0)
    company_id = fields.Many2one(
        'res.company', string="Compañía", related='ot_id.company_id',
        store=True, index=True)
