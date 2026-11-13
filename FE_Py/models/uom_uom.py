# -*- coding: utf-8 -*-
"""Correspondencia entre las unidades de Odoo y las de SIFEN (campo que
FE_Py agrega a uom.uom)."""

from odoo import fields, models


class UomUom(models.Model):
    """Correspondencia entre las unidades de Odoo y las de SIFEN.

    No reemplaza al dato del producto (que es el que manda), pero permite
    proponerlo automáticamente al crear productos nuevos, en vez de
    obligar a elegirlo uno por uno.
    """
    _inherit = 'uom.uom'

    fe_py_unidad_medida_id = fields.Many2one(
        'fe_py.unidad_medida', string='FEPy Unidad de Medida',
        help='Se usa para proponer la unidad SIFEN al crear un producto con '
             'esta unidad de medida.',
    )
