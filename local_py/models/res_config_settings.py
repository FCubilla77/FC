# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Expone la licencia del producto en la pantalla de Ajustes.

    Los campos viven en `res.company`; acá se exponen como `related` para poder
    dibujarlos en el bloque «Licencia» de Ajustes. Esta pantalla queda siempre
    disponible, con o sin licencia válida."""
    _inherit = 'res.config.settings'

    local_py_licencia_uuid = fields.Char(
        related='company_id.local_py_licencia_uuid', readonly=True)
    local_py_licencia_codigo = fields.Text(
        related='company_id.local_py_licencia_codigo', readonly=False)
    local_py_licencia_cliente = fields.Char(
        related='company_id.local_py_licencia_cliente', readonly=True)
    local_py_licencia_vencimiento = fields.Date(
        related='company_id.local_py_licencia_vencimiento', readonly=True)
    local_py_licencia_estado = fields.Selection(
        related='company_id.local_py_licencia_estado', readonly=True)
