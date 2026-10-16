# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError


class TllrFcOt(models.Model):
    """Orden de trabajo.

    En la Fase 2 la OT nace de la recepción, en estado En espera, con los
    servicios solicitados como referencia. El resto del ciclo (puestos,
    personal, repuestos, horas, control de calidad, facturación y entrega)
    se incorpora en las fases siguientes.
    """
    _name = 'tllr_fc.ot'
    _description = "Orden de trabajo"
    _inherit = ['mail.thread', 'mail.activity.mixin']
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
        'tllr_fc.ot.servicio', 'ot_id', string="Servicios solicitados", copy=False)

    @api.depends('fecha_ingreso', 'fecha_entrega', 'state')
    def _compute_dias_taller(self):
        ahora = fields.Datetime.now()
        for ot in self:
            if not ot.fecha_ingreso:
                ot.dias_taller = 0
                continue
            fin = ot.fecha_entrega or ahora
            ot.dias_taller = max((fin - ot.fecha_ingreso).days, 0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == "Nuevo":
                compania = self.env['res.company'].browse(
                    vals.get('company_id') or self.env.company.id)
                vals['name'] = compania._tllr_fc_siguiente_codigo('tllr_fc.ot')
        return super().create(vals_list)

    def write(self, vals):
        if 'tipo' in vals and not self.env.user.has_group('tllr_fc.group_supervisor'):
            raise AccessError("Solo el supervisor o el administrador de taller pueden cambiar el tipo de OT.")
        return super().write(vals)

    def _tllr_fc_cancelar_por_recepcion(self):
        """Cancela la OT en espera cuando se anula su recepción (sin liquidación)."""
        motivo = self.env.ref(
            'tllr_fc.motivo_cancelacion_recepcion_anulada', raise_if_not_found=False)
        for ot in self:
            ot.write({
                'state': 'cancelada',
                'motivo_cancelacion_id': motivo.id if motivo else False,
            })
            ot.message_post(body="OT cancelada porque se anuló su recepción (sin liquidación).")

    def action_ver_recepcion(self):
        self.ensure_one()
        return self.recepcion_id._tllr_fc_accion_formulario()
