# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    fe_py_recepcion_confirmar_auto = fields.Boolean(
        string='Confirmar Facturas Electrónicas Recibidas - Automáticamente',
        groups='account.group_account_manager', copy=False,
        help='Al leer el XML de este proveedor, si todos los controles pasan sin avisos ni '
             'impedimentos y todos los productos vienen de equivalencias ya confirmadas, se '
             'confirma la recepción y se publica la factura (o nota) de proveedor. Si algo '
             'falla, queda en Cargado para revisarla a mano.')
