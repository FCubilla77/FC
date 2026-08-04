# -*- coding: utf-8 -*-

from odoo import models, fields


class LocalPyConceptoIva(models.Model):
    _name = 'local_py.concepto_iva'
    _description = 'Concepto IVA (Retenciones — DNIT/Tesaka)'
    _order = 'sequence, id'

    name = fields.Char(string='Nombre', required=True)
    codigo = fields.Char(string='Código', required=True, help='Código oficial (ej. IVA.1) que exige Tesaka.')
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)
