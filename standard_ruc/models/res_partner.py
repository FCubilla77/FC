# -*- coding: utf-8 -*-
from odoo import models, fields, exceptions, api
import re


class ResPartner(models.Model):
    _inherit = 'res.partner'

    obviar_validacion = fields.Boolean(string='Obviar validación de RUT', default=False)
    vat = fields.Char(string="RUC", index=True)

    def clear_vat(self, vat):
        allowed_characters = '1234567890-'
        if vat:
            for vat_character in vat:
                if vat_character not in allowed_characters:
                    vat = vat.replace(vat_character, '')
        return vat

    @api.depends('vat', 'obviar_validacion')
    def val_ruc(self):
        for this in self:
            ruc = this.clear_vat(this.vat)
            obviar_validacion_ruc = this.obviar_validacion
            if this.parent_id and this.parent_id.obviar_validacion:
                obviar_validacion_ruc = True
            if not obviar_validacion_ruc:
                if ruc:
                    pattern = "^[0-9]+-[0-9]$"
                    if re.match(pattern, ruc):
                        ruc_das = str(ruc).split("-")
                        ruc_dig = ruc_das[1]
                        ruc_proper_dig = str(this.digito_verificador(ruc))
                        if ruc_proper_dig != ruc_dig:
                            raise exceptions.ValidationError("El digito verificador debería de ser " + ruc_proper_dig)
                    else:
                        raise exceptions.ValidationError("Error de formato de RUT! (Ejemplo: 12345678-0)")
                    if this.vat != ruc:
                        this.vat = ruc

    def digito_verificador(self, ruc):
        ruc_asd = str(ruc).split("-")
        ruc_ci = ruc_asd[0]
        ruc_str = str(ruc_ci)[::-1]
        v_total = 0
        basemax = 11
        k = 2
        for i in range(0, len(ruc_str)):
            if k > basemax:
                k = 2
            v_total += int(ruc_str[i]) * k
            k += 1
            resto = v_total % basemax
        if resto > 1:
            return basemax - resto
        else:
            return 0

    @api.model_create_multi
    def create(self, vals_list):
        result = super(ResPartner, self).create(vals_list)
        result.val_ruc()
        return result

    def write(self, vals):
        result = super(ResPartner, self).write(vals)
        if vals.get('vat'):
            self.val_ruc()
        return result

    # @api.model
    # def name_search(self, name, args=None, operator='ilike', limit=100):
    #     result = super(ResPartner, self).name_search(name, args=args, operator=operator, limit=limit)
    #     if not result:
    #         result = self.env['res.partner'].search([('vat', 'ilike', name)])
    #         return result.name_get()
    #     else:
    #         return result