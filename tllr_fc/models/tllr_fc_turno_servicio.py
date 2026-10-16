# -*- coding: utf-8 -*-
from odoo import fields, models


class TllrFcTurnoServicio(models.Model):
    _name = 'tllr_fc.turno.servicio'
    _description = "Servicio solicitado en el turno"
    _order = 'id'

    turno_id = fields.Many2one(
        'tllr_fc.turno', string="Turno", required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one(
        'product.product', string="Servicio", required=True,
        domain="[('type', '=', 'service')]", ondelete='restrict')
    observacion = fields.Char(string="Observación")
    company_id = fields.Many2one(
        'res.company', string="Compañía", related='turno_id.company_id',
        store=True, index=True)
