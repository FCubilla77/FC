# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

NIVELES_COMBUSTIBLE = [
    ('reserva', "Reserva"),
    ('1_4', "1/4"),
    ('1_2', "1/2"),
    ('3_4', "3/4"),
    ('lleno', "Lleno"),
]
ORDEN_COMBUSTIBLE = [clave for clave, _etiqueta in NIVELES_COMBUSTIBLE]


class TllrFcEntrega(models.Model):
    """Entrega del vehículo al cliente (revisión de inventario y condiciones)."""
    _name = 'tllr_fc.entrega'
    _description = "Entrega de vehículo"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'tllr_fc.mixin.wizard']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(
        string="Número", required=True, readonly=True, copy=False, default="Nuevo")
    company_id = fields.Many2one(
        'res.company', string="Compañía", required=True, index=True,
        default=lambda self: self.env.company)
    fecha = fields.Datetime(
        string="Fecha", required=True, default=fields.Datetime.now, tracking=True)
    ot_id = fields.Many2one(
        'tllr_fc.ot', string="OT", required=True, ondelete='restrict', index=True,
        check_company=True, tracking=True,
        domain="[('state', '=', 'listo')]")
    ot_tipo = fields.Selection(related='ot_id.tipo', string="Tipo de OT")
    ot_state = fields.Selection(related='ot_id.state', string="Estado de la OT")
    vehiculo_id = fields.Many2one(
        'tllr_fc.vehiculo', string="Vehículo", related='ot_id.vehiculo_id', store=True)
    partner_id = fields.Many2one(
        'res.partner', string="Cliente", related='ot_id.partner_id', store=True)
    retira_id = fields.Many2one(
        'res.partner', string="Retira", required=True, ondelete='restrict', tracking=True,
        help="Persona que retira el vehículo; puede ser distinta del contacto principal.")
    linea_ids = fields.One2many(
        'tllr_fc.entrega.linea', 'entrega_id', string="Revisión de inventario", copy=False)
    kilometraje_ingreso = fields.Integer(
        string="Kilometraje al ingreso", related='ot_id.kilometraje_ingreso')
    kilometraje_salida = fields.Integer(string="Kilometraje de salida", tracking=True)
    combustible_ingreso = fields.Selection(
        related='ot_id.combustible_ingreso', string="Combustible al ingreso")
    combustible_salida = fields.Selection(
        NIVELES_COMBUSTIBLE, string="Combustible a la salida")
    alerta_combustible = fields.Char(
        string="Alerta de combustible", compute='_compute_alerta_combustible')
    comentarios = fields.Text(string="Comentarios")
    hay_diferencias = fields.Boolean(
        string="Con diferencias de inventario", compute='_compute_hay_diferencias')
    state = fields.Selection(
        [('borrador', "Borrador"), ('confirmada', "Confirmada")],
        string="Estado", required=True, default='borrador', copy=False, tracking=True)

    @api.depends('ot_id', 'combustible_salida', 'ot_id.combustible_ingreso', 'ot_id.tipo')
    def _compute_alerta_combustible(self):
        for entrega in self:
            alerta = False
            ingreso = entrega.ot_id.combustible_ingreso
            salida = entrega.combustible_salida
            if (ingreso and salida and entrega.ot_id.tipo != 'interno'
                    and ORDEN_COMBUSTIBLE.index(salida) < ORDEN_COMBUSTIBLE.index(ingreso)):
                etiquetas = dict(NIVELES_COMBUSTIBLE)
                alerta = "El combustible de salida (%s) es menor al de ingreso (%s)." % (
                    etiquetas[salida], etiquetas[ingreso])
            entrega.alerta_combustible = alerta

    @api.depends('linea_ids.diferencia')
    def _compute_hay_diferencias(self):
        for entrega in self:
            entrega.hay_diferencias = any(entrega.linea_ids.mapped('diferencia'))

    @api.constrains('ot_id', 'state')
    def _check_una_confirmada(self):
        for entrega in self.filtered(lambda e: e.state == 'confirmada'):
            otras = self.search_count([
                ('ot_id', '=', entrega.ot_id.id), ('state', '=', 'confirmada'),
                ('id', '!=', entrega.id)])
            if otras:
                raise ValidationError("La OT %s ya tiene una entrega confirmada." % entrega.ot_id.name)

    @api.constrains('ot_id')
    def _check_ot_entregable(self):
        for entrega in self:
            ot = entrega.ot_id
            if entrega.state == 'borrador' and not (
                    ot.state == 'listo' or (ot.state == 'cancelada' and ot.liquidada)):
                raise ValidationError(
                    "Solo se entregan OT listas para entrega o canceladas con liquidación (%s)." % ot.name)

    # ------------------------------------------------------------------
    @api.onchange('ot_id')
    def _onchange_ot_id(self):
        if self.ot_id and not self._origin.id:
            self.retira_id = self.ot_id.partner_id
            self.kilometraje_salida = self.ot_id.kilometraje_ingreso
            self.combustible_salida = self.ot_id.combustible_ingreso
            self.linea_ids = [(5, 0, 0)] + [
                (0, 0, vals) for vals in self.ot_id._tllr_fc_lineas_de_entrega()]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            ot = self.env['tllr_fc.ot'].browse(vals.get('ot_id'))
            if not vals.get('name') or vals['name'] == "Nuevo":
                compania = self.env['res.company'].browse(
                    vals.get('company_id') or ot.company_id.id or self.env.company.id)
                vals['name'] = compania._tllr_fc_siguiente_codigo('tllr_fc.entrega')
            if ot:
                vals.setdefault('retira_id', ot.partner_id.id)
                vals.setdefault('kilometraje_salida', ot.kilometraje_ingreso)
                if 'linea_ids' not in vals:
                    vals['linea_ids'] = [(0, 0, v) for v in ot._tllr_fc_lineas_de_entrega()]
        return super().create(vals_list)

    def write(self, vals):
        if any(e.state == 'confirmada' for e in self) and not self.env.context.get(
                'tllr_fc_permitir_write'):
            raise UserError("Una entrega confirmada no se modifica.")
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_borrador(self):
        if any(e.state == 'confirmada' for e in self):
            raise UserError("Una entrega confirmada no se elimina.")

    # ------------------------------------------------------------------
    def _tllr_fc_problemas(self):
        """Condiciones que exigen la autorización de un supervisor."""
        self.ensure_one()
        ot = self.ot_id
        problemas = []
        if ot.tipo == 'cliente':
            facturas = ot.sudo()._tllr_fc_facturas().filtered(
                lambda m: m.move_type == 'out_invoice' and m.state == 'posted')
            if not facturas:
                problemas.append("La OT no tiene una factura confirmada.")
            for factura in facturas:
                contado = (not factura.invoice_date_due or not factura.invoice_date
                           or factura.invoice_date_due <= factura.invoice_date)
                if contado and factura.payment_state not in ('paid', 'in_payment'):
                    problemas.append(
                        "La factura %s es de contado y no está pagada." % factura.name)
        pendientes = self.linea_ids.filtered('diferencia')
        if pendientes:
            problemas.append("Diferencias de inventario: %s." % ', '.join(pendientes.mapped('name')))
        if self.kilometraje_salida < ot.kilometraje_ingreso:
            problemas.append(
                "El kilometraje de salida (%s) es menor al de ingreso (%s)." % (
                    self.kilometraje_salida, ot.kilometraje_ingreso))
        return problemas

    def action_confirmar(self):
        self.ensure_one()
        ot = self.ot_id
        if self.state != 'borrador':
            raise UserError("La entrega ya está confirmada.")
        if not (ot.state == 'listo' or (ot.state == 'cancelada' and ot.liquidada)):
            raise UserError(
                "La OT %s no está lista para entrega (estado «%s»)." % (
                    ot.name, dict(ot._fields['state'].selection)[ot.state]))
        if not self.kilometraje_salida:
            raise UserError("Indicá el kilometraje de salida.")
        if self.search_count([('ot_id', '=', ot.id), ('state', '=', 'confirmada')]):
            raise UserError("La OT %s ya tiene una entrega confirmada." % ot.name)
        problemas = self._tllr_fc_problemas()
        if problemas and not self.env.context.get('tllr_fc_excepcion'):
            return self._tllr_fc_abrir_excepcion(
                'action_confirmar', 'supervisor',
                "Entregar la OT %s sin cumplir:\n- %s" % (ot.name, '\n- '.join(problemas)))
        if problemas and not self._tllr_fc_es_supervisor():
            raise AccessError("Solo un supervisor puede autorizar la entrega con observaciones.")
        ot._tllr_fc_aplicar_entrega(self)
        self.with_context(tllr_fc_permitir_write=True).write({'state': 'confirmada'})
        mensaje = "Entrega %s confirmada. Retira: %s." % (self.name, self.retira_id.name)
        if self.alerta_combustible:
            mensaje += "<br/>⚠ %s" % self.alerta_combustible
            ot.message_post(body="⚠ Entrega %s: %s" % (self.name, self.alerta_combustible))
        self.message_post(body=mensaje)
        return True

    def _tllr_fc_es_supervisor(self):
        return self.env.user.has_group('tllr_fc.group_supervisor')

    def action_ver_ot(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'tllr_fc.ot',
            'res_id': self.ot_id.id, 'view_mode': 'form', 'target': 'current'}


class TllrFcEntregaLinea(models.Model):
    _name = 'tllr_fc.entrega.linea'
    _description = "Línea de revisión de la entrega"
    _order = 'id'

    entrega_id = fields.Many2one(
        'tllr_fc.entrega', string="Entrega", required=True, ondelete='cascade', index=True)
    origen = fields.Selection(
        [('recepcion', "Inventario de la recepción"),
         ('repuesto_cliente', "Repuesto del cliente")],
        string="Origen", required=True, default='recepcion')
    name = fields.Char(string="Descripción", required=True)
    presente_recepcion = fields.Boolean(string="Estaba presente al ingreso", default=True)
    entregado = fields.Boolean(string="Entregado")
    observacion = fields.Char(string="Observación")
    diferencia = fields.Boolean(
        string="Diferencia", compute='_compute_diferencia', store=True)

    @api.depends('origen', 'presente_recepcion', 'entregado')
    def _compute_diferencia(self):
        for linea in self:
            linea.diferencia = (
                linea.origen == 'recepcion' and linea.presente_recepcion and not linea.entregado)
