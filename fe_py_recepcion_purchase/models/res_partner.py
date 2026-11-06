# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    fe_py_recepcion_confirmar_sin_cotizacion = fields.Boolean(
        string='Confirmar Facturas Electrónicas Recibidas sin Cotización',
        groups='account.group_account_manager', copy=False,
        help='Con la confirmación automática activada: si no hay una cotización pendiente de '
             'facturar que coincida, confirma igual y publica la factura sin cotización. Si no '
             'está marcado, la recepción queda en Cargado.')
