# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .tllr_fc_licencia import tllr_fc_licencia_verificar
from .utils import escapar_ilike


class TllrFcTipoVehiculo(models.Model):
    _name = 'tllr_fc.tipo_vehiculo'
    _description = "Tipo de vehículo"
    _order = 'name'
    _check_company_auto = True

    name = fields.Char(string="Nombre", required=True)
    active = fields.Boolean(string="Activo", default=True)
    company_id = fields.Many2one(
        'res.company', string="Compañía", required=True,
        default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        Company = self.env['res.company']
        for vals in vals_list:
            tllr_fc_licencia_verificar(
                self.env, Company.browse(vals['company_id']) if vals.get('company_id') else None)
        return super().create(vals_list)

    @api.constrains('name', 'company_id')
    def _check_nombre_unico(self):
        for tipo in self:
            repetido = self.with_context(active_test=False).search_count([
                ('id', '!=', tipo.id),
                ('company_id', '=', tipo.company_id.id),
                ('name', '=ilike', escapar_ilike((tipo.name or '').strip())),
            ])
            if repetido:
                raise ValidationError(
                    "Ya existe el tipo de vehículo «%s» en esta compañía." % tipo.name)
