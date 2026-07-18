# -*- coding: utf-8 -*-

from odoo import models, fields


class L10nPyImputacionTributaria(models.Model):
    _name = 'local_py.imputacion_tributaria'
    _description = 'Imputación Tributaria (Paraguay)'
    _order = 'sequence, id'

    name = fields.Char(string='Nombre', required=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)
