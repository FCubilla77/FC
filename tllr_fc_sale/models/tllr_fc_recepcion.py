# -*- coding: utf-8 -*-
from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError


class TllrFcRecepcion(models.Model):
    _inherit = 'tllr_fc.recepcion'

    tllr_fc_usar_ventas = fields.Boolean(related='company_id.tllr_fc_usar_ventas')
    sale_order_id = fields.Many2one(
        'sale.order', string="Presupuesto", copy=False, ondelete='set null', index='btree_not_null',
        tracking=True, check_company=True,
        domain="[('partner_id', '=', partner_id), ('state', 'in', ('draft', 'sent', 'sale')), "
               "'|', ('state', '=', 'sale'), '|', ('validity_date', '=', False), "
               "('validity_date', '>=', context_today().strftime('%Y-%m-%d')), "
               "('tllr_fc_recepcion_ids', '=', False)]",
        help="Presupuesto previo del cliente: mismo cliente, vigente y sin otra recepción vinculada.")
    cliente_pidio_presupuesto = fields.Boolean(
        string="El cliente pidió presupuesto", copy=False, tracking=True,
        help="La OT no inicia hasta que el presupuesto esté confirmado (el supervisor puede "
             "autorizar el inicio con un motivo).")

    @api.onchange('sale_order_id')
    def _onchange_sale_order_id(self):
        pedido = self.sale_order_id
        if not pedido:
            return
        self.cliente_pidio_presupuesto = True
        existentes = self.servicio_ids.product_id
        nuevos = []
        for linea in pedido.sudo().order_line.filtered(
                lambda l: not l.display_type and l.product_id.type == 'service'):
            if linea.product_id in existentes:
                continue
            existentes |= linea.product_id
            nuevos.append(Command.create({'product_id': linea.product_id.id}))
        if nuevos:
            self.servicio_ids = nuevos

    @api.constrains('sale_order_id', 'partner_id', 'vehiculo_id')
    def _check_sale_order(self):
        for recepcion in self.filtered('sale_order_id'):
            pedido = recepcion.sale_order_id.sudo()
            if pedido.state == 'cancel':
                raise ValidationError("El presupuesto %s está cancelado." % pedido.name)
            if pedido.partner_id != recepcion.partner_id:
                raise ValidationError(
                    "El presupuesto %s es de otro cliente (%s)." % (
                        pedido.name, pedido.partner_id.display_name))
            if pedido.tllr_fc_vehiculo_id and pedido.tllr_fc_vehiculo_id != recepcion.vehiculo_id:
                raise ValidationError(
                    "El presupuesto %s es del vehículo %s, distinto al de la recepción." % (
                        pedido.name, pedido.tllr_fc_vehiculo_id.display_name))
            otra = self.sudo().search_count([
                ('id', '!=', recepcion.id), ('sale_order_id', '=', pedido.id),
                ('state', '!=', 'cancelada')])
            if otra:
                raise ValidationError(
                    "El presupuesto %s ya está vinculado a otra recepción." % pedido.name)

    def _tllr_fc_preparar_ot(self):
        valores = super()._tllr_fc_preparar_ot()
        if self.sale_order_id:
            valores['sale_order_id'] = self.sale_order_id.id
        return valores

    def _tllr_fc_confirmar(self):
        ot = super()._tllr_fc_confirmar()
        pedido = self.sale_order_id.sudo()
        if pedido:
            valores = {'tllr_fc_ot_id': ot.id}
            if not pedido.tllr_fc_vehiculo_id:
                valores['tllr_fc_vehiculo_id'] = self.vehiculo_id.id
            if not pedido.tllr_fc_kilometraje:
                valores['tllr_fc_kilometraje'] = self.kilometraje
            pedido.write(valores)
            pedido.message_post(body="Presupuesto vinculado a la recepción %s y a la OT %s." % (
                self.name, ot.name))
        return ot

    def action_cancelar(self):
        resultado = super().action_cancelar()
        for recepcion in self.filtered(lambda r: r.state == 'cancelada' and r.sale_order_id):
            pedido = recepcion.sale_order_id.sudo()
            if pedido.tllr_fc_ot_id and pedido.tllr_fc_ot_id.state == 'cancelada':
                pedido.write({'tllr_fc_ot_id': False})
            pedido.message_post(body="Recepción %s anulada: el presupuesto queda libre." % recepcion.name)
            recepcion.with_context(tllr_fc_permitir_write=True).write({'sale_order_id': False})
        return resultado
