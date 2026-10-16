# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TllrFcPersonal(models.Model):
    _name = 'tllr_fc.personal'
    _description = "Personal de taller"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'
    _check_company_auto = True

    codigo = fields.Char(
        string="Código", required=True, readonly=True, copy=False, default="Nuevo")
    name = fields.Char(string="Nombre", required=True, tracking=True)
    funcion_id = fields.Many2one(
        'tllr_fc.funcion', string="Función", required=True,
        ondelete='restrict', check_company=True, tracking=True)
    user_id = fields.Many2one(
        'res.users', string="Usuario",
        help="Permite que la persona opere desde su propio usuario (opcional).")
    company_id = fields.Many2one(
        'res.company', string="Compañía", required=True,
        default=lambda self: self.env.company)
    active = fields.Boolean(string="Activo", default=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('codigo') or vals['codigo'] == "Nuevo":
                compania = self.env['res.company'].browse(
                    vals.get('company_id') or self.env.company.id)
                vals['codigo'] = compania._tllr_fc_siguiente_codigo('tllr_fc.personal')
        return super().create(vals_list)
