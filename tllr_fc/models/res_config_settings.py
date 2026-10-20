# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    tllr_fc_generar_asientos = fields.Boolean(
        related='company_id.tllr_fc_generar_asientos', readonly=False)
    tllr_fc_diario_id = fields.Many2one(
        related='company_id.tllr_fc_diario_id', readonly=False)
    tllr_fc_cuenta_wip_id = fields.Many2one(
        related='company_id.tllr_fc_cuenta_wip_id', readonly=False)
    tllr_fc_cuenta_costo_ventas_id = fields.Many2one(
        related='company_id.tllr_fc_cuenta_costo_ventas_id', readonly=False)
    tllr_fc_cuenta_gasto_interna_id = fields.Many2one(
        related='company_id.tllr_fc_cuenta_gasto_interna_id', readonly=False)
    tllr_fc_cuenta_gasto_garantia_id = fields.Many2one(
        related='company_id.tllr_fc_cuenta_gasto_garantia_id', readonly=False)
    tllr_fc_cuenta_perdida_id = fields.Many2one(
        related='company_id.tllr_fc_cuenta_perdida_id', readonly=False)
    tllr_fc_asiento_horas = fields.Boolean(
        related='company_id.tllr_fc_asiento_horas', readonly=False)
    tllr_fc_cuenta_mano_obra_id = fields.Many2one(
        related='company_id.tllr_fc_cuenta_mano_obra_id', readonly=False)
    tllr_fc_almacen_principal_id = fields.Many2one(
        related='company_id.tllr_fc_almacen_principal_id', readonly=False)
    tllr_fc_diario_venta_id = fields.Many2one(
        related='company_id.tllr_fc_diario_venta_id', readonly=False)
    tllr_fc_qc_cliente = fields.Boolean(
        related='company_id.tllr_fc_qc_cliente', readonly=False)
    tllr_fc_qc_interno = fields.Boolean(
        related='company_id.tllr_fc_qc_interno', readonly=False)
    tllr_fc_qc_garantia = fields.Boolean(
        related='company_id.tllr_fc_qc_garantia', readonly=False)
    tllr_fc_aprobacion_adicional = fields.Selection(
        related='company_id.tllr_fc_aprobacion_adicional', readonly=False)
