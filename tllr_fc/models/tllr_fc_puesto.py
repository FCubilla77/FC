# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TllrFcPuesto(models.Model):
    _name = 'tllr_fc.puesto'
    _description = "Puesto de trabajo"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'
    _check_company_auto = True

    codigo = fields.Char(
        string="Código", required=True, readonly=True, copy=False, default="Nuevo")
    name = fields.Char(string="Puesto", required=True, tracking=True)
    servicio_ids = fields.Many2many(
        'product.template', 'tllr_fc_puesto_servicio_rel', 'puesto_id', 'product_tmpl_id',
        string="Tipos de trabajo", domain="[('type', '=', 'service')]",
        help="Servicios que se realizan en el puesto. Un servicio puede estar en varios puestos.")
    almacen_id = fields.Many2one(
        'stock.warehouse', string="Almacén de herramientas", required=True,
        ondelete='restrict', check_company=True)
    color = fields.Integer(string="Color")
    company_id = fields.Many2one(
        'res.company', string="Compañía", required=True,
        default=lambda self: self.env.company)
    active = fields.Boolean(string="Activo", default=True)
    es_calidad = fields.Boolean(
        string="Puesto de control de calidad", readonly=True, copy=False,
        help="Puesto del sistema: agrupa en el tablero las OT en control de calidad.")

    @api.constrains('servicio_ids')
    def _check_servicios(self):
        for puesto in self.filtered(lambda p: not p.es_calidad):
            if not puesto.servicio_ids:
                raise ValidationError(
                    "El puesto %s debe realizar al menos un tipo de trabajo (servicio)." % puesto.name)
            no_servicios = puesto.servicio_ids.filtered(lambda p: p.type != 'service')
            if no_servicios:
                raise ValidationError(
                    "Solo se pueden asignar productos de tipo servicio a un puesto: %s." %
                    ', '.join(no_servicios.mapped('display_name')))

    @api.ondelete(at_uninstall=False)
    def _unlink_no_calidad(self):
        if self.filtered('es_calidad'):
            raise ValidationError("El puesto de control de calidad es del sistema y no se elimina.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('codigo') or vals['codigo'] == "Nuevo":
                compania = self.env['res.company'].browse(
                    vals.get('company_id') or self.env.company.id)
                vals['codigo'] = compania._tllr_fc_siguiente_codigo('tllr_fc.puesto')
        puestos = super().create(vals_list)
        # El constrains solo se dispara si se informa el campo: se valida siempre al crear.
        puestos._check_servicios()
        return puestos
