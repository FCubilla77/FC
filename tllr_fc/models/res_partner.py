# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    tllr_fc_descuento = fields.Float(
        string="Descuento en taller (%)", default=0.0,
        help="Porcentaje de descuento por defecto en servicios, repuestos, insumos "
             "facturables y accesorios de las órdenes de trabajo (0 a 100).")
    tllr_fc_vehiculo_ids = fields.One2many(
        'tllr_fc.vehiculo', 'partner_id', string="Vehículos")
    tllr_fc_vehiculo_count = fields.Integer(
        string="Cantidad de vehículos", compute='_compute_tllr_fc_vehiculo_count')

    @api.constrains('tllr_fc_descuento')
    def _check_tllr_fc_descuento(self):
        for partner in self:
            if not 0 <= partner.tllr_fc_descuento <= 100:
                raise ValidationError("El descuento en taller debe estar entre 0 y 100.")

    @api.depends('tllr_fc_vehiculo_ids')
    def _compute_tllr_fc_vehiculo_count(self):
        datos = self.env['tllr_fc.vehiculo'].sudo()._read_group(
            [('partner_id', 'in', self.ids)], ['partner_id'], ['__count'])
        conteo = {partner.id: cantidad for partner, cantidad in datos}
        for partner in self:
            partner.tllr_fc_vehiculo_count = conteo.get(partner.id, 0)

    def action_ver_vehiculos_tllr_fc(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Vehículos",
            'res_model': 'tllr_fc.vehiculo',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }
