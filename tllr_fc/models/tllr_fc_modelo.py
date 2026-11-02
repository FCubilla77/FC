# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .utils import escapar_ilike


class TllrFcModelo(models.Model):
    _name = 'tllr_fc.modelo'
    _description = "Modelo de vehículo"
    _order = 'marca_id, name'
    _check_company_auto = True

    name = fields.Char(string="Nombre", required=True)
    marca_id = fields.Many2one(
        'tllr_fc.marca', string="Marca", required=True,
        ondelete='restrict', check_company=True)
    active = fields.Boolean(string="Activo", default=True)
    company_id = fields.Many2one(
        'res.company', string="Compañía", required=True,
        default=lambda self: self.env.company)

    @api.constrains('name', 'marca_id', 'company_id')
    def _check_nombre_unico(self):
        for modelo in self:
            repetido = self.with_context(active_test=False).search_count([
                ('id', '!=', modelo.id),
                ('company_id', '=', modelo.company_id.id),
                ('marca_id', '=', modelo.marca_id.id),
                ('name', '=ilike', escapar_ilike((modelo.name or '').strip())),
            ])
            if repetido:
                raise ValidationError(
                    "Ya existe el modelo «%s» para la marca %s." % (
                        modelo.name, modelo.marca_id.display_name))
