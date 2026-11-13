# -*- coding: utf-8 -*-
"""Condición del crédito (campo que FE_Py agrega a account.payment.term)."""

from odoo import fields, models


class AccountPaymentTerm(models.Model):
    """Condición de la operación y del crédito."""
    _inherit = 'account.payment.term'

    fe_py_condicion_credito = fields.Selection(
        string='FEPy Condición del Crédito',
        selection=[('1', 'Plazo'), ('2', 'Cuota')], default='1',
        help='Se informa como iCondCred en las operaciones a crédito. '
             '"Plazo" informa dPlazoCre; "Cuota" informa el detalle de cada '
             'cuota. Solo aplica si la Condición de local_py es Crédito.',
    )
