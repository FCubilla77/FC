# -*- coding: utf-8 -*-
from odoo import fields, models


class FePyRecepcionConfiguracion(models.Model):
    _inherit = 'fe_py_recepcion.configuracion'

    vincular_compras = fields.Boolean(
        string='Vincular con cotizaciones', default=True,
        help='Permite asignar una cotización (orden de compra) a cada factura electrónica '
             'recibida y una línea de la cotización a cada línea del XML. La factura de '
             'proveedor generada queda vinculada con la cotización, igual que si se hubiera '
             'cargado a mano.')
