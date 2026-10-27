# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

CAMPOS_SOLO_SUPERVISOR = ('precio_unitario', 'descuento', 'no_facturar', 'cobrar_cliente')


class TllrFcOtServicio(models.Model):
    """Servicio de la orden de trabajo: planificación, precio y estado."""
    _name = 'tllr_fc.ot.servicio'
    _description = "Servicio de la orden de trabajo"
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
        'product.product', string="Servicio", required=True,
        domain="[('type', '=', 'service')]", ondelete='restrict')
    descripcion = fields.Char(string="Observación")
    @api.depends('product_id')
    def _compute_display_name(self):
        for servicio in self:
            servicio.display_name = servicio.product_id.display_name or ''

    informe = fields.Text(
        string="Informe del servicio",
        help="Informe de los trabajos realizados en este servicio.")
    garantia_dias = fields.Integer(
        string="Garantía (días)", related='product_id.product_tmpl_id.tllr_fc_garantia_dias')
    garantia_km = fields.Integer(
        string="Garantía (km)", related='product_id.product_tmpl_id.tllr_fc_garantia_km')
    puesto_line_id = fields.Many2one(
        'tllr_fc.ot.puesto', string="Puesto", domain="[('ot_id', '=', ot_id)]",
        ondelete='set null', index=True)
    cantidad = fields.Float(string="Cantidad", default=1.0)
    precio_unitario = fields.Monetary(string="Precio unitario", currency_field='currency_id')
    descuento = fields.Float(string="Desc. (%)")
    no_facturar = fields.Boolean(
        string="No facturar", copy=False,
        help="Cortesía: el servicio se realiza pero no se factura. Solo el supervisor.")
    cobrar_cliente = fields.Boolean(
        string="Cobrar al cliente", copy=False,
        help="Solo en OT de garantía: el servicio no está cubierto por la garantía y se "
             "factura al cliente (requiere su aprobación, como un adicional). Solo el "
             "supervisor.")
    ot_tipo = fields.Selection(related='ot_id.tipo', string="Tipo de OT")
    facturable = fields.Boolean(string="Facturable", compute='_compute_facturable')
    subtotal = fields.Monetary(
        string="Subtotal", currency_field='currency_id', compute='_compute_subtotal')
    producto_ids = fields.One2many(
        'tllr_fc.ot.producto', 'servicio_id', string="Repuestos e insumos vinculados")
    costo_repuestos = fields.Monetary(
        string="Costo de repuestos", currency_field='currency_id',
        compute='_compute_costo_repuestos', groups='tllr_fc.group_supervisor',
        help="Costo de lo consumido de los repuestos e insumos vinculados a este servicio.")
    horas_estandar = fields.Float(
        string="Horas estándar", compute='_compute_horas_estandar')
    costo_estandar = fields.Monetary(
        string="Costo estándar", currency_field='currency_id',
        compute='_compute_costos', groups='tllr_fc.group_supervisor')
    costo_efectivo = fields.Monetary(
        string="Costo efectivo", currency_field='currency_id',
        compute='_compute_costos', groups='tllr_fc.group_supervisor')
    estado = fields.Selection([
        ('pendiente', "Pendiente"),
        ('terminado', "Terminado"),
        ('no_realizado', "No realizado"),
    ], string="Estado", required=True, default='pendiente', copy=False,
        index=True)
    terminado_por_id = fields.Many2one(
        'res.users', string="Terminado por", readonly=True, copy=False)
    fecha_terminado = fields.Datetime(string="Fecha de término", readonly=True, copy=False)
    motivo_no_realizado = fields.Char(string="Motivo (no realizado)", readonly=True, copy=False)
    adicional = fields.Boolean(
        string="Adicional", readonly=True, copy=False,
        help="Agregado después de iniciar la OT.")
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

    # ------------------------------------------------------------------
    # Cálculos
    # ------------------------------------------------------------------
    @api.depends('no_facturar', 'estado', 'cobrar_cliente', 'ot_id.tipo')
    def _compute_facturable(self):
        for servicio in self:
            facturable = not servicio.no_facturar and servicio.estado != 'no_realizado'
            if servicio.ot_id.tipo == 'garantia':
                # En una OT de garantía solo se factura lo marcado «Cobrar al cliente».
                facturable = facturable and servicio.cobrar_cliente
            servicio.facturable = facturable

    @api.depends('cantidad', 'precio_unitario', 'descuento', 'facturable')
    def _compute_subtotal(self):
        for servicio in self:
            if servicio.facturable:
                servicio.subtotal = servicio.cantidad * servicio.precio_unitario * (
                    1 - servicio.descuento / 100.0)
            else:
                servicio.subtotal = 0.0

    @api.depends('product_id.tllr_fc_horas_estandar', 'cantidad', 'estado')
    def _compute_horas_estandar(self):
        for servicio in self:
            if servicio.estado == 'no_realizado':
                servicio.horas_estandar = 0.0
            else:
                servicio.horas_estandar = (
                    servicio.product_id.tllr_fc_horas_estandar * servicio.cantidad)

    def _tllr_fc_costo_estandar_valor(self):
        self.ensure_one()
        if self.estado == 'no_realizado':
            return 0.0
        # En una OT cancelada solo cuesta lo que se llegó a ejecutar.
        if self.ot_id.state == 'cancelada' and self.estado != 'terminado':
            return 0.0
        return self.product_id.sudo().standard_price * self.cantidad

    def _tllr_fc_requiere_horas(self):
        """Un servicio propio exige horas cargadas al terminar. Compras exime a los tercerizados."""
        self.ensure_one()
        return True

    def _tllr_fc_costo_efectivo_servicio(self):
        """Costo efectivo del servicio. El puente de Compras lo reemplaza por el
        costo real de la compra confirmada (servicios tercerizados)."""
        self.ensure_one()
        return self._tllr_fc_costo_estandar_valor()

    @api.depends('producto_ids.costo')
    def _compute_costo_repuestos(self):
        for servicio in self:
            servicio.costo_repuestos = sum(servicio.sudo().producto_ids.mapped('costo'))

    @api.depends('product_id', 'cantidad', 'estado', 'ot_id.state')
    def _compute_costos(self):
        for servicio in self:
            servicio.costo_estandar = servicio._tllr_fc_costo_estandar_valor()
            servicio.costo_efectivo = servicio._tllr_fc_costo_efectivo_servicio()

    @api.constrains('cantidad', 'descuento', 'precio_unitario')
    def _check_valores(self):
        for servicio in self:
            if servicio.cantidad <= 0:
                raise ValidationError("La cantidad del servicio debe ser mayor que cero.")
            if not 0 <= servicio.descuento <= 100:
                raise ValidationError("El descuento debe estar entre 0 y 100.")
            if servicio.precio_unitario < 0:
                raise ValidationError("El precio no puede ser negativo.")

    @api.constrains('cobrar_cliente', 'ot_id')
    def _check_cobrar_cliente(self):
        for servicio in self:
            if servicio.cobrar_cliente and servicio.ot_id.tipo != 'garantia':
                raise ValidationError("«Cobrar al cliente» solo aplica a las OT de garantía.")

    def _tllr_fc_sincronizar_cobro(self):
        """Marcar «Cobrar al cliente» exige la aprobación del cliente (como un adicional)."""
        for servicio in self.filtered(lambda s: s.ot_id.tipo == 'garantia'):
            ctx = servicio.with_context(tllr_fc_permitir_write=True)
            if servicio.cobrar_cliente:
                if servicio.state_aprobacion == 'no_requiere':
                    ctx.write({'state_aprobacion': 'pendiente'})
                if not servicio.precio_unitario:
                    ctx.write({'precio_unitario': servicio.product_id.list_price})
            elif servicio.state_aprobacion != 'no_requiere':
                ctx.write({'state_aprobacion': 'no_requiere', 'aprobacion_id': False})

    @api.constrains('puesto_line_id', 'ot_id')
    def _check_puesto_de_la_ot(self):
        for servicio in self:
            if servicio.puesto_line_id and servicio.puesto_line_id.ot_id != servicio.ot_id:
                raise ValidationError("El puesto del servicio debe pertenecer a la misma OT.")

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _es_supervisor(self):
        return self.env.user.has_group('tllr_fc.group_supervisor')

    def _tllr_fc_verificar_ot_editable(self, ots):
        for ot in ots:
            if ot.state not in ('espera', 'proceso'):
                raise UserError(
                    "La OT %s está en estado «%s»: ya no se pueden modificar sus servicios."
                    % (ot.name, dict(ot._fields['state'].selection)[ot.state]))

    def _tllr_fc_cobro_en_listo(self, vals):
        """«Cobrar al cliente» también se marca con la OT de garantía lista para entrega,
        mientras no se haya cerrado para facturar."""
        return set(vals) <= {'cobrar_cliente'} and all(
            linea.ot_id.tipo == 'garantia' and linea.ot_id.state == 'listo'
            and not linea.ot_id.cerrada_facturar for linea in self)

    def _tllr_fc_verificar_pertenencia(self):
        """El servicio debe figurar entre los trabajos del puesto asignado."""
        for servicio in self.filtered('puesto_line_id'):
            puesto = servicio.puesto_line_id.puesto_id
            if servicio.product_id.product_tmpl_id in puesto.servicio_ids:
                continue
            if not self._es_supervisor():
                raise ValidationError(
                    "El puesto «%s» no realiza el servicio «%s». Elegí otro puesto o pedile "
                    "al supervisor que lo autorice." % (puesto.name, servicio.product_id.display_name))
            servicio.ot_id.message_post(body=(
                "El supervisor %s asignó el servicio «%s» al puesto «%s», que no lo tiene "
                "entre sus tipos de trabajo." % (
                    self.env.user.name, servicio.product_id.display_name, puesto.name)))

    def _tllr_fc_asignar_puesto_automatico(self):
        """Asocia al primer puesto de la OT que realiza el servicio (si no tiene uno)."""
        for servicio in self.filtered(lambda s: not s.puesto_line_id):
            candidatas = servicio.ot_id.puesto_line_ids.filtered(
                lambda l: servicio.product_id.product_tmpl_id in l.puesto_id.servicio_ids)
            # Se prefiere una línea que todavía no tiene servicio (mismo puesto repetido).
            libres = candidatas.filtered(lambda l: not l.servicio_ids)
            elegida = (libres or candidatas)[:1]
            if elegida:
                servicio.puesto_line_id = elegida

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        es_supervisor = self._es_supervisor()
        ots = self.env['tllr_fc.ot'].browse([v['ot_id'] for v in vals_list if v.get('ot_id')])
        self._tllr_fc_verificar_ot_editable(ots)
        productos = self.env['product.product']
        for vals in vals_list:
            ot = self.env['tllr_fc.ot'].browse(vals.get('ot_id'))
            producto = productos.browse(vals.get('product_id'))
            if not es_supervisor:
                for campo in CAMPOS_SOLO_SUPERVISOR:
                    vals.pop(campo, None)
            if 'precio_unitario' not in vals:
                vals['precio_unitario'] = producto.list_price
            if 'descuento' not in vals:
                vals['descuento'] = ot.partner_id.tllr_fc_descuento
            if ot.state != 'espera':
                vals['adicional'] = True
                vals['state_aprobacion'] = 'pendiente' if ot.tipo == 'cliente' else 'no_requiere'
            if vals.get('cobrar_cliente') and ot.tipo == 'garantia':
                vals['state_aprobacion'] = 'pendiente'
        servicios = super().create(vals_list)
        servicios._tllr_fc_asignar_puesto_automatico()
        servicios._tllr_fc_verificar_pertenencia()
        return servicios

    def write(self, vals):
        if not self.env.context.get('tllr_fc_permitir_write'):
            if any(campo in vals for campo in CAMPOS_SOLO_SUPERVISOR) and not self._es_supervisor():
                raise AccessError(
                    "Solo el supervisor o el administrador de taller pueden cambiar el precio, "
                    "el descuento o marcar «No facturar».")
            for campo in ('estado', 'terminado_por_id', 'fecha_terminado',
                          'motivo_no_realizado', 'adicional', 'state_aprobacion',
                          'aprobacion_id'):
                if campo in vals:
                    raise UserError(
                        "El estado del servicio se cambia con los botones de la OT.")
            if set(vals) <= {'informe'}:
                # El informe se puede completar hasta la entrega.
                for ot in self.ot_id:
                    if ot.state in ('entregado', 'cancelada'):
                        raise UserError("La OT %s ya está cerrada." % ot.name)
            elif not self._tllr_fc_cobro_en_listo(vals):
                self._tllr_fc_verificar_ot_editable(self.ot_id)
        if 'puesto_line_id' in vals:
            for servicio in self:
                if vals['puesto_line_id'] != servicio.puesto_line_id.id and servicio.puesto_line_id \
                        and self.env['tllr_fc.ot.hora'].sudo().search_count(
                            [('servicio_id', '=', servicio.id)]):
                    raise UserError(
                        "El servicio «%s» tiene horas cargadas: no se puede cambiar de puesto."
                        % servicio.product_id.display_name)
        resultado = super().write(vals)
        if 'puesto_line_id' in vals:
            self._tllr_fc_verificar_pertenencia()
            self.producto_ids._tllr_fc_alinear_puesto_con_servicio()
        if 'cobrar_cliente' in vals:
            self._tllr_fc_sincronizar_cobro()
            for servicio in self:
                servicio.ot_id.message_post(body="%s: «Cobrar al cliente» %s por %s." % (
                    servicio.product_id.display_name,
                    "activado" if servicio.cobrar_cliente else "desactivado", self.env.user.name))
        if 'no_facturar' in vals:
            for servicio in self:
                servicio.ot_id.message_post(body="%s: «No facturar» %s por %s." % (
                    servicio.product_id.display_name,
                    "activado" if servicio.no_facturar else "desactivado", self.env.user.name))
        return resultado

    @api.ondelete(at_uninstall=False)
    def _unlink_validar(self):
        self._tllr_fc_verificar_ot_editable(self.ot_id)
        for servicio in self:
            if servicio.estado == 'terminado':
                raise UserError(
                    "No se puede eliminar el servicio «%s» porque ya está terminado."
                    % servicio.product_id.display_name)

    # ------------------------------------------------------------------
    # Acciones de estado
    # ------------------------------------------------------------------
    def action_terminar(self):
        ahora = fields.Datetime.now()
        for servicio in self:
            ot = servicio.ot_id
            if ot.state != 'proceso':
                raise UserError("Solo se pueden terminar servicios de una OT en proceso.")
            if servicio.estado == 'terminado':
                continue
            ot._tllr_fc_verificar_no_detenida("terminar servicios")
            servicio._tllr_fc_verificar_aprobacion()
            linea = servicio.puesto_line_id
            if not linea or linea.state != 'activo':
                raise UserError(
                    "El servicio «%s» no pertenece al puesto activo de la OT."
                    % servicio.product_id.display_name)
            if not linea._tllr_fc_usuario_puede_operar():
                raise AccessError(
                    "Solo el supervisor o el personal asignado al puesto activo pueden "
                    "terminar sus servicios.")
            servicio.with_context(tllr_fc_permitir_write=True).write({
                'estado': 'terminado',
                'terminado_por_id': self.env.user.id,
                'fecha_terminado': ahora,
                'motivo_no_realizado': False,
            })
            ot.message_post(body="Servicio terminado: %s (%s)." % (
                servicio.product_id.display_name, self.env.user.name))
        return True

    def _tllr_fc_verificar_aprobacion(self):
        """Un adicional pendiente de aprobación no se ejecuta si la aprobación es obligatoria."""
        self.ensure_one()
        if (self.state_aprobacion == 'pendiente'
                and self.company_id.tllr_fc_aprobacion_adicional == 'obligatoria'):
            raise UserError(
                "«%s» es un trabajo adicional pendiente de aprobación del cliente. El "
                "supervisor debe registrar la aprobación o autorizar la ejecución sin ella."
                % self.product_id.display_name)

    def action_autorizar_sin_aprobacion(self):
        """El supervisor autoriza ejecutar el adicional sin la aprobación del cliente."""
        if not self._es_supervisor():
            raise AccessError("Solo el supervisor puede autorizar la ejecución sin aprobación.")
        self.ensure_one()
        if self.state_aprobacion != 'pendiente':
            raise UserError("La línea no está pendiente de aprobación.")
        if not self.env.context.get('tllr_fc_excepcion'):
            return self._tllr_fc_abrir_excepcion(
                'action_autorizar_sin_aprobacion', 'supervisor',
                "Ejecutar «%s» sin la aprobación del cliente." % self.product_id.display_name)
        self.with_context(tllr_fc_permitir_write=True).state_aprobacion = 'autorizado'
        return True

    def action_no_realizado(self):
        if not self._es_supervisor():
            raise AccessError("Solo el supervisor puede marcar un servicio como no realizado.")
        if len(self) == 1 and not self.env.context.get('tllr_fc_excepcion'):
            return self._tllr_fc_abrir_excepcion(
                'action_no_realizado', 'supervisor',
                "Marcar el servicio «%s» como NO realizado (no se factura)."
                % self.product_id.display_name)
        motivo = (self.env.context.get('tllr_fc_motivo') or '').strip()
        if not motivo:
            raise UserError("Indicá el motivo por el que el servicio no se realizó.")
        for servicio in self:
            if servicio.ot_id.state not in ('espera', 'proceso'):
                raise UserError("La OT ya no admite cambios en sus servicios.")
            servicio.with_context(tllr_fc_permitir_write=True).write({
                'estado': 'no_realizado',
                'motivo_no_realizado': motivo,
                'terminado_por_id': False,
                'fecha_terminado': False,
            })
            servicio.ot_id.message_post(body="Servicio NO realizado: %s. Motivo: %s" % (
                servicio.product_id.display_name, motivo))
        return True

    def action_reabrir(self):
        """Devuelve el servicio a Pendiente (solo supervisor, con la OT sin controlar)."""
        if not self._es_supervisor():
            raise AccessError("Solo el supervisor puede volver un servicio a pendiente.")
        for servicio in self:
            if servicio.ot_id.state not in ('espera', 'proceso'):
                raise UserError("La OT ya no admite cambios en sus servicios.")
            if servicio.puesto_line_id.state == 'terminado':
                raise UserError(
                    "El puesto del servicio ya terminó. Para un retrabajo usá «Retroceder "
                    "puesto» en la OT.")
            servicio.with_context(tllr_fc_permitir_write=True).write({
                'estado': 'pendiente',
                'terminado_por_id': False,
                'fecha_terminado': False,
                'motivo_no_realizado': False,
            })
            servicio.ot_id.message_post(body="Servicio vuelto a pendiente: %s (%s)." % (
                servicio.product_id.display_name, self.env.user.name))
        return True
