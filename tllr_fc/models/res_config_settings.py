# -*- coding: utf-8 -*-
from odoo import api, fields, models


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

    # Integraciones: al guardar, Odoo instala (o desinstala) el módulo puente.
    # Solo ejecuta el cambio un administrador de Odoo (base.group_system).
    module_tllr_fc_sale = fields.Boolean(string="Instalar integración con Ventas")
    module_tllr_fc_purchase = fields.Boolean(string="Instalar integración con Compras")

    # Ajustes graba los campos relacionados de a uno en la compañía; la validación
    # de los asientos se difiere hasta que están todos guardados.
    @api.model_create_multi
    def create(self, vals_list):
        registros = super(ResConfigSettings, self.with_context(
            tllr_fc_diferir_validacion=True)).create(vals_list)
        registros = registros.with_env(self.env)
        registros.company_id._tllr_fc_validar_asientos()
        return registros

    def write(self, vals):
        resultado = super(ResConfigSettings, self.with_context(
            tllr_fc_diferir_validacion=True)).write(vals)
        self.company_id._tllr_fc_validar_asientos()
        return resultado
