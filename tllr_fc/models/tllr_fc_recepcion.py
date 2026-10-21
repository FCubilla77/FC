# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# Campos de mensajería que pueden cambiar aunque la recepción esté cerrada.
CAMPOS_LIBRES = {
    'message_follower_ids', 'message_ids', 'message_main_attachment_id',
    'activity_ids', 'message_partner_ids',
}
ESTADOS_OT_ABIERTA = ('espera', 'proceso', 'calidad', 'listo')


class TllrFcRecepcion(models.Model):
    _name = 'tllr_fc.recepcion'
    _description = "Recepción de vehículo"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'tllr_fc.mixin.wizard']
    _order = 'fecha desc, id desc'
    _check_company_auto = True

    name = fields.Char(
        string="Número", required=True, readonly=True, copy=False, default="Nuevo")
    fecha = fields.Datetime(
        string="Fecha", required=True, default=lambda self: fields.Datetime.now(),
        copy=False, tracking=True)
    vehiculo_id = fields.Many2one(
        'tllr_fc.vehiculo', string="Vehículo", required=True, tracking=True,
        ondelete='restrict', check_company=True, index=True)
    partner_id = fields.Many2one(
        'res.partner', string="Contacto principal", required=True, tracking=True,
        ondelete='restrict', index=True,
        help="Cliente a facturar. Al elegir el vehículo se completa con su propietario.")
    partner_secundario_id = fields.Many2one(
        'res.partner', string="Contacto secundario", ondelete='restrict',
        help="Quien entrega el vehículo.")
    turno_id = fields.Many2one(
        'tllr_fc.turno', string="Turno", copy=False, ondelete='restrict',
        check_company=True, index=True,
        domain="[('partner_id', '=', partner_id), ('state', 'in', ('agendado', 'confirmado'))]")
    servicio_ids = fields.One2many(
        'tllr_fc.recepcion.servicio', 'recepcion_id', string="Servicios solicitados",
        copy=False)
    kilometraje = fields.Integer(string="Kilometraje", required=True, default=0, copy=True)
    combustible_nivel = fields.Selection([
        ('reserva', "Reserva"),
        ('1_4', "1/4"),
        ('1_2', "1/2"),
        ('3_4', "3/4"),
        ('lleno', "Lleno"),
    ], string="Nivel de combustible")
    item_ids = fields.One2many(
        'tllr_fc.recepcion.item', 'recepcion_id', string="Inventario del vehículo", copy=True)
    observaciones = fields.Text(string="Observaciones / daños visibles", copy=False)
    tipo_ot_propuesto = fields.Selection([
        ('cliente', "Cliente"),
        ('interno', "Interno"),
        ('garantia', "Garantía"),
    ], string="Tipo de OT propuesto", default='cliente',
        help="Lo confirma el supervisor en la OT.")
    ot_origen_id = fields.Many2one(
        'tllr_fc.ot', string="OT original (garantía)", copy=False, ondelete='restrict',
        domain="[('state', '=', 'entregado'), ('tipo', '=', 'cliente'), ('vehiculo_id', '=', vehiculo_id)]",
        help="OT de cliente entregada que originó el reclamo de garantía.")
    garantia_elegida_ids = fields.Many2many(
        'tllr_fc.garantia', 'tllr_fc_recepcion_garantia_rel', 'recepcion_id', 'garantia_id',
        string="Garantías reclamadas (ítems)", copy=False,
        domain="[('ot_id', '=', ot_origen_id), ('reclamo_ot_id', '=', False)]",
        help="Servicios o productos de la OT original por los que se reclama la garantía.")
    garantia_reclamo_ids = fields.One2many(
        'tllr_fc.garantia', 'reclamo_recepcion_id', string="Garantías reclamadas", readonly=True)
    ot_id = fields.Many2one(
        'tllr_fc.ot', string="Orden de trabajo", readonly=True, copy=False,
        ondelete='restrict')
    state = fields.Selection([
        ('borrador', "Borrador"),
        ('confirmada', "Confirmada"),
        ('cancelada', "Cancelada"),
    ], string="Estado", required=True, default='borrador', copy=False,
        tracking=True, index=True)
    company_id = fields.Many2one(
        'res.company', string="Compañía", required=True, index=True,
        default=lambda self: self.env.company)

    # ------------------------------------------------------------------
    # Edición
    # ------------------------------------------------------------------
    def _tllr_fc_asegurar_editable(self):
        """Una recepción confirmada o anulada no se edita."""
        if self.env.context.get('tllr_fc_permitir_write'):
            return
        for recepcion in self:
            if recepcion.state != 'borrador':
                raise UserError(
                    "La recepción %s está %s y no se puede editar. Anulala y registrá "
                    "una nueva, o usá «Duplicar»." % (
                        recepcion.name,
                        'confirmada' if recepcion.state == 'confirmada' else 'anulada'))

    def write(self, vals):
        if set(vals) - CAMPOS_LIBRES:
            self._tllr_fc_asegurar_editable()
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_solo_borrador(self):
        for recepcion in self:
            if recepcion.state != 'borrador':
                raise UserError(
                    "Solo se pueden borrar recepciones en borrador; anulá la recepción %s."
                    % recepcion.name)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == "Nuevo":
                compania = self.env['res.company'].browse(
                    vals.get('company_id') or self.env.company.id)
                vals['name'] = compania._tllr_fc_siguiente_codigo('tllr_fc.recepcion')
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Restricciones
    # ------------------------------------------------------------------
    @api.constrains('kilometraje')
    def _check_kilometraje(self):
        for recepcion in self:
            if recepcion.kilometraje < 0:
                raise ValidationError("El kilometraje no puede ser negativo.")

    @api.constrains('turno_id', 'state')
    def _check_turno_unico(self):
        for recepcion in self.filtered(lambda r: r.turno_id and r.state != 'cancelada'):
            repetida = self.search_count([
                ('id', '!=', recepcion.id),
                ('turno_id', '=', recepcion.turno_id.id),
                ('state', '!=', 'cancelada'),
            ])
            if repetida:
                raise ValidationError(
                    "El turno %s ya está ligado a otra recepción." % recepcion.turno_id.name)

    @api.constrains('ot_id')
    def _check_ot_unica(self):
        for recepcion in self.filtered('ot_id'):
            if self.search_count([
                    ('id', '!=', recepcion.id), ('ot_id', '=', recepcion.ot_id.id)]):
                raise ValidationError("Una OT solo puede pertenecer a una recepción.")

    # ------------------------------------------------------------------
    # Onchange
    # ------------------------------------------------------------------
    @api.onchange('tipo_ot_propuesto')
    def _onchange_tipo_ot_propuesto(self):
        if self.tipo_ot_propuesto != 'garantia':
            self.ot_origen_id = False
            self.garantia_elegida_ids = False

    @api.onchange('ot_origen_id')
    def _onchange_ot_origen_id(self):
        self.garantia_elegida_ids = self.garantia_elegida_ids.filtered(
            lambda g: g.ot_id == self.ot_origen_id)

    @api.onchange('garantia_elegida_ids')
    def _onchange_garantia_elegida_ids(self):
        """Los servicios a repetir salen de las garantías elegidas."""
        if not self.garantia_elegida_ids:
            return
        servicios = self.garantia_elegida_ids.product_id.filtered(lambda p: p.type == 'service')
        if not servicios:
            servicios = self.ot_origen_id.servicio_ids.filtered(
                lambda s: s.estado == 'terminado').product_id
        self.servicio_ids = [Command.clear()] + [Command.create({
            'product_id': p.id,
            'observacion': "Garantía de %s" % self.ot_origen_id.name}) for p in servicios]

    @api.constrains('garantia_elegida_ids', 'ot_origen_id')
    def _check_garantia_elegida(self):
        for recepcion in self.filtered('garantia_elegida_ids'):
            if recepcion.garantia_elegida_ids.filtered(
                    lambda g: g.ot_id != recepcion.ot_origen_id):
                raise ValidationError(
                    "Las garantías elegidas deben pertenecer a la OT original.")

    @api.constrains('ot_origen_id', 'tipo_ot_propuesto', 'vehiculo_id')
    def _check_ot_origen(self):
        for recepcion in self.filtered('ot_origen_id'):
            origen = recepcion.ot_origen_id
            if recepcion.tipo_ot_propuesto != 'garantia':
                raise ValidationError(
                    "La OT original solo se indica en recepciones de tipo Garantía.")
            if origen.tipo != 'cliente' or origen.state != 'entregado':
                raise ValidationError(
                    "La OT original %s debe ser una OT de cliente entregada." % origen.name)
            if origen.vehiculo_id != recepcion.vehiculo_id:
                raise ValidationError(
                    "La OT original %s corresponde a otro vehículo." % origen.name)

    @api.onchange('vehiculo_id')
    def _onchange_vehiculo_id(self):
        if self.vehiculo_id:
            self.partner_id = self.vehiculo_id.partner_id
            if not self.kilometraje:
                self.kilometraje = self.vehiculo_id.kilometraje
            if self.turno_id and self.turno_id.partner_id != self.partner_id:
                self.turno_id = False

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.turno_id and self.turno_id.partner_id != self.partner_id:
            self.turno_id = False

    @api.onchange('turno_id')
    def _onchange_turno_id(self):
        turno = self.turno_id
        if not turno:
            return
        if not self.partner_id:
            self.partner_id = turno.partner_id
        if not self.vehiculo_id:
            self.vehiculo_id = turno.vehiculo_id
        elif self.vehiculo_id != turno.vehiculo_id:
            return {'warning': {
                'title': "El vehículo no coincide con el turno",
                'message': "El turno %s es del vehículo %s y la recepción es del vehículo %s. "
                           "Podés continuar si corresponde." % (
                               turno.name, turno.vehiculo_id.display_name,
                               self.vehiculo_id.display_name),
            }}
        if not self.servicio_ids:
            self.servicio_ids = [(0, 0, {
                'product_id': linea.product_id.id,
                'observacion': linea.observacion,
            }) for linea in turno.servicio_ids]

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def _tllr_fc_accion_formulario(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'tllr_fc.recepcion',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_cargar_items(self):
        """Agrega una línea por cada ítem activo del catálogo que aún no esté cargado."""
        self.ensure_one()
        if self.state != 'borrador':
            raise UserError("Solo se pueden cargar ítems en una recepción en borrador.")
        cargados = self.item_ids.item_id
        catalogo = self.env['tllr_fc.item_inventario'].search([
            ('id', 'not in', cargados.ids),
        ])
        if catalogo:
            self.write({'item_ids': [(0, 0, {
                'item_id': item.id,
                'name': item.name,
            }) for item in catalogo]})
        return True

    def _tllr_fc_ots_abiertas(self):
        self.ensure_one()
        return self.env['tllr_fc.ot'].search([
            ('vehiculo_id', '=', self.vehiculo_id.id),
            ('state', 'in', ESTADOS_OT_ABIERTA),
        ])

    def _tllr_fc_validar_confirmacion(self):
        self.ensure_one()
        if self.state != 'borrador':
            raise UserError("Solo se puede confirmar una recepción en borrador.")
        if not self.servicio_ids:
            raise UserError("Cargá al menos un servicio solicitado.")
        if not self.item_ids:
            raise UserError(
                "Cargá el inventario del vehículo (botón «Cargar ítems del catálogo») "
                "y confirmá cada ítem.")
        if (self.tipo_ot_propuesto == 'garantia' and self.ot_origen_id
                and not (self.garantia_elegida_ids | self.garantia_reclamo_ids)):
            raise UserError(
                "Elegí el servicio o producto de la OT %s por el que se reclama la garantía."
                % self.ot_origen_id.name)
        sin_confirmar = self.item_ids.filtered(lambda i: not i.presente)
        if sin_confirmar:
            raise UserError(
                "Indicá si está presente cada ítem del inventario. Faltan: %s." %
                ', '.join(sin_confirmar.mapped('name')))

    def action_confirmar(self):
        """Confirma la recepción y genera la OT en espera.

        Antes aplica las verificaciones con excepción o advertencia:
        - kilometraje menor al último registrado: el usuario de taller necesita la
          autorización de un supervisor; el supervisor recibe una advertencia;
        - vehículo con OT abierta: advertencia.
        """
        self.ensure_one()
        self._tllr_fc_validar_confirmacion()
        contexto = self.env.context
        es_supervisor = self.env.user.has_group('tllr_fc.group_supervisor')
        km_anterior = self.vehiculo_id.kilometraje
        km_menor = self.kilometraje < km_anterior
        if km_menor and not es_supervisor and not contexto.get('tllr_fc_excepcion'):
            return self._tllr_fc_abrir_excepcion(
                'action_confirmar', 'supervisor',
                "El kilometraje ingresado (%s) es menor al último registrado del "
                "vehículo (%s). Un supervisor debe autorizar la recepción." % (
                    self.kilometraje, km_anterior))
        if not contexto.get('tllr_fc_advertencia_ok'):
            avisos = []
            if km_menor and es_supervisor:
                avisos.append(
                    "El kilometraje ingresado (%s) es menor al último registrado (%s)."
                    % (self.kilometraje, km_anterior))
            abiertas = self._tllr_fc_ots_abiertas()
            if abiertas:
                avisos.append(
                    "El vehículo ya tiene una OT abierta: %s." % ', '.join(abiertas.mapped('name')))
            if avisos:
                return self._tllr_fc_abrir_advertencia(
                    'action_confirmar', '\n'.join(avisos))
        self._tllr_fc_confirmar()
        return True

    def _tllr_fc_preparar_ot(self):
        self.ensure_one()
        return {
            'recepcion_id': self.id,
            'company_id': self.company_id.id,
            'tipo': self.tipo_ot_propuesto or 'cliente',
            'ot_origen_id': self.ot_origen_id.id if self.tipo_ot_propuesto == 'garantia' else False,
            'vehiculo_id': self.vehiculo_id.id,
            'partner_id': self.partner_id.id,
            'partner_secundario_id': self.partner_secundario_id.id,
            'combustible_ingreso': self.combustible_nivel,
            'kilometraje_ingreso': self.kilometraje,
            'fecha_ingreso': self.fecha,
            'servicio_ids': [(0, 0, {
                'product_id': linea.product_id.id,
                'descripcion': linea.observacion,
            }) for linea in self.servicio_ids],
        }

    def _tllr_fc_confirmar(self):
        self.ensure_one()
        ot = self.env['tllr_fc.ot'].create(self._tllr_fc_preparar_ot())
        self.vehiculo_id.write({'kilometraje': self.kilometraje})
        self.with_context(tllr_fc_permitir_write=True).write({
            'state': 'confirmada',
            'ot_id': ot.id,
        })
        garantias = (self.garantia_elegida_ids | self.garantia_reclamo_ids).sudo()
        if garantias:
            garantias.write({'reclamo_recepcion_id': self.id, 'reclamo_ot_id': ot.id})
        if self.turno_id:
            self.turno_id.write({'state': 'recibido'})
            self.turno_id.message_post(
                body="Vehículo recibido: recepción %s." % self._get_html_link())
        self.message_post(
            body="Recepción confirmada. Se generó la OT %s (En espera)." % ot._get_html_link())
        return ot

    def action_cancelar(self):
        """Anula la recepción. Si la OT sigue en espera, se cancela con ella."""
        for recepcion in self:
            if recepcion.state == 'cancelada':
                continue
            ot = recepcion.ot_id
            if recepcion.state == 'confirmada' and ot and ot.state not in ('espera', 'cancelada'):
                raise UserError(
                    "La OT %s ya está en proceso o posterior, por lo que la recepción no se "
                    "anula por sí sola. Cancelá primero la OT." % ot.name)
            if ot and ot.state == 'espera':
                ot._tllr_fc_cancelar_por_recepcion()
            recepcion.with_context(tllr_fc_permitir_write=True).write({'state': 'cancelada'})
            turno = recepcion.turno_id
            if turno and turno.state == 'recibido':
                turno.write({'state': 'confirmado'})
                turno.message_post(
                    body="Recepción %s anulada: el turno vuelve a Confirmado."
                    % recepcion._get_html_link())
            recepcion.message_post(body="Recepción anulada.")
        return True

    def action_duplicar(self):
        """Copia la recepción para registrar otros trabajos del mismo vehículo."""
        self.ensure_one()
        nueva = self.copy()
        return nueva._tllr_fc_accion_formulario()

    def action_imprimir(self):
        self.ensure_one()
        return self.env.ref('tllr_fc.action_report_recepcion').report_action(self)

    def action_ver_ot(self):
        self.ensure_one()
        if not self.ot_id:
            raise UserError("La recepción todavía no generó una OT.")
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'tllr_fc.ot',
            'res_id': self.ot_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def copy_data(self, default=None):
        default = dict(default or {})
        default.setdefault('fecha', fields.Datetime.now())
        return super().copy_data(default)
