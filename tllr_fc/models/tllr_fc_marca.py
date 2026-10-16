# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .utils import escapar_ilike


class TllrFcMarca(models.Model):
    _name = 'tllr_fc.marca'
    _description = "Marca de vehículo"
    _order = 'name'
    _check_company_auto = True

    name = fields.Char(string="Nombre", required=True)
    active = fields.Boolean(string="Activo", default=True)
    company_id = fields.Many2one(
        'res.company', string="Compañía", required=True,
        default=lambda self: self.env.company)

    @api.constrains('name', 'company_id')
    def _check_nombre_unico(self):
        for marca in self:
            repetida = self.with_context(active_test=False).search_count([
                ('id', '!=', marca.id),
                ('company_id', '=', marca.company_id.id),
                ('name', '=ilike', escapar_ilike((marca.name or '').strip())),
            ])
            if repetida:
                raise ValidationError(
                    "Ya existe la marca «%s» en esta compañía." % marca.name)
