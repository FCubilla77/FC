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
             'cuota. Solo aplica si la operación es a crédito.',
    )

    def _fe_py_es_credito(self):
        """True si este Término de Pago representa una operación a CRÉDITO.

        Se deduce de Odoo nativo —hay crédito si alguna línea del término
        vence después de la emisión— en vez de leer un campo de la
        localización. Así FE_Py informa iCondOpe sin depender de nadie.
        Un término sin líneas se considera contado.
        """
        self.ensure_one()
        for linea in self.line_ids:
            for campo in ('nb_days', 'days', 'days_next_month'):
                valor = linea[campo] if campo in linea._fields else 0
                if valor:
                    return True
        return False
