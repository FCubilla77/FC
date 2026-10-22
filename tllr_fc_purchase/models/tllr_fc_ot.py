# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class TllrFcOt(models.Model):
    _inherit = 'tllr_fc.ot'

    tllr_fc_usar_compras = fields.Boolean(related='company_id.tllr_fc_usar_compras')
    compra_ids = fields.One2many(
        'purchase.order', 'tllr_fc_ot_id', string="Órdenes de compra", readonly=True)
    compra_count = fields.Integer(string="Compras", compute='_compute_compra_count')
    tercerizados_resumen = fields.Char(
        string="Tercerizados", compute='_compute_tercerizados_resumen')

    @api.depends('compra_ids')
    def _compute_compra_count(self):
        datos = {
            ot.id: n for ot, n in self.env['purchase.order'].sudo()._read_group(
                [('tllr_fc_ot_id', 'in', self.ids)], ['tllr_fc_ot_id'], ['__count'])}
        for ot in self:
            ot.compra_count = datos.get(ot.id, 0)

    @api.depends('servicio_ids.tercerizado', 'servicio_ids.proveedor_id')
    def _compute_tercerizados_resumen(self):
        for ot in self:
            proveedores = ot.servicio_ids.filtered('tercerizado').proveedor_id
            ot.tercerizados_resumen = ', '.join(proveedores.mapped('name'))

    def _tllr_fc_compras_activas(self):
        self.ensure_one()
        return bool(self.company_id.tllr_fc_usar_compras)

    def action_compra_directa(self):
        """Abre el asistente de compra directa (supervisor) o de solicitud (usuario)."""
        self.ensure_one()
        if not self._tllr_fc_compras_activas():
            raise UserError("La integración con Compras está desactivada en Ajustes.")
        if self.state not in ('espera', 'proceso'):
            raise UserError("La compra directa se hace con la OT en espera o en proceso.")
        return {
            'type': 'ir.actions.act_window', 'name': "Compra directa",
            'res_model': 'tllr_fc.wizard.compra_directa', 'view_mode': 'form', 'target': 'new',
            'context': {'default_ot_id': self.id},
        }

    def action_ver_compras(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': "Compras de la OT",
            'res_model': 'purchase.order', 'view_mode': 'list,form',
            'domain': [('tllr_fc_ot_id', '=', self.id)],
        }
