# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Expone la licencia del producto en Ajustes > Configuración FE_Py.

    Esta pantalla queda SIEMPRE disponible, con o sin licencia válida: es la única
    forma de cargar o renovar el código. Por eso la licencia vive en res.company y
    no en fe_py.configuracion, que tiene la edición bloqueada sin licencia.

    La configuración funcional de Facturación Electrónica (emisor, certificado, CSC,
    automatización, catálogos DNIT y servicios de SIFEN) NO está acá: vive en
    Localización Paraguay > Facturación Electrónica Py > Configuraciones Generales
    FEPy, con sus propias pestañas."""
    _inherit = 'res.config.settings'

    fe_py_licencia_uuid = fields.Char(
        related='company_id.fe_py_licencia_uuid', readonly=True)
    fe_py_licencia_codigo = fields.Text(
        related='company_id.fe_py_licencia_codigo', readonly=False)
    fe_py_licencia_cliente = fields.Char(
        related='company_id.fe_py_licencia_cliente', readonly=True)
    fe_py_licencia_vencimiento = fields.Date(
        related='company_id.fe_py_licencia_vencimiento', readonly=True)
    fe_py_licencia_estado = fields.Selection(
        related='company_id.fe_py_licencia_estado', readonly=True)
