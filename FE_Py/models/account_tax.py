# -*- coding: utf-8 -*-
"""Afectación IVA por impuesto (campo que FE_Py agrega a account.tax)."""

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AccountTax(models.Model):
    """Afectación IVA por impuesto.

    Antes el generador deducía la naturaleza del impuesto mirando su
    porcentaje ("si es 10 entonces es IVA 10%"), lo que fallaría con un
    ISC o una retención del mismo porcentaje. Ahora cada impuesto declara
    explícitamente qué es; el porcentaje se sigue leyendo del propio
    impuesto, que es donde ya estaba bien.
    """
    _inherit = 'account.tax'

    fe_py_afectacion_iva_id = fields.Many2one(
        'fe_py.afectacion_iva', string='FEPy Afectación IVA',
        domain="[('disponible', '=', True)]",
        help='Código que se informa como iAfecIVA en cada línea que use este '
             'impuesto. Sin este dato no se puede generar el XML.',
    )

    @api.constrains('fe_py_afectacion_iva_id')
    def _check_fe_py_afectacion_disponible(self):
        for tax in self:
            afec = tax.fe_py_afectacion_iva_id
            if afec and not afec.disponible:
                raise ValidationError(
                    'El código de Afectación IVA "%s" todavía no está '
                    'disponible: su cálculo (total exonerado, proporción '
                    'gravada y base exenta por línea) no está implementado, '
                    'y usarlo generaría un XML inconsistente.' % afec.name
                )
