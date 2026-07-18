# -*- coding: utf-8 -*-

from odoo import models, fields


class AccountPaymentTerm(models.Model):
    _inherit = 'account.payment.term'

    l10n_py_condicion = fields.Selection(
        [('contado', 'Contado'), ('credito', 'Crédito')],
        string='Condición (Paraguay)',
        help='Clasifica este término de pago como Contado o Crédito, según '
             'la Tabla 2 de la Especificación Técnica de Marangatu (DNIT, '
             'RG 90/2021). Se usa para informar el "Código Condición de '
             'Venta/Compra" en los reportes Libro Ventas y Libro Compras.',
    )
