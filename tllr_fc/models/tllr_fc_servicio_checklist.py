# -*- coding: utf-8 -*-
from odoo import fields, models


class TllrFcServicioChecklist(models.Model):
    _name = 'tllr_fc.servicio.checklist'
    _description = "Lista de verificación del servicio"
    _order = 'sequence, id'

    product_tmpl_id = fields.Many2one(
        'product.template', string="Servicio", required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string="Secuencia", default=10)
    name = fields.Char(string="Punto a verificar", required=True)
