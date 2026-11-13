# -*- coding: utf-8 -*-
"""Unidad de medida SIFEN por producto (campo que FE_Py agrega a product.template)."""

from odoo import fields, models


class ProductTemplate(models.Model):
    """Unidad de medida SIFEN por producto.

    Antes toda línea salía como "Unidad (77)", sin importar si se vendían
    kilos, litros o metros — un dato fiscal incorrecto en cada documento.
    """
    _inherit = 'product.template'

    fe_py_unidad_medida_id = fields.Many2one(
        'fe_py.unidad_medida', string='FEPy Unidad de Medida',
        help='Unidad que se informa como cUniMed en las líneas de este '
             'producto. Obligatoria para poder facturarlo electrónicamente.',
    )
