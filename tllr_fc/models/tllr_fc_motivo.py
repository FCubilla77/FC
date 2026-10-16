# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .utils import escapar_ilike


class TllrFcMotivo(models.Model):
    _name = 'tllr_fc.motivo'
    _description = "Motivo (cancelación o detención)"
    _order = 'tipo, name'
    _check_company_auto = True

    name = fields.Char(string="Motivo", required=True)
    tipo = fields.Selection(
        [('cancelacion', "Cancelación"), ('detencion', "Detención")],
        string="Tipo", required=True, default='cancelacion')
    active = fields.Boolean(string="Activo", default=True)
    # Vacío = compartido por todas las compañías (datos iniciales del módulo).
    company_id = fields.Many2one(
        'res.company', string="Compañía", default=lambda self: self.env.company,
        help="Si se deja vacío, el motivo se comparte entre todas las compañías.")

    @api.constrains('name', 'tipo', 'company_id')
    def _check_nombre_unico(self):
        for motivo in self:
            repetido = self.with_context(active_test=False).search_count([
                ('id', '!=', motivo.id),
                ('company_id', '=', motivo.company_id.id),
                ('tipo', '=', motivo.tipo),
                ('name', '=ilike', escapar_ilike((motivo.name or '').strip())),
            ])
            if repetido:
                raise ValidationError(
                    "Ya existe el motivo «%s» de este tipo." % motivo.name)
