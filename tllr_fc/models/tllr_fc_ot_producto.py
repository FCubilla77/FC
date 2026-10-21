# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

from .product_template import USOS_FACTURABLES

USOS_OT = ('repuesto', 'insumo', 'insumo_facturable', 'accesorio')
CAMPOS_SOLO_SUPERVISOR = (
    'precio_unitario', 'descuento', 'no_facturar', 'provisto_cliente', 'cobrar_cliente')


class TllrFcOtProducto(models.Model):
    """Repuesto, insumo o accesorio de la OT: lo reservado y lo utilizado.

    Reservar crea un movimiento de stock reservado hacia la ubicación virtual
    «Consumo en taller»; registrar lo utilizado valida ese movimiento.
    """
    _name = 'tllr_fc.ot.producto'
    _description = "Repuesto, insumo o accesorio de la orden de trabajo"
    _inherit = ['tllr_fc.mixin.wizard']
    _order = 'ot_id, id'

    ot_id = fields.Many2one(
        'tllr_fc.ot', string="OT", required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(
        'res.company', string="Compañía", related='ot_id.company_id',
        store=True, index=True)
    currency_id = fields.Many2one(
        'res.currency', related='ot_id.company_id.currency_id', string="Moneda")
    product_id = fields.Many2one(
        'product.product', string="Producto", required=True, ondelete='restrict',
        domain="[('tllr_fc_uso_taller', 'in', ('repuesto', 'insumo', 'insumo_facturable', 'accesorio'))]")
    uso = fields.Selection(
        related='product_id.tllr_fc_uso_taller', string="Uso", store=True, readonly=True)
    tracking = fields.Selection(related='product_id.tracking')
    descripcion = fields.Char(string="Observación")
    garantia_dias = fields.Integer(
        string="Garantía (días)", related='product_id.product_tmpl_id.tllr_fc_garantia_dias')
    garantia_km = fields.Integer(
        string="Garantía (km)", related='product_id.product_tmpl_id.tllr_fc_garantia_km')
    cantidad_reservada = fields.Float(string="Reservado", default=1.0, digits='Product Unit')
    cantidad_utilizada = fields.Float(string="Utilizado", digits='Product Unit')
    cantidad_no_utilizada = fields.Float(
        string="No utilizado", digits='Product Unit',
        help="Parte de lo reservado que no se usó. Utilizado + No utilizado debe igualar lo "
             "reservado para poder terminar el puesto. Lo no utilizado se libera y, con "
             "traslados activos, vuelve al almacén principal en un traslado en borrador.")
    cantidad_requerida = fields.Float(
        string="Requerido", digits='Product Unit', compute='_compute_cantidad_requerida',
        help="Reservado menos lo declarado como no utilizado.")
    uom_id = fields.Many2one('uom.uom', related='product_id.uom_id', string="Unidad")
    lote_id = fields.Many2one(
        'stock.lot', string="Lote", domain="[('product_id', '=', product_id)]",
        ondelete='restrict')
    precio_unitario = fields.Monetary(string="Precio unitario", currency_field='currency_id')
    descuento = fields.Float(string="Desc. (%)")
    no_facturar = fields.Boolean(
        string="No facturar", copy=False,
        help="Cortesía: conserva su costo en la OT pero no se factura. Solo el supervisor.")
    provisto_cliente = fields.Boolean(
        string="Provisto por el cliente", copy=False,
        help="El cliente trae el repuesto: no se factura ni mueve el stock de la empresa. "
             "Solo el supervisor.")
    cobrar_cliente = fields.Boolean(
        string="Cobrar al cliente", copy=False,
        help="Solo en OT de garantía: el repuesto o insumo no está cubierto por la garantía y "
             "se factura al cliente (requiere su aprobación, como un adicional). Solo el "
             "supervisor.")
    ot_tipo = fields.Selection(related='ot_id.tipo', string="Tipo de OT")
    facturable = fields.Boolean(string="Facturable", compute='_compute_facturable')
    subtotal = fields.Monetary(
        string="Subtotal", currency_field='currency_id', compute='_compute_subtotal')
    adicional = fields.Boolean(string="Adicional", readonly=True, copy=False)
    state_aprobacion = fields.Selection(
        [
        ('no_requiere', "No requiere"),
        ('pendiente', "Pendiente de aprobación"),
        ('aprobado', "Aprobado"),
        ('autorizado', "Autorizado sin aprobación"),
    ], string="Aprobación", required=True, default='no_requiere', copy=False,
        index=True)
    aprobacion_id = fields.Many2one(
        'tllr_fc.ot.aprobacion', string="Aprobación del cliente", readonly=True,
        copy=False, ondelete='set null')
    puesto_line_id = fields.Many2one(
        'tllr_fc.ot.puesto', string="Puesto", domain="[('ot_id', '=', ot_id)]",
        ondelete='set null', index=True, copy=False,
        help="Puesto de la OT que usa el repuesto o insumo. El stock se traslada al almacén "
             "del puesto y solo se registra su uso cuando el puesto está activo.")
    move_ids = fields.One2many(
        'stock.move', 'tllr_fc_ot_producto_id', string="Movimientos de stock", copy=False)
    traslado_move_ids = fields.One2many(
        'stock.move', 'tllr_fc_traslado_producto_id', string="Movimientos de traslado",
        copy=False)
    autorizado_sin_traslado = fields.Boolean(
        string="Uso autorizado sin traslado", readonly=True, copy=False,
        help="El supervisor autorizó usar el producto sin esperar el traslado al puesto: se "
             "descuenta del almacén principal.")
    traslado_requerido = fields.Boolean(
        string="Requiere traslado", compute='_compute_traslado_requerido')
    cantidad_en_puesto = fields.Float(
        string="En el puesto", compute='_compute_traslado_cantidades', digits='Product Unit')
    reserva_estado = fields.Selection([
        ('na', "—"),
        ('ok', "Reservado"),
        ('parcial', "Reserva parcial"),
        ('sin_stock', "Sin stock"),
        ('traslado', "Pendiente de traslado"),
    ], string="Reserva", compute='_compute_reserva_estado')
    cantidad_consumida = fields.Float(
        string="Consumido en stock", compute='_compute_cantidad_consumida', digits='Product Unit')
    costo = fields.Monetary(
        string="Costo", currency_field='currency_id', compute='_compute_costo',
        groups='tllr_fc.group_supervisor')

    # ------------------------------------------------------------------
    # Cálculos
    # ------------------------------------------------------------------
    @api.depends('uso', 'provisto_cliente', 'no_facturar', 'cobrar_cliente', 'ot_id.tipo')
    def _compute_facturable(self):
        for linea in self:
            facturable = (
                linea.uso in USOS_FACTURABLES
                and not linea.provisto_cliente and not linea.no_facturar)
            if linea.ot_id.tipo == 'garantia':
                # En una OT de garantía solo se factura lo marcado «Cobrar al cliente».
                facturable = facturable and linea.cobrar_cliente
            linea.facturable = facturable

    @api.depends('cantidad_reservada', 'cantidad_no_utilizada')
    def _compute_cantidad_requerida(self):
        for linea in self:
            linea.cantidad_requerida = max(
                linea.cantidad_reservada - linea.cantidad_no_utilizada, 0.0)

    @api.depends('cantidad_utilizada', 'cantidad_requerida', 'precio_unitario',
                 'descuento', 'facturable')
    def _compute_subtotal(self):
        for linea in self:
            if linea.facturable:
                # Se factura lo utilizado; mientras no se use nada, lo reservado (estimado).
                cantidad = linea.cantidad_utilizada or linea.cantidad_requerida
                linea.subtotal = cantidad * linea.precio_unitario * (1 - linea.descuento / 100.0)
            else:
                linea.subtotal = 0.0

    @api.depends('move_ids.state', 'move_ids.quantity')
    def _compute_cantidad_consumida(self):
        for linea in self:
            linea.cantidad_consumida = sum(
                -m.quantity if m.tllr_fc_devolucion_de_id else m.quantity
                for m in linea.sudo().move_ids if m.state == 'done')

    @api.depends('puesto_line_id', 'product_id', 'provisto_cliente', 'ot_id.state',
                 'company_id.tllr_fc_almacen_principal_id',
                 'puesto_line_id.puesto_id.almacen_id')
    def _compute_traslado_requerido(self):
        for linea in self:
            linea.traslado_requerido = linea._tllr_fc_requiere_traslado()

    @api.depends('traslado_move_ids.state', 'traslado_move_ids.quantity',
                 'traslado_move_ids.product_uom_qty', 'move_ids.state', 'move_ids.quantity')
    def _compute_traslado_cantidades(self):
        for linea in self:
            linea.cantidad_en_puesto = linea.sudo()._tllr_fc_cantidad_en_puesto()

    @api.depends('move_ids.state', 'move_ids.quantity', 'move_ids.product_uom_qty',
                 'traslado_move_ids.state', 'traslado_move_ids.quantity',
                 'cantidad_reservada', 'cantidad_utilizada', 'cantidad_no_utilizada',
                 'puesto_line_id', 'company_id.tllr_fc_almacen_principal_id')
    def _compute_reserva_estado(self):
        for linea in self:
            linea = linea.sudo()
            if linea._tllr_fc_requiere_traslado() and not linea.autorizado_sin_traslado:
                consumido = linea.cantidad_consumida
                pendiente = linea.cantidad_requerida - max(consumido, linea.cantidad_utilizada)
                if (pendiente > 0 and linea.ot_id.state in ('espera', 'proceso')
                        and linea._tllr_fc_cantidad_en_puesto() <= 0):
                    linea.reserva_estado = 'traslado'
                    continue
            abiertos = linea._tllr_fc_movimientos_abiertos()
            if not abiertos:
                linea.reserva_estado = 'na'
                continue
            pedido = sum(abiertos.mapped('product_uom_qty'))
            reservado = sum(abiertos.mapped('quantity'))
            if reservado <= 0:
                linea.reserva_estado = 'sin_stock'
            elif reservado < pedido:
                linea.reserva_estado = 'parcial'
            else:
                linea.reserva_estado = 'ok'

    @api.depends('move_ids.state', 'move_ids.value')
    def _compute_costo(self):
        for linea in self:
            hechos = linea.sudo().move_ids.filtered(lambda m: m.state == 'done')
            linea.costo = abs(sum(hechos.mapped('value')))

    @api.constrains('cantidad_reservada', 'cantidad_utilizada', 'cantidad_no_utilizada',
                    'descuento', 'precio_unitario')
    def _check_cantidades(self):
        for linea in self:
            if linea.cantidad_reservada <= 0:
                raise ValidationError(
                    "La cantidad reservada de «%s» debe ser mayor que cero." % linea.product_id.display_name)
            if linea.cantidad_utilizada < 0:
                raise ValidationError("La cantidad utilizada no puede ser negativa.")
            if float_compare(linea.cantidad_utilizada, linea.cantidad_reservada,
                             precision_rounding=linea.uom_id.rounding or 0.001) > 0:
                raise ValidationError(
                    "No se puede utilizar más de lo reservado de «%s». Aumentá primero la "
                    "cantidad reservada." % linea.product_id.display_name)
            if linea.cantidad_no_utilizada < 0:
                raise ValidationError("La cantidad no utilizada no puede ser negativa.")
            if float_compare(linea.cantidad_utilizada + linea.cantidad_no_utilizada,
                             linea.cantidad_reservada,
                             precision_rounding=linea.uom_id.rounding or 0.001) > 0:
                raise ValidationError(
                    "Utilizado + No utilizado de «%s» no puede superar lo reservado (%s)."
                    % (linea.product_id.display_name, linea.cantidad_reservada))
            if not 0 <= linea.descuento <= 100:
                raise ValidationError("El descuento debe estar entre 0 y 100.")
            if linea.precio_unitario < 0:
                raise ValidationError("El precio no puede ser negativo.")

    @api.constrains('no_facturar', 'uso')
    def _check_no_facturar(self):
        for linea in self:
            if linea.no_facturar and linea.uso not in USOS_FACTURABLES:
                raise ValidationError(
                    "«No facturar» solo aplica a repuestos, insumos facturables y accesorios.")

    @api.constrains('cobrar_cliente', 'ot_id', 'uso')
    def _check_cobrar_cliente(self):
        for linea in self:
            if linea.cobrar_cliente and linea.ot_id.tipo != 'garantia':
                raise ValidationError("«Cobrar al cliente» solo aplica a las OT de garantía.")
            if linea.cobrar_cliente and linea.uso not in USOS_FACTURABLES:
                raise ValidationError(
                    "«Cobrar al cliente» solo aplica a repuestos, insumos facturables y accesorios.")

    def _tllr_fc_sincronizar_cobro(self):
        """Marcar «Cobrar al cliente» exige la aprobación del cliente (como un adicional)."""
        for linea in self.filtered(lambda l: l.ot_id.tipo == 'garantia'):
            ctx = linea.with_context(tllr_fc_permitir_write=True)
            if linea.cobrar_cliente:
                if linea.state_aprobacion == 'no_requiere':
                    ctx.write({'state_aprobacion': 'pendiente'})
                if not linea.precio_unitario:
                    ctx.write({'precio_unitario': linea.product_id.list_price})
            elif linea.state_aprobacion != 'no_requiere':
                ctx.write({'state_aprobacion': 'no_requiere', 'aprobacion_id': False})

    @api.constrains('product_id')
    def _check_uso_producto(self):
        for linea in self:
            if linea.product_id.tllr_fc_uso_taller not in USOS_OT:
                raise ValidationError(
                    "«%s» no es un repuesto, insumo ni accesorio (revisá el uso en taller de su ficha)."
                    % linea.product_id.display_name)

    # ------------------------------------------------------------------
    # Utilidades de stock
    # ------------------------------------------------------------------
    def _es_supervisor(self):
        return self.env.user.has_group('tllr_fc.group_supervisor')

    def _tllr_fc_mueve_stock(self):
        self.ensure_one()
        producto = self.product_id
        return (producto.type == 'consu' and producto.is_storable
                and not self.provisto_cliente)

    def _tllr_fc_almacen_puesto(self):
        self.ensure_one()
        ot = self.ot_id
        linea = self.puesto_line_id
        if not linea:
            lineas = ot.puesto_line_ids
            linea = lineas.filtered(lambda l: l.state == 'activo')[:1] or lineas[:1]
        almacen = linea.puesto_id.almacen_id
        if not almacen:
            almacen = self.env['stock.warehouse'].search(
                [('company_id', '=', ot.company_id.id)], limit=1)
        if not almacen:
            raise UserError("La compañía %s no tiene almacén." % ot.company_id.name)
        return almacen.sudo()

    def _tllr_fc_ubicacion_puesto(self):
        self.ensure_one()
        return self._tllr_fc_almacen_puesto().lot_stock_id

    def _tllr_fc_ubicacion_principal(self):
        self.ensure_one()
        return self.ot_id.company_id.tllr_fc_almacen_principal_id.sudo().lot_stock_id

    def _tllr_fc_ubicacion_origen(self):
        self.ensure_one()
        return self._tllr_fc_ubicacion_puesto()

    def _tllr_fc_valores_movimiento(self, cantidad, origen=None):
        self.ensure_one()
        ot = self.ot_id
        return {
            'product_id': self.product_id.id,
            'product_uom': self.product_id.uom_id.id,
            'product_uom_qty': cantidad,
            'location_id': (origen or self._tllr_fc_ubicacion_origen()).id,
            'location_dest_id': ot.company_id._tllr_fc_ubicacion_consumo().id,
            'company_id': ot.company_id.id,
            'origin': ot.name,
            'reference': ot.name,
            'tllr_fc_ot_id': ot.id,
            'tllr_fc_ot_producto_id': self.id,
        }

    def action_devolver_consumo(self):
        """Abre el asistente para devolver a stock lo consumido (supervisor, con motivo)."""
        self.ensure_one()
        if not self._es_supervisor():
            raise AccessError("Solo el supervisor o el administrador de taller pueden devolver consumos.")
        return {
            'type': 'ir.actions.act_window', 'name': "Devolver consumo",
            'res_model': 'tllr_fc.wizard.devolver_consumo', 'view_mode': 'form',
            'target': 'new', 'context': {'default_producto_id': self.id},
        }

    def _tllr_fc_devolver_consumo(self, cantidad, motivo):
        """Deshace parte de lo consumido: lo devuelve al lugar de origen y baja lo utilizado."""
        self.ensure_one()
        ot = self.ot_id
        redondeo = self.uom_id.rounding or 0.001
        if ot.state not in ('proceso', 'calidad', 'listo') or ot.cerrada_facturar \
                or ot._tllr_fc_facturas():
            raise UserError(
                "No se puede devolver el consumo de «%s»: la OT %s no admite cambios de "
                "consumo (estado o facturación)." % (self.product_id.display_name, ot.name))
        if float_compare(cantidad, 0, precision_rounding=redondeo) <= 0:
            raise UserError("Indicá una cantidad a devolver mayor que cero.")
        if float_compare(cantidad, self.cantidad_consumida, precision_rounding=redondeo) > 0:
            raise UserError(
                "Solo se puede devolver hasta lo consumido de «%s» (%s)." % (
                    self.product_id.display_name, self.cantidad_consumida))
        resto = cantidad
        consumo = ot.company_id._tllr_fc_ubicacion_consumo()
        Movimiento = self.env['stock.move'].sudo()
        consumos = self.sudo().move_ids.filtered(
            lambda m: m.state == 'done' and not m.tllr_fc_devolucion_de_id
            and m.location_dest_id == consumo).sorted('id', reverse=True)
        for original in consumos:
            devuelto = sum(Movimiento.search([
                ('tllr_fc_devolucion_de_id', '=', original.id), ('state', '=', 'done')
            ]).mapped('quantity'))
            disponible = original.quantity - devuelto
            parte = min(resto, disponible)
            if float_compare(parte, 0, precision_rounding=redondeo) <= 0:
                continue
            valores = {
                'product_id': self.product_id.id,
                'product_uom': self.product_id.uom_id.id,
                'product_uom_qty': parte,
                'location_id': consumo.id,
                'location_dest_id': original.location_id.id,
                'company_id': ot.company_id.id,
                'origin': "Devolución %s" % ot.name,
                'reference': "Devolución %s" % ot.name,
                'tllr_fc_ot_id': ot.id,
                'tllr_fc_ot_producto_id': self.id,
                'tllr_fc_devolucion_de_id': original.id,
            }
            movimiento = Movimiento.create(valores)
            movimiento._action_confirm()
            self.env['stock.move.line'].sudo().create({
                'move_id': movimiento.id,
                'product_id': self.product_id.id,
                'product_uom_id': self.product_id.uom_id.id,
                'lot_id': self.lote_id.id or False,
                'quantity': parte,
                'location_id': consumo.id,
                'location_dest_id': original.location_id.id,
            })
            movimiento.picked = True
            movimiento._action_done()
            resto -= parte
            if float_compare(resto, 0, precision_rounding=redondeo) <= 0:
                break
        # Baja lo utilizado sin pasar por los controles de la edición normal.
        super(TllrFcOtProducto, self).write({
            'cantidad_utilizada': max(self.cantidad_utilizada - cantidad, 0.0)})
        self._tllr_fc_sincronizar_stock()
        ot.message_post(body="Devolución de consumo: %s × %s por %s. Motivo: %s" % (
            self.product_id.display_name, cantidad, self.env.user.name, motivo))

    def _tllr_fc_movimientos_abiertos(self):
        return self.sudo().move_ids.filtered(
            lambda m: m.state not in ('done', 'cancel'))

    def _tllr_fc_liberar_reserva(self):
        """Cancela los movimientos pendientes (libera lo reservado)."""
        for linea in self:
            abiertos = linea._tllr_fc_movimientos_abiertos()
            if abiertos:
                abiertos._action_cancel()

    # ------------------------------------------------------------------
    # Traslados al puesto
    # ------------------------------------------------------------------
    def _tllr_fc_requiere_traslado(self):
        """Hay traslado cuando el almacén del puesto no es el principal."""
        self.ensure_one()
        principal = self.ot_id.company_id.sudo().tllr_fc_almacen_principal_id
        puesto = self.puesto_line_id.puesto_id.sudo().almacen_id
        return bool(
            principal and puesto and puesto != principal
            and self._tllr_fc_mueve_stock())

    def _tllr_fc_cantidad_traslado(self, sentido, solo_hecho=False):
        self.ensure_one()
        total = 0.0
        for movimiento in self.sudo().traslado_move_ids:
            if movimiento.tllr_fc_sentido != sentido or movimiento.state == 'cancel':
                continue
            if movimiento.state == 'done':
                total += movimiento.quantity
            elif not solo_hecho:
                total += movimiento.product_uom_qty
        return total

    def _tllr_fc_consumido_en(self, ubicacion):
        self.ensure_one()
        consumos = sum(
            m.quantity for m in self.sudo().move_ids
            if m.state == 'done' and m.location_id == ubicacion
            and not m.tllr_fc_devolucion_de_id)
        devoluciones = sum(
            m.quantity for m in self.sudo().move_ids
            if m.state == 'done' and m.tllr_fc_devolucion_de_id
            and m.location_dest_id == ubicacion)
        return consumos - devoluciones

    def _tllr_fc_cantidad_en_puesto(self):
        """Stock trasladado y todavía no consumido en el almacén del puesto."""
        self.ensure_one()
        if not self._tllr_fc_requiere_traslado():
            return 0.0
        return (self._tllr_fc_cantidad_traslado('ida', True)
                - self._tllr_fc_cantidad_traslado('vuelta', True)
                - self._tllr_fc_consumido_en(self._tllr_fc_ubicacion_puesto()))

    def _tllr_fc_objetivo_traslado(self):
        """Cantidad neta que debe estar trasladada al puesto."""
        self.ensure_one()
        if not self._tllr_fc_requiere_traslado():
            return 0.0
        ubicacion = self._tllr_fc_ubicacion_puesto()
        consumido_puesto = self._tllr_fc_consumido_en(ubicacion)
        ot = self.ot_id
        if (ot.state in ('cancelada', 'entregado') or self.puesto_line_id.state == 'terminado'
                or self.autorizado_sin_traslado):
            return consumido_puesto
        consumido_principal = self._tllr_fc_consumido_en(self._tllr_fc_ubicacion_principal())
        return max(self.cantidad_requerida - consumido_principal, consumido_puesto)

    def _tllr_fc_picking_traslado(self, sentido):
        """Picking en borrador de la OT y del puesto (se crea si falta)."""
        self.ensure_one()
        ot = self.ot_id
        picking = self.env['stock.picking'].sudo().search([
            ('tllr_fc_ot_id', '=', ot.id),
            ('tllr_fc_puesto_line_id', '=', self.puesto_line_id.id),
            ('tllr_fc_sentido', '=', sentido), ('state', '=', 'draft')], limit=1)
        if picking:
            return picking
        principal = ot.company_id.tllr_fc_almacen_principal_id.sudo()
        puesto = self._tllr_fc_ubicacion_puesto()
        origen, destino = (
            (principal.lot_stock_id, puesto) if sentido == 'ida' else (puesto, principal.lot_stock_id))
        picking = self.env['stock.picking'].sudo().create({
            'picking_type_id': principal.int_type_id.id,
            'location_id': origen.id,
            'location_dest_id': destino.id,
            'origin': ot.name,
            'company_id': ot.company_id.id,
            'tllr_fc_ot_id': ot.id,
            'tllr_fc_puesto_line_id': self.puesto_line_id.id,
            'tllr_fc_sentido': sentido,
        })
        ot.message_post(body="Traslado %s en borrador (%s «%s»): lo confirma el encargado de almacén." % (
            picking.name, "al puesto" if sentido == 'ida' else "devolución desde el puesto",
            self.puesto_line_id.name))
        return picking

    def _tllr_fc_mover_borrador(self, sentido, cantidad):
        """Suma (cantidad > 0) o resta (< 0) lo pedido en el borrador del sentido."""
        self.ensure_one()
        redondeo = self.uom_id.rounding or 0.001
        movimientos = self.sudo().traslado_move_ids.filtered(
            lambda m: m.tllr_fc_sentido == sentido and m.state == 'draft')
        if float_compare(cantidad, 0, precision_rounding=redondeo) < 0:
            falta = -cantidad
            quitado = 0.0
            for movimiento in movimientos:
                if float_compare(falta, 0, precision_rounding=redondeo) <= 0:
                    break
                quitar = min(falta, movimiento.product_uom_qty)
                restante = movimiento.product_uom_qty - quitar
                picking = movimiento.picking_id
                if float_compare(restante, 0, precision_rounding=redondeo) <= 0:
                    movimiento.unlink()
                else:
                    movimiento.product_uom_qty = restante
                if picking and not picking.move_ids:
                    picking.unlink()
                falta -= quitar
                quitado += quitar
            return -quitado
        if movimientos:
            movimientos[0].product_uom_qty += cantidad
            return cantidad
        picking = self._tllr_fc_picking_traslado(sentido)
        vals = self._tllr_fc_valores_traslado(picking, sentido, cantidad)
        self.env['stock.move'].sudo().create(vals)
        return cantidad

    def _tllr_fc_valores_traslado(self, picking, sentido, cantidad):
        self.ensure_one()
        return {
            'product_id': self.product_id.id,
            'product_uom': self.product_id.uom_id.id,
            'product_uom_qty': cantidad,
            'picking_id': picking.id,
            'picking_type_id': picking.picking_type_id.id,
            'location_id': picking.location_id.id,
            'location_dest_id': picking.location_dest_id.id,
            'company_id': picking.company_id.id,
            'origin': self.ot_id.name,
            'tllr_fc_ot_id': self.ot_id.id,
            'tllr_fc_traslado_producto_id': self.id,
            'tllr_fc_sentido': sentido,
        }

    def _tllr_fc_sincronizar_traslados(self):
        """Deja los borradores de traslado coherentes con lo que cada puesto necesita.

        Compara la cantidad neta ya pedida (borradores y traslados hechos) con la que el
        puesto necesita, y solo registra la diferencia: no duplica traslados.
        """
        if self.env.context.get('tllr_fc_sin_traslados'):
            return
        for linea in self.sudo():
            if not linea.ot_id.company_id.tllr_fc_almacen_principal_id:
                continue
            redondeo = linea.uom_id.rounding or 0.001
            neto = (linea._tllr_fc_cantidad_traslado('ida')
                    - linea._tllr_fc_cantidad_traslado('vuelta'))
            diferencia = linea._tllr_fc_objetivo_traslado() - neto
            if float_is_zero(diferencia, precision_rounding=redondeo):
                continue
            if diferencia > 0:
                # Primero se anula una devolución en borrador; el resto va al puesto.
                absorbido = -linea._tllr_fc_mover_borrador('vuelta', -diferencia)
                resto = diferencia - absorbido
                if float_compare(resto, 0, precision_rounding=redondeo) > 0:
                    linea._tllr_fc_mover_borrador('ida', resto)
            else:
                # Primero se reduce lo pedido en borrador al puesto; el resto se devuelve.
                reducido = -linea._tllr_fc_mover_borrador('ida', diferencia)
                resto = -diferencia - reducido
                if float_compare(resto, 0, precision_rounding=redondeo) > 0:
                    linea._tllr_fc_mover_borrador('vuelta', resto)

    def _tllr_fc_verificar_uso_en_puesto(self, delta):
        """El uso se registra con el puesto activo y el traslado validado."""
        self.ensure_one()
        puesto = self.puesto_line_id
        if puesto and puesto.state != 'activo':
            raise UserError(
                "«%s» pertenece al puesto «%s», que no está activo: solo se registra su uso "
                "mientras el puesto está activo." % (self.product_id.display_name, puesto.name))
        if (delta > 0 and self._tllr_fc_requiere_traslado() and not self.autorizado_sin_traslado
                and float_compare(
                    self._tllr_fc_cantidad_en_puesto(), delta,
                    precision_rounding=self.uom_id.rounding or 0.001) < 0):
            raise UserError(
                "«%s» está pendiente de traslado al puesto «%s»: el encargado de almacén debe "
                "validar el traslado antes de registrar su uso (el supervisor puede autorizar "
                "el uso sin traslado)." % (self.product_id.display_name, puesto.name))

    def action_autorizar_sin_traslado(self):
        """El supervisor autoriza usar el producto sin esperar el traslado."""
        if not self._es_supervisor():
            raise AccessError("Solo el supervisor puede autorizar el uso sin traslado.")
        self.ensure_one()
        if self.autorizado_sin_traslado or not self._tllr_fc_requiere_traslado():
            raise UserError("La línea no tiene un traslado pendiente.")
        if not self.env.context.get('tllr_fc_excepcion'):
            return self._tllr_fc_abrir_excepcion(
                'action_autorizar_sin_traslado', 'supervisor',
                "Usar «%s» sin esperar el traslado al puesto «%s» (se descuenta del almacén "
                "principal)." % (self.product_id.display_name, self.puesto_line_id.name))
        self.with_context(tllr_fc_permitir_write=True).autorizado_sin_traslado = True
        self._tllr_fc_sincronizar_stock()
        self.ot_id.message_post(body="%s: uso autorizado sin traslado por %s. Motivo: %s" % (
            self.product_id.display_name, self.env.user.name,
            self.env.context.get('tllr_fc_motivo', '')))
        return True

    # ------------------------------------------------------------------
    # Consumo y reserva
    # ------------------------------------------------------------------
    def _tllr_fc_consumir(self, cantidad):
        """Valida el consumo de `cantidad` (del puesto y, si se autorizó, del almacén principal)."""
        self.ensure_one()
        origenes = [(self._tllr_fc_ubicacion_origen(), cantidad)]
        if self._tllr_fc_requiere_traslado():
            redondeo = self.uom_id.rounding or 0.001
            del_puesto = min(cantidad, max(self._tllr_fc_cantidad_en_puesto(), 0.0))
            resto = cantidad - del_puesto
            if float_compare(resto, 0, precision_rounding=redondeo) > 0 and not self.autorizado_sin_traslado:
                self._tllr_fc_verificar_uso_en_puesto(cantidad)
            origenes = []
            if float_compare(del_puesto, 0, precision_rounding=redondeo) > 0:
                origenes.append((self._tllr_fc_ubicacion_puesto(), del_puesto))
            if float_compare(resto, 0, precision_rounding=redondeo) > 0:
                origenes.append((self._tllr_fc_ubicacion_principal(), resto))
        movimientos = self.env['stock.move']
        for ubicacion, parte in origenes:
            movimientos |= self._tllr_fc_consumir_desde(ubicacion, parte)
        return movimientos

    def _tllr_fc_consumir_desde(self, origen_ubicacion, cantidad):
        self.ensure_one()
        redondeo = self.uom_id.rounding or 0.001
        movimiento = self.env['stock.move'].sudo().create(
            self._tllr_fc_valores_movimiento(cantidad, origen_ubicacion))
        movimiento._action_confirm()
        if self.lote_id:
            origen = movimiento.location_id
            disponible = self.env['stock.quant']._get_available_quantity(
                self.product_id, origen, lot_id=self.lote_id, strict=False)
            if float_compare(disponible, cantidad, precision_rounding=redondeo) < 0:
                raise UserError(
                    "Stock insuficiente de «%s» (lote %s): disponible %s, necesario %s." % (
                        self.product_id.display_name, self.lote_id.name, disponible, cantidad))
            self.env['stock.move.line'].sudo().create({
                'move_id': movimiento.id,
                'product_id': self.product_id.id,
                'product_uom_id': self.product_id.uom_id.id,
                'lot_id': self.lote_id.id,
                'quantity': cantidad,
                'location_id': origen.id,
                'location_dest_id': movimiento.location_dest_id.id,
            })
        else:
            movimiento._action_assign()
            if float_compare(movimiento.quantity, cantidad, precision_rounding=redondeo) < 0:
                faltante = cantidad - movimiento.quantity
                nombre = self.product_id.display_name
                ubicacion = movimiento.location_id.display_name
                movimiento._action_cancel()
                raise UserError(
                    "Stock insuficiente de «%s»: faltan %s %s en %s." % (
                        nombre, faltante, self.uom_id.name, ubicacion))
        movimiento.picked = True
        movimiento._action_done()
        return movimiento

    def _tllr_fc_reservar(self, cantidad):
        self.ensure_one()
        movimiento = self.env['stock.move'].sudo().create(
            self._tllr_fc_valores_movimiento(cantidad))
        movimiento._action_confirm()
        movimiento._action_assign()
        return movimiento

    def _tllr_fc_sincronizar_stock(self):
        """Deja el stock coherente con lo reservado y lo utilizado.

        - Con la OT en proceso, lo utilizado nuevo se valida (consumo real).
        - Con la OT en espera o en proceso, el resto reservado queda como
          reserva; en cualquier otro estado no queda reserva.
        - Con traslados a los puestos, solo se reserva lo que ya llegó al puesto.
        """
        for linea in self:
            if not linea._tllr_fc_mueve_stock():
                linea._tllr_fc_liberar_reserva()
                linea._tllr_fc_sincronizar_traslados()
                continue
            estado = linea.ot_id.state
            redondeo = linea.uom_id.rounding or 0.001
            consumido = linea.cantidad_consumida
            linea._tllr_fc_liberar_reserva()
            if estado == 'proceso':
                delta = linea.cantidad_utilizada - consumido
                if float_compare(delta, 0, precision_rounding=redondeo) > 0:
                    linea._tllr_fc_consumir(delta)
                    consumido += delta
            linea._tllr_fc_sincronizar_traslados()
            if estado in ('espera', 'proceso'):
                pendiente = linea.cantidad_requerida - max(consumido, linea.cantidad_utilizada)
                if linea._tllr_fc_requiere_traslado():
                    pendiente = min(pendiente, max(linea._tllr_fc_cantidad_en_puesto(), 0.0))
                if float_compare(pendiente, 0, precision_rounding=redondeo) > 0:
                    linea._tllr_fc_reservar(pendiente)

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    def _tllr_fc_verificar_ot_editable(self, ots):
        for ot in ots:
            if ot.state not in ('espera', 'proceso'):
                raise UserError(
                    "La OT %s está en estado «%s»: ya no se pueden modificar sus repuestos e insumos."
                    % (ot.name, dict(ot._fields['state'].selection)[ot.state]))

    @api.model_create_multi
    def create(self, vals_list):
        es_supervisor = self._es_supervisor()
        ots = self.env['tllr_fc.ot'].browse([v['ot_id'] for v in vals_list if v.get('ot_id')])
        self._tllr_fc_verificar_ot_editable(ots)
        for vals in vals_list:
            ot = self.env['tllr_fc.ot'].browse(vals.get('ot_id'))
            producto = self.env['product.product'].browse(vals.get('product_id'))
            if not es_supervisor:
                for campo in CAMPOS_SOLO_SUPERVISOR:
                    vals.pop(campo, None)
            if 'precio_unitario' not in vals:
                vals['precio_unitario'] = (
                    producto.list_price if producto.tllr_fc_uso_taller in USOS_FACTURABLES else 0.0)
            if 'descuento' not in vals:
                vals['descuento'] = ot.partner_id.tllr_fc_descuento
            if ot.state != 'espera':
                vals['adicional'] = True
                vals['state_aprobacion'] = 'pendiente' if ot.tipo == 'cliente' else 'no_requiere'
            if vals.get('cobrar_cliente') and ot.tipo == 'garantia':
                vals['state_aprobacion'] = 'pendiente'
            if not vals.get('puesto_line_id'):
                lineas_puesto = ot.puesto_line_ids.sorted(lambda l: (l.sequence, l.id))
                vals['puesto_line_id'] = (
                    lineas_puesto.filtered(lambda l: l.state == 'activo')[:1]
                    or lineas_puesto[:1]).id
            if (vals.get('cantidad_utilizada') or vals.get('cantidad_no_utilizada')) \
                    and ot.state != 'proceso':
                raise UserError("Solo se registra lo utilizado con la OT en proceso.")
        lineas = super().create(vals_list)
        for linea, vals in zip(lineas, vals_list):
            if vals.get('cantidad_utilizada'):
                linea._tllr_fc_verificar_aprobacion()
                linea._tllr_fc_verificar_uso_en_puesto(vals['cantidad_utilizada'])
        lineas._tllr_fc_sincronizar_stock()
        return lineas

    def _tllr_fc_verificar_aprobacion(self):
        """Un adicional pendiente de aprobación no se consume si la aprobación es obligatoria."""
        self.ensure_one()
        if (self.state_aprobacion == 'pendiente'
                and self.company_id.tllr_fc_aprobacion_adicional == 'obligatoria'):
            raise UserError(
                "«%s» es un trabajo adicional pendiente de aprobación del cliente. El "
                "supervisor debe registrar la aprobación o autorizar el uso sin ella."
                % self.product_id.display_name)

    def action_autorizar_sin_aprobacion(self):
        """El supervisor autoriza usar el adicional sin la aprobación del cliente."""
        if not self._es_supervisor():
            raise AccessError("Solo el supervisor puede autorizar el uso sin aprobación.")
        self.ensure_one()
        if self.state_aprobacion != 'pendiente':
            raise UserError("La línea no está pendiente de aprobación.")
        if not self.env.context.get('tllr_fc_excepcion'):
            return self._tllr_fc_abrir_excepcion(
                'action_autorizar_sin_aprobacion', 'supervisor',
                "Usar «%s» sin la aprobación del cliente." % self.product_id.display_name)
        self.with_context(tllr_fc_permitir_write=True).state_aprobacion = 'autorizado'
        return True

    def write(self, vals):
        if not self.env.context.get('tllr_fc_permitir_write') and (
                {'state_aprobacion', 'aprobacion_id', 'adicional'} & set(vals)):
            raise UserError("La aprobación de un adicional se registra con el botón de la OT.")
        if vals.get('cantidad_utilizada'):
            for linea in self:
                if vals['cantidad_utilizada'] > linea.cantidad_utilizada:
                    linea._tllr_fc_verificar_aprobacion()
                    linea._tllr_fc_verificar_uso_en_puesto(
                        vals['cantidad_utilizada'] - linea.cantidad_utilizada)
        if 'puesto_line_id' in vals:
            for linea in self:
                if vals['puesto_line_id'] == linea.puesto_line_id.id:
                    continue
                if linea.cantidad_consumida or linea._tllr_fc_cantidad_traslado('ida', True):
                    raise UserError(
                        "No se puede cambiar el puesto de «%s»: ya se consumió o se trasladó "
                        "stock para el puesto actual." % linea.product_id.display_name)
                linea._tllr_fc_cancelar_borradores()
        if any(campo in vals for campo in CAMPOS_SOLO_SUPERVISOR) and not self._es_supervisor():
            raise AccessError(
                "Solo el supervisor o el administrador de taller pueden cambiar el precio, el "
                "descuento, «No facturar» o «Provisto por el cliente».")
        if not (self.env.context.get('tllr_fc_refacturando') and set(vals) <= {'no_facturar'}):
            self._tllr_fc_verificar_ot_editable(self.ot_id)
        if 'cantidad_no_utilizada' in vals:
            for linea in self:
                if linea.ot_id.state != 'proceso' and (
                        vals['cantidad_no_utilizada'] != linea.cantidad_no_utilizada):
                    raise UserError("Solo se registra lo no utilizado con la OT en proceso.")
        if 'cantidad_utilizada' in vals:
            for linea in self:
                if linea.ot_id.state != 'proceso' and vals['cantidad_utilizada'] != linea.cantidad_utilizada:
                    raise UserError("Solo se registra lo utilizado con la OT en proceso.")
                if float_compare(vals['cantidad_utilizada'], linea.cantidad_consumida,
                                 precision_rounding=linea.uom_id.rounding or 0.001) < 0:
                    raise UserError(
                        "No se puede reducir lo utilizado de «%s»: ya se descontó %s del stock."
                        % (linea.product_id.display_name, linea.cantidad_consumida))
        if 'product_id' in vals or 'lote_id' in vals:
            for linea in self:
                if linea.cantidad_consumida and (
                        vals.get('product_id', linea.product_id.id) != linea.product_id.id
                        or vals.get('lote_id', linea.lote_id.id) != linea.lote_id.id):
                    raise UserError(
                        "No se puede cambiar el producto ni el lote de «%s»: ya se consumió stock."
                        % linea.product_id.display_name)
        resultado = super().write(vals)
        if {'product_id', 'cantidad_reservada', 'cantidad_utilizada', 'cantidad_no_utilizada',
                'lote_id', 'provisto_cliente', 'puesto_line_id'} & set(vals):
            self._tllr_fc_sincronizar_stock()
        if 'cobrar_cliente' in vals:
            self._tllr_fc_sincronizar_cobro()
        for campo, texto in (
                ('no_facturar', "«No facturar»"), ('provisto_cliente', "«Provisto por el cliente»"),
                ('cobrar_cliente', "«Cobrar al cliente»")):
            if campo in vals:
                for linea in self:
                    linea.ot_id.message_post(body="%s: %s %s por %s." % (
                        linea.product_id.display_name, texto,
                        "activado" if linea[campo] else "desactivado", self.env.user.name))
        return resultado

    @api.ondelete(at_uninstall=False)
    def _unlink_validar(self):
        self._tllr_fc_verificar_ot_editable(self.ot_id)
        for linea in self:
            if linea.cantidad_consumida:
                raise UserError(
                    "No se puede eliminar «%s»: ya se consumió stock." % linea.product_id.display_name)
        self._tllr_fc_liberar_reserva()
        for linea in self:
            linea._tllr_fc_cerrar_traslados()

    def _tllr_fc_cancelar_borradores(self):
        """Anula los traslados en borrador de la línea (y los pickings que queden vacíos)."""
        for linea in self.sudo():
            for movimiento in linea.traslado_move_ids.filtered(lambda m: m.state == 'draft'):
                picking = movimiento.picking_id
                movimiento.unlink()
                if picking and not picking.move_ids:
                    picking.unlink()

    def _tllr_fc_cerrar_traslados(self):
        """Al eliminar la línea: anula lo pendiente y devuelve lo que quedó en el puesto."""
        self.ensure_one()
        self._tllr_fc_cancelar_borradores()
        if not self._tllr_fc_requiere_traslado():
            return
        sobrante = self._tllr_fc_cantidad_en_puesto()
        if sobrante > 0:
            picking = self._tllr_fc_picking_traslado('vuelta')
            vals = self._tllr_fc_valores_traslado(picking, 'vuelta', sobrante)
            vals['tllr_fc_traslado_producto_id'] = False
            self.env['stock.move'].sudo().create(vals)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for linea in self:
            producto = linea.product_id
            linea.precio_unitario = (
                producto.list_price if producto.tllr_fc_uso_taller in USOS_FACTURABLES else 0.0)
            if linea.lote_id and linea.lote_id.product_id != producto:
                linea.lote_id = False
