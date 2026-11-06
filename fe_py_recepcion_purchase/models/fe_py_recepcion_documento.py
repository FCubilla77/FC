# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class FePyRecepcionDocumento(models.Model):
    _inherit = 'fe_py_recepcion.documento'

    vincular_compras = fields.Boolean(compute='_compute_vincular_compras')
    purchase_id = fields.Many2one(
        'purchase.order', string='Cotización', tracking=True, copy=False, ondelete='set null',
        domain="[('company_id', '=', company_id), ('state', 'in', ('purchase', 'done')), "
               "('invoice_status', '=', 'to invoice')]",
        help='Orden de compra confirmada con líneas pendientes de facturar. Como en el estándar '
             'de Odoo, las líneas del XML se pueden vincular o dejar sin vincular.')

    @api.depends('company_id.fe_py_recepcion_vincular_compras')
    def _compute_vincular_compras(self):
        for doc in self:
            doc.vincular_compras = doc.company_id.fe_py_recepcion_vincular_compras

    def _diagnostico(self):
        bloqueos, avisos = super()._diagnostico()
        if self.vincular_compras and self.purchase_id and self.partner_id:
            if self.purchase_id.partner_id.commercial_partner_id != self.partner_id.commercial_partner_id:
                avisos.append(_(
                    'La cotización %(orden)s es de otro proveedor (%(proveedor)s).',
                    orden=self.purchase_id.name, proveedor=self.purchase_id.partner_id.display_name))
        return bloqueos, avisos

    def _vals_factura(self):
        vals = super()._vals_factura()
        if self.vincular_compras and self.purchase_id:
            vals['invoice_origin'] = self.purchase_id.name
        return vals

    def _vals_linea_factura(self, linea):
        vals = super()._vals_linea_factura(linea)
        if self.vincular_compras and linea.purchase_line_id:
            vals['purchase_line_id'] = linea.purchase_line_id.id
        return vals

    def _post_confirmar(self, move):
        super()._post_confirmar(move)
        if self.vincular_compras and self.purchase_id:
            self.purchase_id.message_post(body=_(
                'Factura de proveedor %(factura)s generada desde la factura electrónica recibida %(doc)s.',
                factura=move.display_name, doc=self.name))

    def action_vincular_lineas(self):
        """Vincula las líneas que tienen producto con la línea de la cotización del mismo
        producto que todavía no se usó. Las demás quedan sin vincular."""
        for doc in self:
            if not doc.purchase_id:
                raise UserError(_('Primero elija la cotización.'))
            usadas = doc.line_ids.mapped('purchase_line_id')
            for linea in doc.line_ids.filtered(lambda l: l.producto_id and not l.purchase_line_id):
                candidata = doc.purchase_id.order_line.filtered(
                    lambda pl: pl.product_id == linea.producto_id and pl not in usadas
                    and not pl.display_type)[:1]
                if candidata:
                    linea.purchase_line_id = candidata
                    usadas |= candidata
        return True
