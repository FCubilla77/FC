# -*- coding: utf-8 -*-

from odoo import fields, models


class LocalPyTipoFiscal(models.Model):
    _inherit = 'local_py.tipo_fiscal'

    fe_py_es_electronico = fields.Boolean(
        string='Es Electrónico',
        help='Marca los Tipos Fiscales que corresponden a un Documento '
             'Electrónico SIFEN (Factura Electrónica, Nota de Crédito '
             'Electrónica, Nota de Débito Electrónica, etc.). FE_Py usa este '
             'campo, al confirmar un comprobante, para saber si corresponde '
             'generar su Documento Electrónico automáticamente. No reemplaza '
             'el catálogo duplicado (Factura vs. Factura Electrónica, etc.) '
             '— es un marcador técnico adicional sobre esos mismos registros.',
    )
