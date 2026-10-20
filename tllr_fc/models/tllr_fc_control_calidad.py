# -*- coding: utf-8 -*-
from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError


class TllrFcControlCalidad(models.Model):
    """Control de calidad de la OT. Una OT puede tener varios (historial)."""
    _name = 'tllr_fc.control_calidad'
    _description = "Control de calidad"
    _inherit = ['mail.thread', 'tllr_fc.mixin.wizard']
    _order = 'id desc'

    name = fields.Char(string="Número", required=True, readonly=True, copy=False, default="Nuevo")
    ot_id = fields.Many2one(
        'tllr_fc.ot', string="OT", required=True, ondelete='restrict', index=True,
        readonly=True)
    company_id = fields.Many2one(
        'res.company', string="Compañía", related='ot_id.company_id', store=True, index=True)
    vehiculo_id = fields.Many2one(related='ot_id.vehiculo_id', string="Vehículo")
    partner_id = fields.Many2one(related='ot_id.partner_id', string="Cliente")
    fecha = fields.Datetime(string="Fecha", required=True, default=fields.Datetime.now)
    responsable_id = fields.Many2one(
        'tllr_fc.personal', string="Responsable del control", required=True,
        ondelete='restrict', tracking=True,
        help="Debe ser distinto de todo el personal asignado a la OT (el supervisor puede "
             "autorizar una excepción).")
    linea_ids = fields.One2many(
        'tllr_fc.control_calidad.linea', 'control_id', string="Servicios controlados", copy=False)
    comentarios = fields.Text(string="Comentarios")
    state = fields.Selection([
        ('borrador', "Borrador"),
        ('aprobado', "Aprobado"),
        ('rechazado', "Rechazado"),
    ], string="Estado", required=True, default='borrador', copy=False, tracking=True, index=True)

    @api.onchange('ot_id')
    def _onchange_ot_id(self):
        if self.ot_id and not self._origin.id:
            self.responsable_id = self.ot_id.responsable_id
            self.linea_ids = [Command.clear()] + [
                Command.create(vals) for _c, _i, vals in self.ot_id._tllr_fc_lineas_de_control()]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            ot = self.env['tllr_fc.ot'].browse(vals.get('ot_id'))
            if not vals.get('name') or vals['name'] == "Nuevo":
                vals['name'] = ot.company_id._tllr_fc_siguiente_codigo('tllr_fc.control')
            if not vals.get('responsable_id'):
                vals['responsable_id'] = ot.responsable_id.id
            if 'linea_ids' not in vals:
                vals['linea_ids'] = ot._tllr_fc_lineas_de_control()
        controles = super().create(vals_list)
        for control in controles:
            if control.ot_id.state != 'calidad':
                raise UserError("Solo se crea un control con la OT en control de calidad.")
            otros = self.search_count([
                ('ot_id', '=', control.ot_id.id), ('state', '=', 'borrador'),
                ('id', '!=', control.id)])
            if otros:
                raise UserError("La OT %s ya tiene un control en borrador." % control.ot_id.name)
        return controles

    def write(self, vals):
        if not self.env.context.get('tllr_fc_permitir_write'):
            for control in self:
                if control.state != 'borrador' and set(vals) - {'message_main_attachment_id'}:
                    raise UserError("El control %s ya fue confirmado y no se modifica." % control.name)
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_validar(self):
        for control in self:
            if control.state != 'borrador':
                raise UserError("Solo se puede eliminar un control en borrador.")

    # ------------------------------------------------------------------
    def action_aprobar_todas(self):
        self.ensure_one()
        if self.state != 'borrador':
            raise UserError("El control ya fue confirmado.")
        self.linea_ids.write({'resultado': 'aprobado'})
        return True

    def action_confirmar(self):
        self.ensure_one()
        if not self.env.user.has_group('tllr_fc.group_supervisor'):
            raise AccessError("Solo el supervisor o el administrador de taller confirman el control.")
        if self.state != 'borrador':
            raise UserError("El control ya fue confirmado.")
        ot = self.ot_id
        if ot.state != 'calidad':
            raise UserError("La OT no está en control de calidad.")
        if not self.linea_ids:
            raise UserError("El control no tiene servicios para controlar.")
        sin_resultado = self.linea_ids.filtered(lambda l: not l.resultado)
        if sin_resultado:
            raise UserError("Indicá el resultado de: %s." % ', '.join(
                sin_resultado.mapped('ot_servicio_id.product_id.name')))
        if self.responsable_id in ot.personal_ids and not self.env.context.get('tllr_fc_excepcion'):
            return self._tllr_fc_abrir_excepcion(
                'action_confirmar', 'supervisor',
                "El responsable del control «%s» está asignado como personal de la OT."
                % self.responsable_id.name)
        rechazadas = self.linea_ids.filtered(lambda l: l.resultado == 'rechazado')
        ctx = self.with_context(tllr_fc_permitir_write=True)
        if not rechazadas:
            ctx.write({'state': 'aprobado'})
            ot.state = 'listo'
            ot.message_post(body="Control de calidad %s aprobado: la OT está lista para entrega." % self.name)
        else:
            ctx.write({'state': 'rechazado'})
            detalle = ', '.join(rechazadas.mapped('ot_servicio_id.product_id.name'))
            ot._tllr_fc_devolver_a_proceso(rechazadas.ot_servicio_id)
            ot.message_post(body="Control de calidad %s rechazado (%s). La OT vuelve a proceso." % (
                self.name, detalle))
        return True


class TllrFcControlCalidadLinea(models.Model):
    _name = 'tllr_fc.control_calidad.linea'
    _description = "Línea del control de calidad"
    _order = 'id'

    control_id = fields.Many2one(
        'tllr_fc.control_calidad', string="Control", required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(
        'res.company', related='control_id.company_id', store=True, index=True)
    ot_servicio_id = fields.Many2one(
        'tllr_fc.ot.servicio', string="Servicio", required=True, ondelete='restrict')
    informe = fields.Text(related='ot_servicio_id.informe', string="Informe del servicio")
    resultado_texto = fields.Text(string="Observaciones del control")
    resultado = fields.Selection([
        ('aprobado', "Aprobado"),
        ('rechazado', "Rechazado"),
    ], string="Resultado")
    check_ids = fields.One2many(
        'tllr_fc.control_calidad.check', 'linea_id', string="Lista de verificación")

    def _tllr_fc_verificar_borrador(self, controles):
        if self.env.context.get('tllr_fc_permitir_write'):
            return
        for control in controles:
            if control.state != 'borrador':
                raise UserError("El control %s ya fue confirmado y no se modifica." % control.name)

    def write(self, vals):
        self._tllr_fc_verificar_borrador(self.control_id)
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_validar(self):
        self._tllr_fc_verificar_borrador(self.control_id)


class TllrFcControlCalidadCheck(models.Model):
    _name = 'tllr_fc.control_calidad.check'
    _description = "Punto de verificación del control de calidad"
    _order = 'id'

    linea_id = fields.Many2one(
        'tllr_fc.control_calidad.linea', string="Línea", required=True, ondelete='cascade',
        index=True)
    company_id = fields.Many2one(
        'res.company', related='linea_id.company_id', store=True, index=True)
    name = fields.Char(string="Punto a verificar", required=True)
    cumple = fields.Boolean(string="Cumple")
