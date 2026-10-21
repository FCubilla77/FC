# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class TllrFcWizardRefacturar(models.TransientModel):
    """Vuelve a facturar una OT cuya factura se anuló con una nota de crédito total.

    Lo que no se quiere cobrar en la nueva factura se desmarca: queda con «No facturar»
    (conserva su costo en la OT).
    """
    _name = 'tllr_fc.wizard.refacturar'
    _description = "Refacturar la OT"

    ot_id = fields.Many2one('tllr_fc.ot', string="OT", required=True, ondelete='cascade')
    motivo = fields.Text(string="Motivo", required=True)
    linea_ids = fields.One2many(
        'tllr_fc.wizard.refacturar.linea', 'wizard_id', string="Qué se factura")

    @api.model
    def default_get(self, campos):
        valores = super().default_get(campos)
        ot = self.env['tllr_fc.ot'].browse(
            valores.get('ot_id') or self.env.context.get('default_ot_id'))
        if ot:
            lineas = []
            for servicio in ot.servicio_ids.filtered(lambda s: s.estado != 'no_realizado'):
                if ot.tipo == 'garantia' and not servicio.cobrar_cliente:
                    continue
                lineas.append((0, 0, {
                    'servicio_id': servicio.id, 'name': servicio.product_id.display_name,
                    'cantidad': servicio.cantidad, 'importe': servicio.subtotal,
                    'facturar': not servicio.no_facturar}))
            for producto in ot.producto_ids.filtered(
                    lambda p: not p.provisto_cliente and p.uso in (
                        'repuesto', 'insumo_facturable', 'accesorio')):
                if ot.tipo == 'garantia' and not producto.cobrar_cliente:
                    continue
                lineas.append((0, 0, {
                    'producto_id': producto.id, 'name': producto.product_id.display_name,
                    'cantidad': producto.cantidad_utilizada or producto.cantidad_requerida,
                    'importe': producto.subtotal, 'facturar': not producto.no_facturar}))
            valores['linea_ids'] = lineas
        return valores

    def action_refacturar(self):
        self.ensure_one()
        ot = self.ot_id
        if not self.env.user.has_group('tllr_fc.group_supervisor'):
            raise AccessError("Solo el supervisor o el administrador de taller pueden refacturar.")
        if not ot.puede_refacturar:
            raise UserError("La OT %s no se puede refacturar." % ot.name)
        if not (self.motivo or '').strip():
            raise UserError("Indicá el motivo de la refacturación.")
        if not self.linea_ids.filtered('facturar'):
            raise UserError("Dejá al menos una línea para facturar.")
        ctx = {'tllr_fc_refacturando': True, 'tllr_fc_permitir_write': True}
        for linea in self.linea_ids:
            registro = linea.servicio_id or linea.producto_id
            if registro and registro.no_facturar == linea.facturar:
                registro.with_context(**ctx).write({'no_facturar': not linea.facturar})
        ot.message_post(body="Refacturación solicitada por %s. Motivo: %s" % (
            self.env.user.name, self.motivo))
        return ot.with_context(tllr_fc_refacturando=True).action_cerrar_facturar()


class TllrFcWizardRefacturarLinea(models.TransientModel):
    _name = 'tllr_fc.wizard.refacturar.linea'
    _description = "Línea del asistente de refacturación"

    wizard_id = fields.Many2one(
        'tllr_fc.wizard.refacturar', required=True, ondelete='cascade')
    servicio_id = fields.Many2one('tllr_fc.ot.servicio', string="Servicio")
    producto_id = fields.Many2one('tllr_fc.ot.producto', string="Producto")
    name = fields.Char(string="Descripción", readonly=True)
    cantidad = fields.Float(string="Cantidad", readonly=True)
    importe = fields.Float(string="Importe", readonly=True)
    facturar = fields.Boolean(string="Se factura", default=True)
