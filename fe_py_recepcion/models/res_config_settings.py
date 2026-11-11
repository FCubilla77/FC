# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Expone en Ajustes la configuración de la recepción de facturas electrónicas y
    su licencia.

    Los campos viven en `res.company`; acá se exponen como `related` para poder
    dibujarlos en la sección «Configuración FE_Py Recepción». Esta pantalla queda
    siempre disponible, con o sin licencia válida."""
    _inherit = 'res.config.settings'

    fe_py_recepcion_diario_id = fields.Many2one(
        related='company_id.fe_py_recepcion_diario_id', readonly=False,
        domain="[('type', '=', 'purchase'), ('company_id', '=', company_id)]")
    fe_py_recepcion_diario_nc_id = fields.Many2one(
        related='company_id.fe_py_recepcion_diario_nc_id', readonly=False,
        domain="[('type', '=', 'purchase'), ('company_id', '=', company_id)]")
    fe_py_recepcion_diario_nd_id = fields.Many2one(
        related='company_id.fe_py_recepcion_diario_nd_id', readonly=False,
        domain="[('type', '=', 'purchase'), ('company_id', '=', company_id)]")
    fe_py_recepcion_impuesto_iva10_id = fields.Many2one(
        related='company_id.fe_py_recepcion_impuesto_iva10_id', readonly=False,
        domain="[('type_tax_use', '=', 'purchase'), ('company_id', '=', company_id)]")
    fe_py_recepcion_impuesto_iva5_id = fields.Many2one(
        related='company_id.fe_py_recepcion_impuesto_iva5_id', readonly=False,
        domain="[('type_tax_use', '=', 'purchase'), ('company_id', '=', company_id)]")
    fe_py_recepcion_impuesto_exento_id = fields.Many2one(
        related='company_id.fe_py_recepcion_impuesto_exento_id', readonly=False,
        domain="[('type_tax_use', '=', 'purchase'), ('company_id', '=', company_id)]")

    fe_py_recepcion_estado_facturas = fields.Selection(
        related='company_id.fe_py_recepcion_estado_facturas', readonly=False)
    fe_py_recepcion_tolerancia = fields.Float(
        related='company_id.fe_py_recepcion_tolerancia', readonly=False)
    fe_py_recepcion_validar_remitente = fields.Boolean(
        related='company_id.fe_py_recepcion_validar_remitente', readonly=False)
    fe_py_recepcion_registrar_sin_xml = fields.Boolean(
        related='company_id.fe_py_recepcion_registrar_sin_xml', readonly=False)

    fe_py_recepcion_usar_mapeo = fields.Boolean(
        related='company_id.fe_py_recepcion_usar_mapeo', readonly=False)
    fe_py_recepcion_mapeo_estado = fields.Selection(
        related='company_id.fe_py_recepcion_mapeo_estado', readonly=True)

    def fe_py_recepcion_abrir_mapeo(self):
        self.ensure_one()
        return self.env['ir.actions.act_window']._for_xml_id(
            'fe_py_recepcion.action_fe_py_recepcion_mapeo')

    def fe_py_recepcion_cargar_sugerido(self):
        self.ensure_one()
        return self.env['fe_py_recepcion.mapeo'].cargar_sugerido_local_py()

    fe_py_recepcion_fetchmail_id = fields.Many2one(
        related='company_id.fe_py_recepcion_fetchmail_id', readonly=True)

    def fe_py_recepcion_abrir_cuenta_correo(self):
        self.ensure_one()
        return self.company_id.fe_py_recepcion_abrir_cuenta_correo()

    fe_py_recepcion_licencia_uuid = fields.Char(
        related='company_id.fe_py_recepcion_licencia_uuid', readonly=True)
    fe_py_recepcion_licencia_codigo = fields.Text(
        related='company_id.fe_py_recepcion_licencia_codigo', readonly=False)
    fe_py_recepcion_licencia_cliente = fields.Char(
        related='company_id.fe_py_recepcion_licencia_cliente', readonly=True)
    fe_py_recepcion_licencia_vencimiento = fields.Date(
        related='company_id.fe_py_recepcion_licencia_vencimiento', readonly=True)
    fe_py_recepcion_licencia_estado = fields.Selection(
        related='company_id.fe_py_recepcion_licencia_estado', readonly=True)
