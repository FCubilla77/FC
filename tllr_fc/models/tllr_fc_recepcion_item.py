# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TllrFcRecepcionItem(models.Model):
    _name = 'tllr_fc.recepcion.item'
    _description = "Ítem del inventario del vehículo en la recepción"
    _order = 'id'

    recepcion_id = fields.Many2one(
        'tllr_fc.recepcion', string="Recepción", required=True,
        ondelete='cascade', index=True)
    item_id = fields.Many2one(
        'tllr_fc.item_inventario', string="Ítem del catálogo", ondelete='restrict')
    name = fields.Char(string="Descripción", required=True)
    # Sin valor por defecto: el recepcionista confirma cada ítem.
    presente = fields.Selection(
        [('si', "Sí"), ('no', "No")], string="Presente", copy=False)
    observacion = fields.Char(string="Observación")
    company_id = fields.Many2one(
        'res.company', string="Compañía", related='recepcion_id.company_id',
        store=True, index=True)

    @api.onchange('item_id')
    def _onchange_item_id(self):
        if self.item_id:
            self.name = self.item_id.name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('item_id') and not vals.get('name'):
                vals['name'] = self.env['tllr_fc.item_inventario'].browse(vals['item_id']).name
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
