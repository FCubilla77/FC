# -*- coding: utf-8 -*-
"""Descripción de la moneda para el XML (campo que FE_Py agrega a res.currency)."""

from odoo import fields, models


class ResCurrency(models.Model):
    """Descripción de la moneda para el XML.

    El código ya sirve tal cual: SIFEN usa ISO 4217, el mismo estándar
    que Odoo usa en el nombre de la moneda (PYG, USD, EUR). Solo falta
    la descripción en el formato que espera SIFEN.
    """
    _inherit = 'res.currency'

    fe_py_descripcion = fields.Char(
        string='FEPy Descripción de Moneda',
        help='Texto que se informa como dDesMoneOpe (3 a 20 caracteres). '
             'Ejemplos: "Guarani", "Dolar americano", "Real brasileño". '
             'Sin este dato no se puede facturar en esta moneda.',
    )
