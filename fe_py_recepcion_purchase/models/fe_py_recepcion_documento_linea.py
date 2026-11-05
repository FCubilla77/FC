# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FePyRecepcionDocumentoLinea(models.Model):
    _inherit = 'fe_py_recepcion.documento.linea'

    purchase_id = fields.Many2one(related='documento_id.purchase_id')
    vincular_compras = fields.Boolean(related='documento_id.vincular_compras')
    purchase_line_id = fields.Many2one(
        'purchase.order.line', string='Línea de cotización', copy=False, ondelete='set null',
        domain="[('order_id', '=', purchase_id), ('display_type', '=', False)]",
        help='Opcional. Si se deja vacía, la línea se factura sin vínculo con la cotización.')

    @api.onchange('purchase_line_id')
    def _onchange_purchase_line_id(self):
        for linea in self:
            if linea.purchase_line_id and not linea.producto_id:
                linea.producto_id = linea.purchase_line_id.product_id

    @api.constrains('purchase_line_id', 'documento_id')
    def _check_purchase_line_id(self):
        for linea in self.filtered('purchase_line_id'):
            if linea.purchase_line_id.order_id != linea.documento_id.purchase_id:
                raise ValidationError(_(
                    'Línea %s: la línea de cotización elegida no pertenece a la cotización de la recepción.',
                    linea.orden))
            repetidas = linea.documento_id.line_ids.filtered(
                lambda l: l.purchase_line_id == linea.purchase_line_id)
            if len(repetidas) > 1:
                raise ValidationError(_(
                    'Línea %s: la misma línea de cotización está vinculada más de una vez.', linea.orden))
