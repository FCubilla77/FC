# -*- coding: utf-8 -*-

from odoo import models, fields


class LocalPyConceptoRentaNoResidente(models.Model):
    _name = 'local_py.concepto_renta_no_residente'
    _description = 'Concepto Renta No Residente (INR — Retenciones a Proveedores del Exterior)'
    _order = 'sequence, id'

    name = fields.Char(string='Nombre', required=True)
    codigo = fields.Char(
        string='Código', required=True,
        help='Código oficial (ej. RENTA_NO_RESIDENTE.10) que exige Tesaka.',
    )
    porcentaje_imputacion = fields.Float(
        string='% Imputación', digits=(5, 2),
        help='Porcentaje del Importe a Pagar que constituye la Base Imponible de este '
             'concepto — algunos conceptos de INR retienen sobre el importe bruto '
             'completo (100%), otros sobre una base reducida (por ejemplo, 30% o 50% '
             'del importe bruto), según lo que fija la DNIT para cada concepto.',
    )
    porcentaje = fields.Float(
        string='Porcentaje', digits=(5, 2),
        help='Porcentaje de Retención sobre la Base Imponible, para cuando NO se '
             'absorbe (se descuenta del pago al Proveedor).',
    )
    porcentaje_absorcion = fields.Float(
        string='Porcentaje Absorción', digits=(5, 2),
        help='Porcentaje de Retención sobre la Base Imponible, para cuando SÍ se '
             'absorbe (queda como un Gasto aparte para la Compañía, sin descontarle '
             'nada al Proveedor).',
    )
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)

    def _compute_display_name(self):
        for concepto in self:
            concepto.display_name = '%s - %s' % (concepto.codigo, concepto.name) if concepto.codigo else concepto.name
