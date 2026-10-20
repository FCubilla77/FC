# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

from .product_template import USOS_FACTURABLES

USOS_OT = ('repuesto', 'insumo', 'insumo_facturable', 'accesorio')
CAMPOS_SOLO_SUPERVISOR = ('precio_unitario', 'descuento', 'no_facturar', 'provisto_cliente')


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
    cantidad_reservada = fields.Float(string="Reservado", default=1.0, digits='Product Unit')
    cantidad_utilizada = fields.Float(string="Utilizado", digits='Product Unit')
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
    move_ids = fields.One2many(
        'stock.move', 'tllr_fc_ot_producto_id', string="Movimientos de stock", copy=False)
    reserva_estado = fields.Selection([
        ('na', "—"),
        ('ok', "Reservado"),
        ('parcial', "Reserva parcial"),
        ('sin_stock', "Sin stock"),
    ], string="Reserva", compute='_compute_reserva_estado')
    cantidad_consumida = fields.Float(
        string="Consumido en stock", compute='_compute_cantidad_consumida', digits='Product Unit')
    costo = fields.Monetary(
        string="Costo", currency_field='currency_id', compute='_compute_costo',
        groups='tllr_fc.group_supervisor')

    # ------------------------------------------------------------------
    # Cálculos
    # ------------------------------------------------------------------
    @api.depends('uso', 'provisto_cliente', 'no_facturar')
    def _compute_facturable(self):
        for linea in self:
            linea.facturable = (
                linea.uso in USOS_FACTURABLES
                and not linea.provisto_cliente and not linea.no_facturar)

    @api.depends('cantidad_utilizada', 'cantidad_reservada', 'precio_unitario',
                 'descuento', 'facturable')
    def _compute_subtotal(self):
        for linea in self:
            if linea.facturable:
                # Se factura lo utilizado; mientras no se use nada, lo reservado (estimado).
                cantidad = linea.cantidad_utilizada or linea.cantidad_reservada
                linea.subtotal = cantidad * linea.precio_unitario * (1 - linea.descuento / 100.0)
            else:
                linea.subtotal = 0.0

    @api.depends('move_ids.state', 'move_ids.quantity')
    def _compute_cantidad_consumida(self):
        for linea in self:
            linea.cantidad_consumida = sum(
                m.quantity for m in linea.sudo().move_ids if m.state == 'done')

    @api.depends('move_ids.state', 'move_ids.quantity', 'move_ids.product_uom_qty')
    def _compute_reserva_estado(self):
        for linea in self:
            abiertos = linea.sudo()._tllr_fc_movimientos_abiertos()
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

    @api.constrains('cantidad_reservada', 'cantidad_utilizada', 'descuento', 'precio_unitario')
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

    def _tllr_fc_ubicacion_origen(self):
        self.ensure_one()
        ot = self.ot_id
        lineas = ot.puesto_line_ids
        linea = lineas.filtered(lambda l: l.state == 'activo')[:1] or lineas[:1]
        almacen = linea.puesto_id.almacen_id
        if not almacen:
            almacen = self.env['stock.warehouse'].search(
                [('company_id', '=', ot.company_id.id)], limit=1)
        if not almacen:
            raise UserError("La compañía %s no tiene almacén." % ot.company_id.name)
        return almacen.sudo().lot_stock_id

    def _tllr_fc_valores_movimiento(self, cantidad):
        self.ensure_one()
        ot = self.ot_id
        return {
            'product_id': self.product_id.id,
            'product_uom': self.product_id.uom_id.id,
            'product_uom_qty': cantidad,
            'location_id': self._tllr_fc_ubicacion_origen().id,
            'location_dest_id': ot.company_id._tllr_fc_ubicacion_consumo().id,
            'company_id': ot.company_id.id,
            'origin': ot.name,
            'reference': ot.name,
            'tllr_fc_ot_id': ot.id,
            'tllr_fc_ot_producto_id': self.id,
        }

    def _tllr_fc_movimientos_abiertos(self):
        return self.sudo().move_ids.filtered(
            lambda m: m.state not in ('done', 'cancel'))

    def _tllr_fc_liberar_reserva(self):
        """Cancela los movimientos pendientes (libera lo reservado)."""
        for linea in self:
            abiertos = linea._tllr_fc_movimientos_abiertos()
            if abiertos:
                abiertos._action_cancel()

    def _tllr_fc_consumir(self, cantidad):
        """Valida un movimiento por `cantidad` hacia el consumo del taller."""
        self.ensure_one()
        redondeo = self.uom_id.rounding or 0.001
        movimiento = self.env['stock.move'].sudo().create(
            self._tllr_fc_valores_movimiento(cantidad))
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
                movimiento._action_cancel()
                raise UserError(
                    "Stock insuficiente de «%s»: faltan %s %s en %s." % (
                        nombre, faltante, self.uom_id.name,
                        self._tllr_fc_ubicacion_origen().display_name))
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
        """
        for linea in self:
            if not linea._tllr_fc_mueve_stock():
                linea._tllr_fc_liberar_reserva()
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
            if estado in ('espera', 'proceso'):
                pendiente = linea.cantidad_reservada - max(consumido, linea.cantidad_utilizada)
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
            if vals.get('cantidad_utilizada') and ot.state != 'proceso':
                raise UserError("Solo se registra lo utilizado con la OT en proceso.")
        lineas = super().create(vals_list)
        for linea, vals in zip(lineas, vals_list):
            if vals.get('cantidad_utilizada'):
                linea._tllr_fc_verificar_aprobacion()
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
        if any(campo in vals for campo in CAMPOS_SOLO_SUPERVISOR) and not self._es_supervisor():
            raise AccessError(
                "Solo el supervisor o el administrador de taller pueden cambiar el precio, el "
                "descuento, «No facturar» o «Provisto por el cliente».")
        self._tllr_fc_verificar_ot_editable(self.ot_id)
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
        if {'product_id', 'cantidad_reservada', 'cantidad_utilizada', 'lote_id',
                'provisto_cliente'} & set(vals):
            self._tllr_fc_sincronizar_stock()
        for campo, texto in (('no_facturar', "«No facturar»"), ('provisto_cliente', "«Provisto por el cliente»")):
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

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for linea in self:
            producto = linea.product_id
            linea.precio_unitario = (
                producto.list_price if producto.tllr_fc_uso_taller in USOS_FACTURABLES else 0.0)
            if linea.lote_id and linea.lote_id.product_id != producto:
                linea.lote_id = False
