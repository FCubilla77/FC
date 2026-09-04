# -*- coding: utf-8 -*-
"""Espejo técnico de la Configuración FEPy sobre res.company.

La configuración de Facturación Electrónica ya NO vive en la Compañía:
vive en fe_py.configuracion (Localización Paraguay > Facturación
Electrónica Py > Configuraciones Generales FEPy). En Ajustes > Empresas
queda únicamente lo nativo de Odoo.

Estos campos son de SOLO LECTURA y no se muestran en ninguna vista. Son
un atajo interno para que el resto del módulo pueda seguir escribiendo
`company.fe_py_ambiente` sin tener que buscar la configuración en cada
lugar. El dato real, el editable, está siempre en fe_py.configuracion.
"""

from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    fe_py_configuracion_id = fields.Many2one(
        'fe_py.configuracion', string='Configuración FEPy',
        compute='_compute_fe_py_configuracion', store=False,
    )

    # -- Espejo de solo lectura, para uso interno del módulo -------------
    fe_py_habilitado = fields.Boolean(
        related='fe_py_configuracion_id.fe_py_habilitado', readonly=True)
    fe_py_ambiente = fields.Selection(
        related='fe_py_configuracion_id.fe_py_ambiente', readonly=True)
    fe_py_cert_path = fields.Char(
        related='fe_py_configuracion_id.fe_py_cert_path', readonly=True)
    fe_py_private_key_path = fields.Char(
        related='fe_py_configuracion_id.fe_py_private_key_path', readonly=True)
    fe_py_public_key_path = fields.Char(
        related='fe_py_configuracion_id.fe_py_public_key_path', readonly=True)
    fe_py_idcsc = fields.Char(
        related='fe_py_configuracion_id.fe_py_idcsc', readonly=True)
    fe_py_csc = fields.Char(
        related='fe_py_configuracion_id.fe_py_csc', readonly=True)
    fe_py_envio_automatico = fields.Boolean(
        related='fe_py_configuracion_id.fe_py_envio_automatico', readonly=True)
    fe_py_kude_automatico = fields.Boolean(
        related='fe_py_configuracion_id.fe_py_kude_automatico', readonly=True)
    fe_py_email_automatico = fields.Boolean(
        related='fe_py_configuracion_id.fe_py_email_automatico', readonly=True)
    fe_py_reintento_automatico = fields.Boolean(
        related='fe_py_configuracion_id.fe_py_reintento_automatico', readonly=True)

    @api.depends_context('company')
    def _compute_fe_py_configuracion(self):
        Config = self.env['fe_py.configuracion'].sudo()
        for company in self:
            company.fe_py_configuracion_id = Config.search(
                [('company_id', '=', company.id)], limit=1,
            )
