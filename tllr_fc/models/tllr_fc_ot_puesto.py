# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class TllrFcOtPuesto(models.Model):
    """Puesto por el que pasa la OT (líneas ordenadas por el supervisor)."""
    _name = 'tllr_fc.ot.puesto'
    _description = "Puesto de la orden de trabajo"
    _order = 'sequence, id'
    _check_company_auto = True

    ot_id = fields.Many2one(
        'tllr_fc.ot', string="OT", required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(
        'res.company', string="Compañía", related='ot_id.company_id',
        store=True, index=True)
    sequence = fields.Integer(string="Orden", default=10)
    puesto_id = fields.Many2one(
        'tllr_fc.puesto', string="Puesto", required=True, ondelete='restrict',
        check_company=True)
    name = fields.Char(string="Nombre", related='puesto_id.name')
    state = fields.Selection([
        ('pendiente', "Pendiente"),
        ('activo', "Activo"),
        ('terminado', "Terminado"),
    ], string="Estado", required=True, default='pendiente', copy=False, index=True)
    personal_ids = fields.Many2many(
        'tllr_fc.personal', 'tllr_fc_ot_puesto_personal_rel', 'puesto_line_id', 'personal_id',
        string="Personal", check_company=True)
    servicio_ids = fields.One2many(
        'tllr_fc.ot.servicio', 'puesto_line_id', string="Servicios")
    fecha_inicio = fields.Datetime(string="Inicio", readonly=True, copy=False)
    fecha_fin = fields.Datetime(string="Fin", readonly=True, copy=False)
    almacen_id = fields.Many2one(
        'stock.warehouse', related='puesto_id.almacen_id', string="Almacén")

    @api.constrains('state', 'ot_id')
    def _check_un_solo_activo(self):
        for ot in self.ot_id:
            activos = ot.puesto_line_ids.filtered(lambda l: l.state == 'activo')
            if len(activos) > 1:
                raise ValidationError(
                    "La OT %s no puede tener más de un puesto activo a la vez." % ot.name)

    # ------------------------------------------------------------------
    def _tllr_fc_usuario_puede_operar(self):
        """Supervisor o personal asignado al puesto (por su usuario)."""
        self.ensure_one()
        if self.env.user.has_group('tllr_fc.group_supervisor'):
            return True
        return self.env.user in self.personal_ids.user_id

    def _tllr_fc_verificar_ot_editable(self, ots):
        for ot in ots:
            if ot.state not in ('espera', 'proceso'):
                raise UserError(
                    "La OT %s ya no admite cambios en sus puestos." % ot.name)

    @api.model_create_multi
    def create(self, vals_list):
        ots = self.env['tllr_fc.ot'].browse([v['ot_id'] for v in vals_list if v.get('ot_id')])
        self._tllr_fc_verificar_ot_editable(ots)
        for vals in vals_list:
            vals['state'] = 'pendiente'
        lineas = super().create(vals_list)
        # Los servicios de la OT sin puesto que este puesto realiza se le asocian.
        for linea in lineas:
            sin_puesto = linea.ot_id.servicio_ids.filtered(
                lambda s: not s.puesto_line_id
                and s.product_id.product_tmpl_id in linea.puesto_id.servicio_ids)
            if sin_puesto:
                sin_puesto.write({'puesto_line_id': linea.id})
        for ot in lineas.ot_id:
            ot._tllr_fc_asignar_puesto_productos()
        return lineas

    def write(self, vals):
        if not self.env.context.get('tllr_fc_permitir_write'):
            if 'state' in vals or 'fecha_inicio' in vals or 'fecha_fin' in vals:
                raise UserError("El estado del puesto cambia con los botones de la OT.")
            self._tllr_fc_verificar_ot_editable(self.ot_id)
            if 'puesto_id' in vals and any(l.state != 'pendiente' for l in self):
                raise UserError("Solo se puede cambiar el puesto mientras está pendiente.")
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_validar(self):
        self._tllr_fc_verificar_ot_editable(self.ot_id)
        for linea in self:
            if linea.state != 'pendiente':
                raise UserError(
                    "Solo se puede quitar un puesto que todavía está pendiente (%s)." % linea.name)
