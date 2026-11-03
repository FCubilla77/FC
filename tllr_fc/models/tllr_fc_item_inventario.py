# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .tllr_fc_licencia import tllr_fc_licencia_verificar
from .utils import escapar_ilike


class TllrFcItemInventario(models.Model):
    _name = 'tllr_fc.item_inventario'
    _description = "Ítem de inventario del vehículo"
    _order = 'name'
    _check_company_auto = True

    name = fields.Char(string="Nombre", required=True)
    active = fields.Boolean(string="Activo", default=True)
    # Vacío = compartido por todas las compañías (datos iniciales del módulo).
    company_id = fields.Many2one(
        'res.company', string="Compañía", default=lambda self: self.env.company,
        help="Si se deja vacío, el ítem se comparte entre todas las compañías.")

    @api.model_create_multi
    def create(self, vals_list):
        Company = self.env['res.company']
        for vals in vals_list:
            tllr_fc_licencia_verificar(
                self.env, Company.browse(vals['company_id']) if vals.get('company_id') else None)
        return super().create(vals_list)

    @api.constrains('name', 'company_id')
    def _check_nombre_unico(self):
        for item in self:
            repetido = self.with_context(active_test=False).search_count([
                ('id', '!=', item.id),
                ('company_id', '=', item.company_id.id),
                ('name', '=ilike', escapar_ilike((item.name or '').strip())),
            ])
            if repetido:
                raise ValidationError(
                    "Ya existe el ítem de inventario «%s»." % item.name)
