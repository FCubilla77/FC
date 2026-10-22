# -*- coding: utf-8 -*-
from markupsafe import Markup, escape

from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_compare


class TllrFcWizardCompraDirecta(models.TransientModel):
    _name = 'tllr_fc.wizard.compra_directa'
    _description = "Compra directa de repuestos desde la OT"

    ot_id = fields.Many2one('tllr_fc.ot', string="OT", required=True, readonly=True)
    es_supervisor = fields.Boolean(compute='_compute_es_supervisor')
    proveedor_id = fields.Many2one('res.partner', string="Proveedor")
    nota = fields.Text(string="Nota para el supervisor")
    linea_ids = fields.One2many(
        'tllr_fc.wizard.compra_directa.linea', 'wizard_id', string="Repuestos a comprar")

    def _compute_es_supervisor(self):
        supervisor = self.env.user.has_group('tllr_fc.group_supervisor')
        for asistente in self:
            asistente.es_supervisor = supervisor

    @api.model
    def default_get(self, campos):
        valores = super().default_get(campos)
        ot = self.env['tllr_fc.ot'].browse(
            valores.get('ot_id') or self.env.context.get('default_ot_id'))
        if ot and 'linea_ids' in campos:
            lineas = []
            for linea in ot.sudo().producto_ids.filtered(
                    lambda p: p._tllr_fc_mueve_stock() and not p.origen_compra_id):
                pendiente = linea.cantidad_requerida - linea.cantidad_consumida
                abiertos = linea._tllr_fc_movimientos_abiertos()
                if abiertos:
                    # Lo ya reservado en stock para esta línea no hace falta comprarlo.
                    faltante = pendiente - sum(abiertos.mapped('quantity'))
                else:
                    faltante = pendiente - linea.product_id.sudo().free_qty
                if float_compare(faltante, 0, precision_rounding=linea.uom_id.rounding or 0.001) > 0:
                    lineas.append(Command.create({
                        'producto_id': linea.id, 'cantidad': faltante}))
            valores['linea_ids'] = lineas
        return valores

    def _verificar(self):
        self.ensure_one()
        ot = self.ot_id
        if not ot.company_id.tllr_fc_usar_compras:
            raise UserError("La integración con Compras está desactivada en Ajustes.")
        if ot.state not in ('espera', 'proceso'):
            raise UserError("La compra directa se hace con la OT en espera o en proceso.")
        lineas = self.linea_ids.filtered(lambda l: l.cantidad > 0)
        if not lineas:
            raise UserError("Indicá al menos un repuesto con cantidad.")
        return lineas

    def action_crear_compra(self):
        """Crea la orden de compra (borrador) de los repuestos; solo supervisor."""
        self.ensure_one()
        if not self.env.user.has_group('tllr_fc.group_supervisor'):
            raise AccessError("Solo el supervisor o el administrador de taller crean la compra directa.")
        lineas = self._verificar()
        if not self.proveedor_id:
            raise UserError("Elegí el proveedor de la compra.")
        ot = self.ot_id
        compania = ot.company_id
        orden = []
        for linea in lineas:
            valores = {
                'product_id': linea.product_id.id,
                'name': linea.product_id.display_name,
                'product_qty': linea.cantidad,
            }
            if linea.precio:
                valores['price_unit'] = linea.precio
            orden.append(Command.create(valores))
        compra = self.env['purchase.order'].sudo().with_company(compania).create({
            'partner_id': self.proveedor_id.id,
            'company_id': compania.id,
            'origin': ot.name,
            'tllr_fc_ot_id': ot.id,
            'tllr_fc_tipo': 'directa',
            'order_line': orden,
        })
        lineas.producto_id.sudo().with_context(tllr_fc_permitir_write=True).write(
            {'origen_compra_id': compra.id})
        ot.message_post(body=Markup("Compra directa %s creada al proveedor %s: %s.") % (
            compra._get_html_link(), escape(self.proveedor_id.display_name),
            escape(', '.join(lineas.mapped('product_id.display_name')))))
        return {
            'type': 'ir.actions.act_window', 'res_model': 'purchase.order',
            'res_id': compra.id, 'view_mode': 'form', 'target': 'current'}

    def action_solicitar(self):
        """El usuario de taller solicita la compra: actividad para el supervisor."""
        self.ensure_one()
        lineas = self._verificar()
        ot = self.ot_id.sudo()
        grupo = self.env.ref('tllr_fc.group_supervisor')
        destinatarios = ot.responsable_id.user_id
        if not destinatarios:
            destinatarios = self.env['res.users'].sudo().search(
                [('all_group_ids', 'in', grupo.id), ('share', '=', False)], limit=3)
        detalle = ', '.join("%s × %s" % (l.cantidad, l.product_id.display_name) for l in lineas)
        for usuario in destinatarios:
            ot.activity_schedule(
                'mail.mail_activity_data_todo', user_id=usuario.id,
                summary="Solicitud de compra directa",
                note="%s solicita comprar: %s.%s" % (
                    self.env.user.name, detalle, (" " + self.nota) if self.nota else ""))
        self.ot_id.message_post(body="Se solicitó una compra directa: %s." % detalle)
        return {'type': 'ir.actions.act_window_close'}


class TllrFcWizardCompraDirectaLinea(models.TransientModel):
    _name = 'tllr_fc.wizard.compra_directa.linea'
    _description = "Línea de compra directa"

    wizard_id = fields.Many2one(
        'tllr_fc.wizard.compra_directa', required=True, ondelete='cascade')
    ot_id = fields.Many2one(related='wizard_id.ot_id')
    producto_id = fields.Many2one(
        'tllr_fc.ot.producto', string="Repuesto de la OT", required=True,
        domain="[('ot_id', '=', ot_id)]")
    product_id = fields.Many2one(related='producto_id.product_id', string="Producto")
    cantidad = fields.Float(string="Cantidad a comprar", required=True)
    precio = fields.Float(
        string="Precio unitario", help="Opcional: vacío = precio del proveedor o de la ficha.")
