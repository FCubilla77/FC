# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TllrFcRecepcionServicio(models.Model):
    _name = 'tllr_fc.recepcion.servicio'
    _description = "Servicio solicitado en la recepción"
    _order = 'id'

    recepcion_id = fields.Many2one(
        'tllr_fc.recepcion', string="Recepción", required=True,
        ondelete='cascade', index=True)
    product_id = fields.Many2one(
        'product.product', string="Servicio", required=True,
        domain="[('type', '=', 'service')]", ondelete='restrict')
    observacion = fields.Char(string="Observación")
    company_id = fields.Many2one(
        'res.company', string="Compañía", related='recepcion_id.company_id',
        store=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        recepciones = self.env['tllr_fc.recepcion'].browse(
            [v['recepcion_id'] for v in vals_list if v.get('recepcion_id')])
        recepciones._tllr_fc_asegurar_editable()
        return super().create(vals_list)

    def write(self, vals):
        self.recepcion_id._tllr_fc_asegurar_editable()
        return super().write(vals)

    def unlink(self):
        self.recepcion_id._tllr_fc_asegurar_editable()
        return super().unlink()
