# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class TllrFcOt(models.Model):
    """Orden de trabajo.

    En la Fase 2 la OT nace de la recepción, en estado En espera, con los
    servicios solicitados como referencia. El resto del ciclo (puestos,
    personal, repuestos, horas, control de calidad, facturación y entrega)
    se incorpora en las fases siguientes.
    """
    _name = 'tllr_fc.ot'
    _description = "Orden de trabajo"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'tllr_fc.mixin.wizard']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(
        string="Número", required=True, readonly=True, copy=False, default="Nuevo")
    company_id = fields.Many2one(
        'res.company', string="Compañía", required=True, index=True,
        default=lambda self: self.env.company)
    state = fields.Selection([
        ('espera', "En espera"),
        ('proceso', "En proceso"),
        ('calidad', "En control de calidad"),
        ('listo', "Listo para entrega"),
        ('entregado', "Entregado"),
        ('cancelada', "Cancelada"),
    ], string="Estado", required=True, default='espera', copy=False,
        tracking=True, index=True)
    tipo = fields.Selection([
        ('cliente', "Cliente"),
        ('interno', "Interno"),
        ('garantia', "Garantía"),
    ], string="Tipo de OT", required=True, default='cliente', tracking=True)
    recepcion_id = fields.Many2one(
        'tllr_fc.recepcion', string="Recepción", required=True, readonly=True,
        copy=False, ondelete='restrict', index=True)
    vehiculo_id = fields.Many2one(
        'tllr_fc.vehiculo', string="Vehículo", required=True, readonly=True,
        ondelete='restrict', check_company=True, index=True)
    partner_id = fields.Many2one(
        'res.partner', string="Cliente a facturar", required=True, readonly=True,
        ondelete='restrict', index=True)
    partner_secundario_id = fields.Many2one(
        'res.partner', string="Contacto secundario", readonly=True, ondelete='restrict')
    combustible_ingreso = fields.Selection([
        ('reserva', "Reserva"),
        ('1_4', "1/4"),
        ('1_2', "1/2"),
        ('3_4', "3/4"),
        ('lleno', "Lleno"),
    ], string="Combustible al ingreso", readonly=True)
    kilometraje_ingreso = fields.Integer(string="Kilometraje al ingreso", readonly=True)
    fecha_ingreso = fields.Datetime(string="Fecha de ingreso", readonly=True)
    fecha_entrega = fields.Datetime(string="Fecha de entrega", readonly=True, copy=False)
    dias_taller = fields.Integer(string="Días en taller", compute='_compute_dias_taller')
    motivo_cancelacion_id = fields.Many2one(
        'tllr_fc.motivo', string="Motivo de cancelación", readonly=True, copy=False,
        domain="[('tipo', '=', 'cancelacion')]", ondelete='restrict')
    servicio_ids = fields.One2many(
        'tllr_fc.ot.servicio', 'ot_id', string="Servicios", copy=False)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', string="Moneda")
    responsable_id = fields.Many2one(
        'tllr_fc.personal', string="Responsable", tracking=True, check_company=True,
        copy=False, help="Una persona por OT. Debe ser distinta del personal asignado a los "
                         "puestos (el supervisor puede autorizar una excepción).")
    requiere_qc = fields.Boolean(
        string="Requiere control de calidad", tracking=True, copy=False,
        help="El supervisor lo marca para exigir el control aunque el ajuste del tipo de OT "
             "no lo pida.")
    puesto_line_ids = fields.One2many(
        'tllr_fc.ot.puesto', 'ot_id', string="Puestos", copy=False)
    puesto_activo_id = fields.Many2one(
        'tllr_fc.puesto', string="Puesto activo", compute='_compute_puesto_activo',
        inverse='_inverse_puesto_activo', store=True, index=True,
        group_expand='_read_group_puesto_activo_id')
    personal_ids = fields.Many2many(
        'tllr_fc.personal', string="Personal asignado", compute='_compute_personal',
        store=True)
    producto_ids = fields.One2many(
        'tllr_fc.ot.producto', 'ot_id', string="Repuestos, insumos y accesorios", copy=False)
    descripcion_trabajos = fields.Text(string="Trabajos realizados")
    hora_ids = fields.One2many('tllr_fc.ot.hora', 'ot_id', string="Horas trabajadas", copy=False)
    herramienta_danada_ids = fields.One2many(
        'tllr_fc.ot.herramienta_danada', 'ot_id', string="Herramientas dañadas", copy=False)
    aprobacion_ids = fields.One2many(
        'tllr_fc.ot.aprobacion', 'ot_id', string="Aprobaciones de adicionales", copy=False)
    control_ids = fields.One2many(
        'tllr_fc.control_calidad', 'ot_id', string="Controles de calidad", copy=False)
    control_count = fields.Integer(string="Controles", compute='_compute_control_count')
    horas_reales = fields.Float(string="Horas reales", compute='_compute_horas')
    costo_horas = fields.Monetary(
        string="Costo de horas", currency_field='currency_id', compute='_compute_horas',
        groups='tllr_fc.group_supervisor')
    aviso_horas = fields.Char(string="Aviso de horas", compute='_compute_horas')
    adicionales_pendientes = fields.Integer(
        string="Adicionales pendientes de aprobación", compute='_compute_adicionales_pendientes',
        store=True)
    detenida = fields.Boolean(string="Detenida", readonly=True, copy=False, tracking=True)
    motivo_detencion_id = fields.Many2one(
        'tllr_fc.motivo', string="Motivo de detención", readonly=True, copy=False,
        domain="[('tipo', '=', 'detencion')]", ondelete='restrict')
    fecha_reanudacion_estimada = fields.Date(
        string="Reanudación estimada", readonly=True, copy=False)
    detenida_desde = fields.Datetime(string="Detenida desde", readonly=True, copy=False)
    dias_detenida = fields.Float(
        string="Días detenida (acumulado)", readonly=True, copy=False, digits=(16, 2))
    dias_detenida_total = fields.Float(
        string="Días detenida", compute='_compute_dias_detenida_total', digits=(16, 2))
    descuento_cliente = fields.Float(
        string="Descuento del cliente (%)", related='partner_id.tllr_fc_descuento')
    total_servicios = fields.Monetary(
        string="Total servicios", currency_field='currency_id', compute='_compute_totales')
    total_productos = fields.Monetary(
        string="Total repuestos e insumos", currency_field='currency_id',
        compute='_compute_totales')
    total = fields.Monetary(
        string="Total", currency_field='currency_id', compute='_compute_totales')
    horas_estandar = fields.Float(string="Horas estándar", compute='_compute_totales')
    servicios_resumen = fields.Char(string="Servicios (resumen)", compute='_compute_resumen')
    servicios_pendientes = fields.Integer(
        string="Servicios pendientes", compute='_compute_resumen')
    tiene_adicionales = fields.Boolean(string="Con adicionales", compute='_compute_resumen')

    @api.depends('fecha_ingreso', 'fecha_entrega', 'state')
    def _compute_dias_taller(self):
        ahora = fields.Datetime.now()
        for ot in self:
            if not ot.fecha_ingreso:
                ot.dias_taller = 0
                continue
            fin = ot.fecha_entrega or ahora
            ot.dias_taller = max((fin - ot.fecha_ingreso).days, 0)

    @api.depends('control_ids')
    def _compute_control_count(self):
        for ot in self:
            ot.control_count = len(ot.control_ids)

    @api.depends('hora_ids.horas', 'hora_ids.fecha', 'hora_ids.personal_id', 'hora_ids.aviso')
    def _compute_horas(self):
        for ot in self:
            horas = ot.hora_ids.sudo()
            ot.horas_reales = sum(horas.mapped('horas'))
            ot.costo_horas = sum(horas.mapped('costo'))
            avisos = [a for a in horas.mapped('aviso') if a]
            ot.aviso_horas = ' '.join(sorted(set(avisos))) if avisos else False

    @api.depends('servicio_ids.state_aprobacion', 'producto_ids.state_aprobacion')
    def _compute_adicionales_pendientes(self):
        for ot in self:
            ot.adicionales_pendientes = (
                len(ot.servicio_ids.filtered(lambda s: s.state_aprobacion == 'pendiente'))
                + len(ot.producto_ids.filtered(lambda p: p.state_aprobacion == 'pendiente')))

    @api.depends('detenida', 'detenida_desde', 'dias_detenida')
    def _compute_dias_detenida_total(self):
        ahora = fields.Datetime.now()
        for ot in self:
            actual = 0.0
            if ot.detenida and ot.detenida_desde:
                actual = (ahora - ot.detenida_desde).total_seconds() / 86400.0
            ot.dias_detenida_total = ot.dias_detenida + actual

    @api.depends('puesto_line_ids.state', 'puesto_line_ids.puesto_id')
    def _compute_puesto_activo(self):
        for ot in self:
            activa = ot.puesto_line_ids.filtered(lambda l: l.state == 'activo')[:1]
            ot.puesto_activo_id = activa.puesto_id

    @api.depends('puesto_line_ids.personal_ids')
    def _compute_personal(self):
        for ot in self:
            ot.personal_ids = ot.puesto_line_ids.personal_ids

    @api.depends('servicio_ids.subtotal', 'servicio_ids.horas_estandar',
                 'producto_ids.subtotal')
    def _compute_totales(self):
        for ot in self:
            ot.total_servicios = sum(ot.servicio_ids.mapped('subtotal'))
            ot.total_productos = sum(ot.producto_ids.mapped('subtotal'))
            ot.total = ot.total_servicios + ot.total_productos
            ot.horas_estandar = sum(ot.servicio_ids.mapped('horas_estandar'))

    @api.depends('servicio_ids.product_id', 'servicio_ids.estado', 'servicio_ids.adicional',
                 'producto_ids.adicional')
    def _compute_resumen(self):
        for ot in self:
            ot.servicios_resumen = ', '.join(
                ot.servicio_ids.filtered(lambda s: s.estado != 'no_realizado')
                .mapped('product_id.name'))
            ot.servicios_pendientes = len(ot.servicio_ids.filtered(
                lambda s: s.estado == 'pendiente'))
            ot.tiene_adicionales = bool(
                ot.servicio_ids.filtered('adicional') or ot.producto_ids.filtered('adicional'))

    @api.model
    def _read_group_puesto_activo_id(self, puestos, domain):
        """El tablero muestra todos los puestos activos como columnas."""
        return self.env['tllr_fc.puesto'].search(
            [('company_id', 'in', self.env.companies.ids)])

    # ------------------------------------------------------------------
    # Tablero: arrastre de tarjetas
    # ------------------------------------------------------------------
    def _inverse_puesto_activo(self):
        """Arrastrar una tarjeta a otra columna del tablero.

        Solo el supervisor, solo con la OT en proceso, solo hacia el puesto que
        sigue y con los servicios del puesto actual terminados. No cambia el
        estado de la OT. Cualquier incumplimiento revierte el movimiento.
        """
        for ot in self:
            actual = ot.puesto_line_ids.filtered(lambda l: l.state == 'activo')[:1]
            destino_puesto = ot.puesto_activo_id
            if destino_puesto == actual.puesto_id:
                continue
            if not self.env.user.has_group('tllr_fc.group_supervisor'):
                raise AccessError(
                    "Solo el supervisor o el administrador de taller pueden mover las OT "
                    "entre puestos.")
            if ot.state != 'proceso':
                raise UserError(
                    "La OT %s no está en proceso: no se puede mover entre puestos." % ot.name)
            if not destino_puesto:
                raise UserError(
                    "La OT %s no puede quedar «Sin puesto». Para volver al puesto anterior "
                    "usá el botón «Retroceder puesto» del formulario de la OT." % ot.name)
            siguiente = ot.puesto_line_ids.filtered(lambda l: l.state == 'pendiente')[:1]
            if not siguiente or siguiente.puesto_id != destino_puesto:
                raise UserError(
                    "La OT %s solo puede pasar al puesto que sigue en su recorrido (%s). "
                    "Para volver a un puesto anterior usá «Retroceder puesto»." % (
                        ot.name, siguiente.puesto_id.name or "ninguno"))
            ot._tllr_fc_verificar_puesto_terminable()
            ot._tllr_fc_avanzar_puesto(avanzar_ot=False)

    # ------------------------------------------------------------------
    # Recorrido por los puestos
    # ------------------------------------------------------------------
    def _tllr_fc_es_supervisor(self):
        return self.env.user.has_group('tllr_fc.group_supervisor')

    def _tllr_fc_verificar_no_detenida(self, accion="continuar"):
        self.ensure_one()
        if self.detenida:
            raise UserError(
                "La OT %s está detenida (%s): no se puede %s hasta reanudarla." % (
                    self.name, self.motivo_detencion_id.name or '', accion))

    def _tllr_fc_verificar_puesto_terminable(self):
        self.ensure_one()
        actual = self.puesto_line_ids.filtered(lambda l: l.state == 'activo')[:1]
        if not actual:
            raise UserError("La OT %s no tiene un puesto activo." % self.name)
        pendientes = actual.servicio_ids.filtered(lambda s: s.estado == 'pendiente')
        if pendientes:
            raise UserError(
                "Faltan servicios por terminar en el puesto «%s»: %s." % (
                    actual.name, ', '.join(pendientes.mapped('product_id.name'))))
        return actual

    def _tllr_fc_avanzar_puesto(self, avanzar_ot=True):
        """Termina el puesto activo y activa el siguiente.

        Si era el último y `avanzar_ot`, la OT sale de proceso.
        """
        self.ensure_one()
        self._tllr_fc_verificar_no_detenida("avanzar de puesto")
        ahora = fields.Datetime.now()
        actual = self.puesto_line_ids.filtered(lambda l: l.state == 'activo')[:1]
        siguiente = self.puesto_line_ids.filtered(lambda l: l.state == 'pendiente')[:1]
        lineas = self.with_context(tllr_fc_permitir_write=True).puesto_line_ids
        actual = lineas.browse(actual.id)
        siguiente = lineas.browse(siguiente.id)
        actual.write({'state': 'terminado', 'fecha_fin': ahora})
        if siguiente:
            siguiente.write({'state': 'activo', 'fecha_inicio': ahora})
            self.message_post(body="Puesto «%s» terminado. Pasa al puesto «%s»." % (
                actual.name, siguiente.name))
            self.producto_ids._tllr_fc_sincronizar_stock()
        else:
            self.message_post(body="Puesto «%s» terminado (último puesto)." % actual.name)
            if avanzar_ot:
                self._tllr_fc_finalizar_recorrido()

    def _tllr_fc_exige_qc(self):
        self.ensure_one()
        return bool(
            self.requiere_qc
            or self.company_id['tllr_fc_qc_%s' % self.tipo])

    def _tllr_fc_finalizar_recorrido(self):
        self.ensure_one()
        sin_cerrar = self.servicio_ids.filtered(lambda s: s.estado == 'pendiente')
        if sin_cerrar:
            raise UserError(
                "No se puede terminar la OT: hay servicios pendientes (%s)." % ', '.join(
                    sin_cerrar.mapped('product_id.name')))
        # Lo reservado y no usado vuelve al stock.
        self.state = 'calidad' if self._tllr_fc_exige_qc() else 'listo'
        self.producto_ids._tllr_fc_sincronizar_stock()
        if self.state == 'calidad':
            control = self._tllr_fc_crear_control()
            self.message_post(body="Todos los puestos terminaron: la OT pasa a control de calidad (%s)."
                              % control.name)
        else:
            self.message_post(body="Todos los puestos terminaron: la OT está lista para entrega.")

    # ------------------------------------------------------------------
    # Control de calidad
    # ------------------------------------------------------------------
    def _tllr_fc_lineas_de_control(self):
        """Comandos para las líneas de un control: un servicio terminado por línea."""
        self.ensure_one()
        comandos = []
        for servicio in self.servicio_ids.filtered(lambda s: s.estado == 'terminado'):
            checks = [(0, 0, {'name': punto.name})
                      for punto in servicio.product_id.product_tmpl_id.sudo().tllr_fc_checklist_ids]
            comandos.append((0, 0, {'ot_servicio_id': servicio.id, 'check_ids': checks}))
        return comandos

    def _tllr_fc_crear_control(self):
        """Devuelve el control en borrador de la OT, creándolo si no existe."""
        self.ensure_one()
        borrador = self.control_ids.filtered(lambda c: c.state == 'borrador')[:1]
        if borrador:
            return borrador
        return self.env['tllr_fc.control_calidad'].sudo().create({
            'ot_id': self.id,
            'responsable_id': self.responsable_id.id,
        })

    def _tllr_fc_devolver_a_proceso(self, servicios):
        """Un control rechazado devuelve la OT a proceso.

        Los servicios rechazados vuelven a pendiente y se reactiva el primer puesto
        que los realiza; los puestos siguientes vuelven a pendiente para repetir el
        recorrido (sus servicios ya terminados no se tocan).
        """
        self.ensure_one()
        lineas = self.puesto_line_ids.sorted(lambda l: (l.sequence, l.id))
        con_rechazo = (servicios.puesto_line_id & lineas).sorted(lambda l: (l.sequence, l.id))
        destino = con_rechazo[:1] or lineas[-1:]
        for servicio in servicios:
            servicio.with_context(tllr_fc_permitir_write=True).write({
                'estado': 'pendiente', 'terminado_por_id': False, 'fecha_terminado': False})
        posicion = list(lineas.ids).index(destino.id) if destino else 0
        for indice, linea in enumerate(lineas):
            ctx = linea.with_context(tllr_fc_permitir_write=True)
            if indice == posicion:
                ctx.write({'state': 'activo', 'fecha_fin': False})
            elif indice > posicion:
                ctx.write({'state': 'pendiente', 'fecha_inicio': False, 'fecha_fin': False})
        self.state = 'proceso'
        self.producto_ids._tllr_fc_sincronizar_stock()

    # ------------------------------------------------------------------
    # Volver atrás en los estados de la OT
    # ------------------------------------------------------------------
    def action_volver_estado(self):
        """Vuelve la OT un estado atrás (supervisor, con motivo).

        - En control de calidad → En proceso (el último puesto vuelve a activo).
        - Listo para entrega → En control de calidad (nuevo control en borrador).
        - En proceso → En espera, solo si todavía no se ejecutó nada.
        Entregada y cancelada no se reabren.
        """
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor o el administrador de taller pueden volver atrás el estado de la OT.")
        destinos = {'calidad': 'proceso', 'listo': 'calidad', 'proceso': 'espera'}
        if self.state not in destinos:
            raise UserError("Una OT %s no se puede reabrir." % (
                "entregada" if self.state == 'entregado' else "cancelada"))
        if self.state == 'proceso':
            self._tllr_fc_verificar_puede_volver_a_espera()
        etiquetas = dict(self._fields['state'].selection)
        if not self.env.context.get('tllr_fc_excepcion'):
            return self._tllr_fc_abrir_excepcion(
                'action_volver_estado', 'supervisor',
                "Volver la OT de «%s» a «%s»." % (
                    etiquetas[self.state], etiquetas[destinos[self.state]]))
        origen = self.state
        if origen == 'calidad':
            borradores = self.control_ids.filtered(lambda c: c.state == 'borrador')
            borradores.sudo().unlink()
            lineas = self.puesto_line_ids.sorted(lambda l: (l.sequence, l.id))
            if lineas:
                lineas[-1].with_context(tllr_fc_permitir_write=True).write(
                    {'state': 'activo', 'fecha_fin': False})
            self.state = 'proceso'
            self.producto_ids._tllr_fc_sincronizar_stock()
        elif origen == 'listo':
            self.state = 'calidad'
            self.producto_ids._tllr_fc_sincronizar_stock()
            self._tllr_fc_crear_control()
        else:
            self.puesto_line_ids.with_context(tllr_fc_permitir_write=True).write(
                {'state': 'pendiente', 'fecha_inicio': False, 'fecha_fin': False})
            self.state = 'espera'
            self.producto_ids._tllr_fc_sincronizar_stock()
        self.message_post(body="La OT volvió de «%s» a «%s». Motivo: %s" % (
            etiquetas[origen], etiquetas[self.state], self.env.context.get('tllr_fc_motivo', '')))
        return True

    def _tllr_fc_verificar_puede_volver_a_espera(self):
        self.ensure_one()
        if (self.servicio_ids.filtered(lambda s: s.estado != 'pendiente')
                or self.hora_ids or self.producto_ids.filtered('cantidad_consumida')):
            raise UserError(
                "No se puede volver a «En espera»: ya hay servicios terminados, horas cargadas "
                "o repuestos consumidos. Usá «Retroceder puesto» para un retrabajo.")

    def action_ver_controles(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Controles de calidad",
            'res_model': 'tllr_fc.control_calidad',
            'view_mode': 'list,form',
            'domain': [('ot_id', '=', self.id)],
        }

    def action_abrir_control(self):
        """Abre el control en borrador de la OT (lo crea si falta)."""
        self.ensure_one()
        if self.state != 'calidad':
            raise UserError("La OT no está en control de calidad.")
        control = self._tllr_fc_crear_control()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'tllr_fc.control_calidad',
            'res_id': control.id,
            'view_mode': 'form',
        }

    # ------------------------------------------------------------------
    # OT detenida
    # ------------------------------------------------------------------
    def action_detener(self):
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor o el administrador de taller pueden detener una OT.")
        if self.state not in ('espera', 'proceso'):
            raise UserError("Solo se puede detener una OT en espera o en proceso.")
        if self.detenida:
            raise UserError("La OT ya está detenida.")
        return {
            'type': 'ir.actions.act_window',
            'name': "Detener OT",
            'res_model': 'tllr_fc.wizard.detener',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_ot_id': self.id},
        }

    def _tllr_fc_detener(self, motivo, fecha_estimada):
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor o el administrador de taller pueden detener una OT.")
        if self.state not in ('espera', 'proceso') or self.detenida:
            raise UserError("La OT no se puede detener en su estado actual.")
        self.write({
            'detenida': True,
            'motivo_detencion_id': motivo.id,
            'fecha_reanudacion_estimada': fecha_estimada,
            'detenida_desde': fields.Datetime.now(),
        })
        self.message_post(body="OT detenida: %s%s." % (
            motivo.name,
            (" (reanudación estimada %s)" % fecha_estimada) if fecha_estimada else ''))

    def _tllr_fc_cerrar_detencion(self):
        """Suma el tramo detenido al acumulado y deja la OT en marcha."""
        for ot in self.filtered('detenida'):
            tramo = 0.0
            if ot.detenida_desde:
                tramo = (fields.Datetime.now() - ot.detenida_desde).total_seconds() / 86400.0
            ot.write({
                'detenida': False,
                'dias_detenida': ot.dias_detenida + tramo,
                'detenida_desde': False,
                'fecha_reanudacion_estimada': False,
            })

    def action_reanudar(self):
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor o el administrador de taller pueden reanudar una OT.")
        if not self.detenida:
            raise UserError("La OT no está detenida.")
        self._tllr_fc_cerrar_detencion()
        self.message_post(body="OT reanudada. Días detenida acumulados: %.2f." % self.dias_detenida)
        return True

    # ------------------------------------------------------------------
    # Trabajos adicionales
    # ------------------------------------------------------------------
    def action_registrar_aprobacion(self):
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor o el administrador de taller registran aprobaciones.")
        if not self.adicionales_pendientes:
            raise UserError("La OT no tiene adicionales pendientes de aprobación.")
        return {
            'type': 'ir.actions.act_window',
            'name': "Registrar aprobación",
            'res_model': 'tllr_fc.wizard.aprobacion',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_ot_id': self.id},
        }

    # ------------------------------------------------------------------
    # Ganchos para los módulos puente (Ventas / Compras)
    # ------------------------------------------------------------------
    def _tllr_fc_requiere_presupuesto(self):
        """Con Ventas activo, las OT de cliente requieren presupuesto confirmado."""
        self.ensure_one()
        return False

    def _tllr_fc_presupuesto_ok_para_iniciar(self):
        self.ensure_one()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == "Nuevo":
                compania = self.env['res.company'].browse(
                    vals.get('company_id') or self.env.company.id)
                vals['name'] = compania._tllr_fc_siguiente_codigo('tllr_fc.ot')
        return super().create(vals_list)

    def write(self, vals):
        if not self._tllr_fc_es_supervisor():
            if 'tipo' in vals:
                raise AccessError(
                    "Solo el supervisor o el administrador de taller pueden cambiar el tipo de OT.")
            if 'requiere_qc' in vals:
                raise AccessError(
                    "Solo el supervisor o el administrador de taller pueden exigir el control de calidad.")
            if 'responsable_id' in vals:
                raise AccessError(
                    "Solo el supervisor o el administrador de taller pueden definir el responsable.")
        if vals.get('requiere_qc') is False:
            for ot in self:
                if ot.company_id['tllr_fc_qc_%s' % (vals.get('tipo') or ot.tipo)]:
                    raise UserError(
                        "No se puede quitar el control de calidad: el ajuste de la compañía lo "
                        "exige para las OT de este tipo.")
        return super().write(vals)

    def action_iniciar(self):
        """En espera → En proceso. Activa el primer puesto."""
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor o el administrador de taller pueden iniciar la OT.")
        if self.state != 'espera':
            raise UserError("Solo se puede iniciar una OT que está en espera.")
        self._tllr_fc_verificar_no_detenida("iniciar")
        if not self.responsable_id:
            raise UserError("Indicá el responsable de la OT antes de iniciarla.")
        lineas = self.puesto_line_ids
        if not lineas:
            raise UserError("Agregá al menos un puesto a la OT antes de iniciarla.")
        sin_personal = lineas.filtered(lambda l: not l.personal_ids)
        if sin_personal:
            raise UserError(
                "Asigná al menos una persona a cada puesto: %s." % ', '.join(sin_personal.mapped('name')))
        sin_puesto = self.servicio_ids.filtered(
            lambda s: not s.puesto_line_id and s.estado != 'no_realizado')
        if sin_puesto:
            raise UserError(
                "Hay servicios sin puesto asignado: %s." % ', '.join(sin_puesto.mapped('product_id.name')))
        if not self.servicio_ids:
            raise UserError("La OT no tiene servicios.")
        if self.responsable_id in self.personal_ids and not self.env.context.get('tllr_fc_excepcion'):
            return self._tllr_fc_abrir_excepcion(
                'action_iniciar', 'supervisor',
                "El responsable «%s» también figura como personal de un puesto." % self.responsable_id.name)
        if (self._tllr_fc_requiere_presupuesto() and not self._tllr_fc_presupuesto_ok_para_iniciar()
                and not self.env.context.get('tllr_fc_excepcion')):
            return self._tllr_fc_abrir_excepcion(
                'action_iniciar', 'supervisor',
                "Iniciar la OT sin el presupuesto confirmado por el cliente.")
        primera = lineas.sorted(lambda l: (l.sequence, l.id))[:1]
        ahora = fields.Datetime.now()
        lineas.with_context(tllr_fc_permitir_write=True).write({'state': 'pendiente'})
        primera.with_context(tllr_fc_permitir_write=True).write(
            {'state': 'activo', 'fecha_inicio': ahora})
        self.state = 'proceso'
        self.producto_ids._tllr_fc_sincronizar_stock()
        self.message_post(body="OT iniciada. Puesto activo: «%s»." % primera.name)
        return True

    def action_terminar_puesto(self):
        """Termina el puesto activo y pasa al siguiente (o cierra el recorrido)."""
        for ot in self:
            if ot.state != 'proceso':
                raise UserError("La OT %s no está en proceso." % ot.name)
            actual = ot._tllr_fc_verificar_puesto_terminable()
            if not actual._tllr_fc_usuario_puede_operar():
                raise AccessError(
                    "Solo el supervisor o el personal asignado al puesto activo pueden terminarlo.")
            ot._tllr_fc_avanzar_puesto()
        return True

    def action_retroceder_puesto(self):
        """Vuelve al puesto anterior para un retrabajo (supervisor, con motivo)."""
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor puede retroceder la OT a un puesto anterior.")
        if self.state != 'proceso':
            raise UserError("Solo se puede retroceder una OT en proceso.")
        lineas = self.puesto_line_ids.sorted(lambda l: (l.sequence, l.id))
        actual = lineas.filtered(lambda l: l.state == 'activo')[:1]
        anteriores = lineas.filtered(lambda l: l.state == 'terminado')
        if not actual or not anteriores:
            raise UserError("La OT no tiene un puesto anterior al que volver.")
        if not self.env.context.get('tllr_fc_excepcion'):
            return self._tllr_fc_abrir_excepcion(
                'action_retroceder_puesto', 'supervisor',
                "Volver al puesto «%s» (retrabajo)." % anteriores[-1].name)
        destino = anteriores[-1]
        ctx = self.with_context(tllr_fc_permitir_write=True)
        actual.with_context(tllr_fc_permitir_write=True).write({'state': 'pendiente', 'fecha_inicio': False})
        destino.with_context(tllr_fc_permitir_write=True).write({'state': 'activo', 'fecha_fin': False})
        # Los servicios terminados del puesto de destino se retrabajan.
        for servicio in destino.servicio_ids.filtered(lambda s: s.estado == 'terminado'):
            servicio.with_context(tllr_fc_permitir_write=True).write({
                'estado': 'pendiente', 'terminado_por_id': False, 'fecha_terminado': False})
        ctx.message_post(body="Retroceso al puesto «%s» para retrabajo. Motivo: %s" % (
            destino.name, self.env.context.get('tllr_fc_motivo', '')))
        self.producto_ids._tllr_fc_sincronizar_stock()
        return True

    def _tllr_fc_cancelar_por_recepcion(self):
        """Cancela la OT en espera cuando se anula su recepción (sin liquidación)."""
        motivo = self.env.ref(
            'tllr_fc.motivo_cancelacion_recepcion_anulada', raise_if_not_found=False)
        for ot in self:
            ot.write({
                'state': 'cancelada',
                'motivo_cancelacion_id': motivo.id if motivo else False,
            })
            ot.producto_ids._tllr_fc_sincronizar_stock()
            ot._tllr_fc_cerrar_detencion()
            ot.message_post(body="OT cancelada porque se anuló su recepción (sin liquidación).")

    def action_ver_recepcion(self):
        self.ensure_one()
        return self.recepcion_id._tllr_fc_accion_formulario()
