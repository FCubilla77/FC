# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

USOS_TALLER = [
    ('repuesto', "Repuesto"),
    ('insumo', "Insumo (no facturable)"),
    ('insumo_facturable', "Insumo facturable"),
    ('accesorio', "Accesorio"),
    ('herramienta', "Herramienta"),
    ('ninguno', "Ninguno"),
]

USOS_FACTURABLES = ('repuesto', 'insumo_facturable', 'accesorio')


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    tllr_fc_uso_taller = fields.Selection(
        USOS_TALLER, string="Uso en taller", default='ninguno',
        help="Define cómo se usa el producto en la orden de trabajo. Se facturan "
             "los usos Repuesto, Insumo facturable y Accesorio; el Insumo (no "
             "facturable) se consume sin cobrarse y la Herramienta solo sirve "
             "para el control de inventario del puesto.")
    tllr_fc_horas_estandar = fields.Float(
        string="Horas estándar",
        help="Horas estándar del servicio: base de cotización y de eficiencia.")
    tllr_fc_checklist_ids = fields.One2many(
        'tllr_fc.servicio.checklist', 'product_tmpl_id', string="Lista de verificación")
    tllr_fc_garantia_dias = fields.Integer(
        string="Garantía (días)", help="0 = sin garantía.")
    tllr_fc_garantia_km = fields.Integer(
        string="Garantía (km)", help="Plazo opcional en kilómetros. 0 = no aplica.")
    tllr_fc_puesto_ids = fields.Many2many(
        'tllr_fc.puesto', 'tllr_fc_puesto_servicio_rel', 'product_tmpl_id', 'puesto_id',
        string="Puestos", readonly=True)

    @api.onchange('type')
    def _onchange_type_tllr_fc(self):
        if self.type != 'consu':
            self.tllr_fc_uso_taller = 'ninguno'

    @api.constrains('tllr_fc_garantia_dias', 'tllr_fc_garantia_km', 'tllr_fc_horas_estandar')
    def _check_tllr_fc_valores(self):
        for producto in self:
            if producto.tllr_fc_garantia_dias < 0 or producto.tllr_fc_garantia_km < 0:
                raise ValidationError("El plazo de garantía no puede ser negativo.")
            if producto.tllr_fc_horas_estandar < 0:
                raise ValidationError("Las horas estándar no pueden ser negativas.")
