# -*- coding: utf-8 -*-
from datetime import timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError

ESTADOS_PENDIENTES = ('agendado', 'confirmado')


class TllrFcTurno(models.Model):
    _name = 'tllr_fc.turno'
    _description = "Turno"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha_hora desc, id desc'
    _check_company_auto = True

    name = fields.Char(
        string="Número", required=True, readonly=True, copy=False, default="Nuevo")
    fecha_hora = fields.Datetime(
        string="Fecha y hora", required=True, tracking=True,
        default=lambda self: fields.Datetime.now())
    duracion = fields.Float(
        string="Duración estimada (h)", compute='_compute_duracion',
        store=True, readonly=False,
        help="Suma de las horas estándar de los servicios; se puede ajustar.")
    fecha_fin = fields.Datetime(
        string="Fin estimado", compute='_compute_fecha_fin', store=True)
    partner_id = fields.Many2one(
        'res.partner', string="Cliente", required=True, tracking=True,
        ondelete='restrict', index=True)
    vehiculo_id = fields.Many2one(
        'tllr_fc.vehiculo', string="Vehículo", required=True, tracking=True,
        ondelete='restrict', check_company=True,
        domain="[('partner_id', '=', partner_id)]")
    servicio_ids = fields.One2many(
        'tllr_fc.turno.servicio', 'turno_id', string="Servicios solicitados", copy=True)
    puesto_id = fields.Many2one(
        'tllr_fc.puesto', string="Puesto sugerido", check_company=True, tracking=True,
        ondelete='restrict')
    state = fields.Selection([
        ('agendado', "Agendado"),
        ('confirmado', "Confirmado"),
        ('recibido', "Recibido"),
        ('no_asistio', "No asistió"),
        ('cancelado', "Cancelado"),
    ], string="Estado", required=True, default='agendado', copy=False,
        tracking=True, index=True)
    recepcion_ids = fields.One2many(
        'tllr_fc.recepcion', 'turno_id', string="Recepciones", copy=False)
    recepcion_id = fields.Many2one(
        'tllr_fc.recepcion', string="Recepción", compute='_compute_recepcion_id')
    vencido = fields.Boolean(
        string="Vencido", compute='_compute_vencido', search='_search_vencido')
    aviso_superposicion = fields.Char(
        string="Aviso de superposición", compute='_compute_aviso_superposicion')
    color_calendario = fields.Integer(
        string="Color", compute='_compute_color_calendario')
    fecha_hora_texto = fields.Char(
        string="Fecha y hora (texto)", compute='_compute_fecha_hora_texto')
    company_id = fields.Many2one(
        'res.company', string="Compañía", required=True, index=True,
        default=lambda self: self.env.company)

    # ------------------------------------------------------------------
    # Cálculos
    # ------------------------------------------------------------------
    @api.depends('servicio_ids.product_id')
    def _compute_duracion(self):
        for turno in self:
            turno.duracion = sum(
                turno.servicio_ids.product_id.product_tmpl_id.mapped('tllr_fc_horas_estandar'))

    @api.depends('fecha_hora', 'duracion')
    def _compute_fecha_fin(self):
        for turno in self:
            if turno.fecha_hora:
                turno.fecha_fin = turno.fecha_hora + timedelta(hours=turno.duracion or 1.0)
            else:
                turno.fecha_fin = False

    @api.depends('recepcion_ids.state')
    def _compute_recepcion_id(self):
        for turno in self:
            vigentes = turno.recepcion_ids.filtered(lambda r: r.state != 'cancelada')
            turno.recepcion_id = vigentes[:1]

    @api.depends('fecha_hora', 'state')
    def _compute_vencido(self):
        ahora = fields.Datetime.now()
        for turno in self:
            turno.vencido = bool(
                turno.fecha_hora and turno.fecha_hora < ahora
                and turno.state in ESTADOS_PENDIENTES)

    def _search_vencido(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise UserError("Operación de búsqueda no soportada para «Vencido».")
        buscar_vencidos = (operator == '=') == value
        dominio = [
            ('fecha_hora', '<', fields.Datetime.now()),
            ('state', 'in', list(ESTADOS_PENDIENTES)),
        ]
        if buscar_vencidos:
            return dominio
        return ['!', '&'] + dominio

    @api.depends('fecha_hora', 'fecha_fin', 'puesto_id', 'state')
    def _compute_aviso_superposicion(self):
        for turno in self:
            aviso = False
            if (turno.puesto_id and turno.fecha_hora and turno.fecha_fin
                    and turno.state in ESTADOS_PENDIENTES):
                dominio = [
                    ('puesto_id', '=', turno.puesto_id.id),
                    ('state', 'in', list(ESTADOS_PENDIENTES)),
                    ('fecha_hora', '<', turno.fecha_fin),
                    ('fecha_fin', '>', turno.fecha_hora),
                ]
                if turno._origin.id:
                    dominio.append(('id', '!=', turno._origin.id))
                otros = self.env['tllr_fc.turno'].search(dominio, limit=3)
                if otros:
                    aviso = "El puesto sugerido ya tiene turno en ese horario: %s." % (
                        ', '.join(otros.mapped('name')))
            turno.aviso_superposicion = aviso

    @api.depends('state', 'vencido')
    def _compute_color_calendario(self):
        colores = {
            'agendado': 4,      # azul
            'confirmado': 10,   # verde
            'recibido': 7,      # gris azulado
            'no_asistio': 9,    # violeta
            'cancelado': 0,
        }
        for turno in self:
            turno.color_calendario = 1 if turno.vencido else colores.get(turno.state, 0)

    @api.depends('fecha_hora', 'partner_id.tz')
    def _compute_fecha_hora_texto(self):
        for turno in self:
            if not turno.fecha_hora:
                turno.fecha_hora_texto = False
                continue
            zona = pytz.timezone(
                turno.partner_id.tz or self.env.user.tz or 'America/Asuncion')
            local = pytz.utc.localize(turno.fecha_hora).astimezone(zona)
            turno.fecha_hora_texto = local.strftime('%d/%m/%Y %H:%M')

    # ------------------------------------------------------------------
    # Onchange
    # ------------------------------------------------------------------
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.vehiculo_id and self.vehiculo_id.partner_id != self.partner_id:
            self.vehiculo_id = False

    @api.onchange('servicio_ids')
    def _onchange_servicio_ids(self):
        """Propone el puesto que realiza la mayor cantidad de los servicios pedidos."""
        if self.puesto_id or not self.servicio_ids:
            return
        plantillas = self.servicio_ids.product_id.product_tmpl_id
        puestos = self.env['tllr_fc.puesto'].search([('servicio_ids', 'in', plantillas.ids)])
        if puestos:
            self.puesto_id = max(puestos, key=lambda p: len(p.servicio_ids & plantillas))

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == "Nuevo":
                compania = self.env['res.company'].browse(
                    vals.get('company_id') or self.env.company.id)
                vals['name'] = compania._tllr_fc_siguiente_codigo('tllr_fc.turno')
        return super().create(vals_list)

    @api.ondelete(at_uninstall=False)
    def _unlink_si_sin_recepcion(self):
        for turno in self:
            if turno.recepcion_ids:
                raise UserError(
                    "El turno %s tiene recepciones registradas; cancelalo en lugar de borrarlo."
                    % turno.name)

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_confirmar(self):
        for turno in self:
            if turno.state != 'agendado':
                raise UserError("Solo se puede confirmar un turno agendado.")
            turno.state = 'confirmado'
            turno.message_post(body="Turno confirmado con el cliente.")
        return True

    def action_recibir(self):
        """Crea la recepción en borrador con los datos del turno."""
        self.ensure_one()
        if self.state not in ESTADOS_PENDIENTES:
            raise UserError("Solo se puede recibir un turno agendado o confirmado.")
        if self.recepcion_id:
            raise UserError(
                "El turno ya tiene la recepción %s." % self.recepcion_id.name)
        recepcion = self.env['tllr_fc.recepcion'].create({
            'turno_id': self.id,
            'vehiculo_id': self.vehiculo_id.id,
            'partner_id': self.partner_id.id,
            'kilometraje': self.vehiculo_id.kilometraje,
            'company_id': self.company_id.id,
            'servicio_ids': [(0, 0, {
                'product_id': linea.product_id.id,
                'observacion': linea.observacion,
            }) for linea in self.servicio_ids],
        })
        self.message_post(body="Recepción %s creada en borrador." % recepcion._get_html_link())
        return recepcion._tllr_fc_accion_formulario()

    def action_ver_recepcion(self):
        self.ensure_one()
        if not self.recepcion_id:
            raise UserError("El turno todavía no tiene recepción.")
        return self.recepcion_id._tllr_fc_accion_formulario()

    def action_no_asistio(self):
        for turno in self:
            if not turno.vencido:
                raise UserError("Solo se puede marcar «No asistió» un turno vencido.")
            turno.state = 'no_asistio'
            turno.message_post(body="El cliente no asistió al turno.")
        return True

    def action_reprogramar(self):
        self.ensure_one()
        if not self.vencido:
            raise UserError("Solo se puede reprogramar un turno vencido.")
        nuevo = self.copy({'fecha_hora': fields.Datetime.now() + timedelta(days=1)})
        self.state = 'cancelado'
        self.message_post(
            body="Turno reprogramado: se creó el turno %s." % nuevo._get_html_link())
        nuevo.message_post(
            body="Reprogramación del turno %s. Ajustá la fecha y hora." % self._get_html_link())
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'tllr_fc.turno',
            'res_id': nuevo.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_cancelar(self):
        for turno in self:
            if turno.state not in ESTADOS_PENDIENTES:
                raise UserError("Solo se puede cancelar un turno agendado o confirmado.")
            turno.state = 'cancelado'
            turno.message_post(body="Turno cancelado.")
        return True

    def action_recordatorio(self):
        self.ensure_one()
        if not self.partner_id.email:
            raise UserError(
                "El cliente %s no tiene correo electrónico cargado." % self.partner_id.display_name)
        plantilla = self.env.ref('tllr_fc.mail_template_turno_recordatorio')
        plantilla.send_mail(self.id, force_send=True)
        self.message_post(
            body="Recordatorio enviado a %s." % self.partner_id.email)
        return True
