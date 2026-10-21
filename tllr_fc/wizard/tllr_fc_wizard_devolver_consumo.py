# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class TllrFcWizardDevolverConsumo(models.TransientModel):
    """Devuelve a stock lo consumido por una línea de la OT (con motivo)."""
    _name = 'tllr_fc.wizard.devolver_consumo'
    _description = "Devolver consumo de la OT"

    producto_id = fields.Many2one(
        'tllr_fc.ot.producto', string="Línea", required=True, ondelete='cascade')
    consumido = fields.Float(
        string="Consumido", related='producto_id.cantidad_consumida', digits='Product Unit')
    cantidad = fields.Float(string="Cantidad a devolver", required=True, digits='Product Unit')
    motivo = fields.Text(string="Motivo", required=True)

    @api.model
    def default_get(self, campos):
        valores = super().default_get(campos)
        producto = self.env['tllr_fc.ot.producto'].browse(
            valores.get('producto_id') or self.env.context.get('default_producto_id'))
        if producto and 'cantidad' in campos:
            valores['cantidad'] = producto.cantidad_consumida
        return valores

    def action_devolver(self):
        self.ensure_one()
        if not self.env.user.has_group('tllr_fc.group_supervisor'):
            raise AccessError("Solo el supervisor o el administrador de taller pueden devolver consumos.")
        if not (self.motivo or '').strip():
            raise UserError("Indicá el motivo de la devolución.")
        self.producto_id._tllr_fc_devolver_consumo(self.cantidad, self.motivo)
        return {'type': 'ir.actions.act_window_close'}
