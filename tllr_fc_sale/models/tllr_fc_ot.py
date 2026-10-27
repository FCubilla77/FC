# -*- coding: utf-8 -*-
from collections import defaultdict

from markupsafe import Markup, escape

from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError


class TllrFcOt(models.Model):
    _inherit = 'tllr_fc.ot'

    tllr_fc_usar_ventas = fields.Boolean(related='company_id.tllr_fc_usar_ventas')
    sale_order_id = fields.Many2one(
        'sale.order', string="Presupuesto / pedido", readonly=True, copy=False,
        ondelete='set null', index='btree_not_null')
    presupuesto_estado = fields.Selection([
        ('sin_presupuesto', "Sin presupuesto"),
        ('borrador', "Presupuesto en borrador"),
        ('confirmado', "Presupuesto confirmado"),
        ('vencido', "Presupuesto vencido"),
    ], string="Estado del presupuesto", compute='_compute_presupuesto_estado')
    presupuesto_importe = fields.Monetary(
        string="Importe del presupuesto", currency_field='currency_id',
        compute='_compute_presupuesto_estado')
    actualizar_presupuesto = fields.Boolean(
        string="Habilitar actualización del presupuesto", copy=False,
        help="Permite actualizar el presupuesto existente con lo ejecutado por la OT.")

    @api.depends('sale_order_id.state', 'sale_order_id.validity_date', 'sale_order_id.amount_total')
    def _compute_presupuesto_estado(self):
        hoy = fields.Date.context_today(self)
        for ot in self:
            pedido = ot.sale_order_id.sudo()
            if not pedido or pedido.state == 'cancel':
                ot.presupuesto_estado = 'sin_presupuesto'
                ot.presupuesto_importe = 0.0
                continue
            if pedido.state == 'sale':
                ot.presupuesto_estado = 'confirmado'
            elif pedido.validity_date and pedido.validity_date < hoy:
                ot.presupuesto_estado = 'vencido'
            else:
                ot.presupuesto_estado = 'borrador'
            ot.presupuesto_importe = pedido.amount_total

    def write(self, vals):
        if 'actualizar_presupuesto' in vals and not self._tllr_fc_es_supervisor():
            raise AccessError(
                "Solo el supervisor o el administrador de taller pueden habilitar la "
                "actualización del presupuesto.")
        return super().write(vals)

    # ------------------------------------------------------------------
    # Ganchos del núcleo
    # ------------------------------------------------------------------
    def _tllr_fc_usa_ventas(self):
        """Una OT con pedido vigente se factura siempre desde su pedido."""
        self.ensure_one()
        if self.tipo == 'interno':
            return False
        if self.sale_order_id and self.sale_order_id.sudo().state != 'cancel':
            return True
        return bool(self.company_id.tllr_fc_usar_ventas)

    def _tllr_fc_requiere_presupuesto(self):
        self.ensure_one()
        return bool(
            self.tipo == 'cliente' and self.company_id.tllr_fc_usar_ventas
            and self.recepcion_id.cliente_pidio_presupuesto)

    def _tllr_fc_presupuesto_ok_para_iniciar(self):
        self.ensure_one()
        return self.presupuesto_estado == 'confirmado'

    def _tllr_fc_importe_estimado(self):
        self.ensure_one()
        if self.sale_order_id and self.sale_order_id.sudo().state != 'cancel':
            return self.presupuesto_importe
        return super()._tllr_fc_importe_estimado()

    def _tllr_fc_facturas(self):
        facturas = super()._tllr_fc_facturas()
        pedido = self.sale_order_id.sudo()
        if pedido:
            facturas |= pedido.invoice_ids.filtered(
                lambda m: m.move_type == 'out_invoice'
                and not (m.state == 'posted' and m._tllr_fc_totalmente_acreditada()))
        return facturas

    # ------------------------------------------------------------------
    # Presupuesto / pedido
    # ------------------------------------------------------------------
    def _tllr_fc_valores_lineas_pedido(self, solo_realizado=False, estimado=False):
        """Valores de las líneas del pedido: lo mismo que se facturaría (precios de la ficha)."""
        self.ensure_one()
        resultado = []
        for comando in self._tllr_fc_lineas_factura(solo_realizado, estimado=estimado):
            datos = comando[2]
            resultado.append({
                'product_id': datos['product_id'],
                'name': datos['name'],
                'product_uom_qty': datos['quantity'],
                'price_unit': datos['price_unit'],
                'discount': datos['discount'],
            })
        return resultado

    def _tllr_fc_actualizar_documento_venta(self, solo_realizado=False, reabrir=False):
        """Crea el presupuesto de la OT o actualiza el existente (un solo documento).

        Con `reabrir` (botón «Crear / actualizar presupuesto») el presupuesto se arma con lo
        estimado (cantidad requerida) y, si estaba confirmado y hay diferencias, vuelve a
        borrador para su reconfirmación. El cierre y la liquidación ajustan el pedido
        confirmado directamente.
        """
        self.ensure_one()
        if not self._tllr_fc_usa_ventas():
            return super()._tllr_fc_actualizar_documento_venta(solo_realizado)
        deseadas = self._tllr_fc_valores_lineas_pedido(solo_realizado, estimado=reabrir)
        pedido = self.sudo().sale_order_id
        if not pedido or pedido.state == 'cancel':
            return self._tllr_fc_crear_pedido(deseadas)
        return self._tllr_fc_sincronizar_pedido(pedido, deseadas, reabrir=reabrir)

    def _tllr_fc_crear_pedido(self, deseadas):
        self.ensure_one()
        compania = self.company_id
        pedido = self.env['sale.order'].sudo().with_company(compania).with_context(
            tllr_fc_desde_ot=True).create({
                'partner_id': self.partner_id.id,
                'company_id': compania.id,
                'origin': self.name,
                'tllr_fc_ot_id': self.id,
                'tllr_fc_vehiculo_id': self.vehiculo_id.id,
                'tllr_fc_kilometraje': self.kilometraje_ingreso,
                'order_line': [
                    Command.create(dict(v, tllr_fc_origen='ot')) for v in deseadas],
            })
        if pedido.currency_id != compania.currency_id:
            raise UserError(
                "La lista de precios del cliente usa %s y los precios de la OT están en %s. "
                "Ajustá la lista de precios del cliente." % (
                    pedido.currency_id.name, compania.currency_id.name))
        self.sudo().with_context(tllr_fc_permitir_write=True).write({'sale_order_id': pedido.id})
        pedido.message_post(body=Markup("Presupuesto generado desde la OT %s por %s.") % (
            escape(self.name), escape(self.env.user.name)))
        self.message_post(body=Markup("Se generó el presupuesto %s.") % pedido._get_html_link())
        return pedido

    def _tllr_fc_plan_sincronizacion(self, pedido, deseadas):
        """Qué cambiar en el pedido para reflejar la OT (no escribe).

        Solo se gestionan las líneas «Desde la OT». Las manuales no se tocan. En la primera
        actualización de un pedido sin líneas marcadas (por ejemplo, un presupuesto previo a
        la recepción) se adoptan las líneas cuyo producto coincide con un ítem de la OT.
        """
        lineas = pedido.order_line.filtered(lambda l: not l.display_type)
        gestionadas = lineas.filtered(lambda l: l.tllr_fc_origen == 'ot')
        adopta = not gestionadas
        disponibles = defaultdict(list)
        for linea in (gestionadas or lineas):
            disponibles[linea.product_id.id].append(linea)
        comandos = []
        hay_cambios = False
        for valores in deseadas:
            candidatas = disponibles.get(valores['product_id'])
            if candidatas:
                linea = candidatas.pop(0)
                cambios = {}
                if linea.tllr_fc_origen != 'ot':
                    cambios['tllr_fc_origen'] = 'ot'
                diferencia = False
                if abs(linea.product_uom_qty - valores['product_uom_qty']) > 1e-6:
                    cambios['product_uom_qty'] = valores['product_uom_qty']
                    diferencia = True
                # Con la cantidad se recalcularía el precio por lista: se fija siempre.
                if diferencia or abs(linea.price_unit - valores['price_unit']) > 1e-6:
                    cambios['price_unit'] = valores['price_unit']
                    diferencia = diferencia or abs(linea.price_unit - valores['price_unit']) > 1e-6
                if abs(linea.discount - valores['discount']) > 1e-6:
                    cambios['discount'] = valores['discount']
                    diferencia = True
                if cambios:
                    hay_cambios = hay_cambios or diferencia
                    if diferencia:
                        cambios['price_unit'] = valores['price_unit']
                    comandos.append(Command.update(linea.id, cambios))
            else:
                hay_cambios = True
                comandos.append(Command.create(dict(valores, tllr_fc_origen='ot')))
        if not adopta:
            # Líneas «Desde la OT» que ya no están en la OT.
            for sobrantes in disponibles.values():
                for linea in sobrantes:
                    if linea.product_uom_qty == 0 and pedido.state == 'sale':
                        continue
                    hay_cambios = True
                    if pedido.state in ('draft', 'sent'):
                        comandos.append(Command.delete(linea.id))
                    else:
                        comandos.append(Command.update(linea.id, {'product_uom_qty': 0}))
        return comandos, hay_cambios

    def _tllr_fc_sincronizar_pedido(self, pedido, deseadas, reabrir=False):
        """Ajusta las líneas «Desde la OT» del pedido y deja el historial en el chatter."""
        self.ensure_one()
        pedido = pedido.with_context(
            skip_procurement=True, tllr_fc_vencido_ok=True, tllr_fc_desde_ot=True)
        if pedido.locked:
            pedido.action_unlock()
        _comandos, hay_cambios = self._tllr_fc_plan_sincronizacion(pedido, deseadas)
        reabierto = False
        if reabrir and hay_cambios and pedido.state == 'sale':
            facturas = pedido.invoice_ids.filtered(lambda m: m.state != 'cancel')
            if facturas:
                raise UserError(
                    "El presupuesto %s ya tiene factura (%s): no se puede reabrir para "
                    "actualizarlo." % (pedido.name, ', '.join(facturas.mapped('name'))))
            pedido._action_cancel()
            pedido.action_draft()
            reabierto = True
        comandos, hay_cambios = self._tllr_fc_plan_sincronizacion(pedido, deseadas)
        if comandos:
            anterior = pedido._tllr_fc_html_lineas()
            pedido.write({'order_line': comandos})
            if hay_cambios:
                pedido.message_post(body=Markup(
                    "<p>Presupuesto actualizado desde la OT %s por %s el %s.</p>"
                    "<p>Líneas anteriores:</p>%s") % (
                        escape(self.name), escape(self.env.user.name),
                        fields.Datetime.context_timestamp(
                            self, fields.Datetime.now()).strftime('%d/%m/%Y %H:%M'),
                        anterior))
        if reabierto:
            pedido.message_post(body=Markup(
                "El presupuesto estaba confirmado: volvió a borrador para su reconfirmación."))
            self.message_post(body=Markup(
                "Presupuesto %s reabierto por actualización: queda pendiente de "
                "reconfirmación por el cliente.") % pedido._get_html_link())
        return pedido

    def _tllr_fc_generar_documento_venta(self, solo_realizado=False):
        """Con Ventas: actualiza el pedido, lo confirma y factura desde él."""
        self.ensure_one()
        if not self._tllr_fc_usa_ventas():
            return super()._tllr_fc_generar_documento_venta(solo_realizado)
        compania = self.company_id
        if not compania.tllr_fc_diario_venta_id:
            raise UserError(
                "Definí el «Diario de factura de venta» en Taller › Configuración › Ajustes "
                "antes de cerrar la OT para facturar.")
        if not self._tllr_fc_lineas_factura(solo_realizado):
            raise UserError("La OT %s no tiene líneas para facturar." % self.name)
        pedido = self._tllr_fc_actualizar_documento_venta(solo_realizado)
        pedido._tllr_fc_verificar_almacenables_manuales(self)
        if pedido.state in ('draft', 'sent'):
            # Sin movimientos de stock propios de Ventas: el stock lo mueve la OT.
            pedido.with_context(skip_procurement=True, tllr_fc_vencido_ok=True).action_confirm()
            pedido.message_post(body=Markup(
                "Confirmado automáticamente al cerrar la OT %s para facturar.") % escape(self.name))
        return pedido._tllr_fc_crear_factura(self)

    def action_actualizar_presupuesto(self):
        """Crea el presupuesto de la OT o lo actualiza con lo ejecutado."""
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError(
                "Solo el supervisor o el administrador de taller pueden actualizar el presupuesto.")
        if self.tipo == 'interno' or not self._tllr_fc_usa_ventas():
            raise UserError("Esta OT no usa presupuesto de Ventas.")
        if self.state in ('entregado', 'cancelada') or self.cerrada_facturar:
            raise UserError("La OT ya está cerrada: no se actualiza el presupuesto.")
        if self.sale_order_id and not self.actualizar_presupuesto:
            raise UserError(
                "Habilitá la actualización del presupuesto en la OT para modificar el existente.")
        pedido = self._tllr_fc_actualizar_documento_venta(reabrir=True)
        self._tllr_fc_ajustar_cubierta_a_presupuesto()
        self.message_post(body=Markup("Presupuesto %s actualizado.") % pedido._get_html_link())
        return True

    def action_ver_presupuesto(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': "Presupuesto",
            'res_model': 'sale.order', 'res_id': self.sale_order_id.id,
            'view_mode': 'form', 'target': 'current',
        }
