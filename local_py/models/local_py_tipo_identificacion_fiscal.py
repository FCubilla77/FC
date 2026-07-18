# -*- coding: utf-8 -*-

from odoo import models, fields


class L10nPyTipoIdentificacionFiscal(models.Model):
    _name = 'local_py.tipo_identificacion_fiscal'
    _description = 'Tipo de Identificación Fiscal (Paraguay)'
    _order = 'sequence, id'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(
        string='Código',
        required=True,
        help='Código oficial según la Tabla 3 de la Especificación Técnica '
             'de Marangatu (DNIT, RG 90/2021).',
    )
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)
