# -*- coding: utf-8 -*-

from odoo import fields, models


class AccountAccount(models.Model):
    _inherit = 'account.account'

    l10n_py_pagos_a_cuenta = fields.Boolean(
        string='Pagos a Cuenta',
        help='Tilde esta opción para que la Cuenta aparezca como elegible en el '
             'selector de "Cuenta" de una Orden de Pago de tipo "Pago a Cuenta" — '
             'reemplaza cualquier filtro automático por Tipo de Cuenta, dejando el '
             'control puntual, cuenta por cuenta, en manos de quien administra el '
             'plan de cuentas.',
    )
