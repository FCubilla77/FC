# -*- coding: utf-8 -*-

from odoo import models, fields


class L10nPyTipoFiscal(models.Model):
    _name = 'local_py.tipo_fiscal'
    _description = 'Tipo Fiscal (Paraguay)'
    _order = 'sequence, id'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(
        string='Código',
        help='Código oficial del Tipo de Comprobante según la Tabla 4 de la '
             'Especificación Técnica de Marangatu (DNIT, RG 90/2021).',
    )
    tipo_comprobante_retencion = fields.Char(
        string='Tipo Comprobante Retención',
        help='Código de Tipo de Comprobante que exige Tesaka para el archivo de '
             'Retenciones (tabla distinta a la de Marangatu, no confundir con el campo '
             '"Código" de arriba) — se usa al generar el archivo JSON para la DNIT.',
    )
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)
    local_py_es_fisico = fields.Boolean(
        string='Es Físico', default=True,
        help='Tildado para los Tipos de Documento Fiscal en papel (Timbrado con '
             'talonario) — sin tildar para los electrónicos (ej. Factura Electronica). '
             'Se usa para filtrar qué Diarios pueden elegirse en Documentos Anulados: '
             'un talonario físico puede tener números dañados/no utilizados, un '
             'Documento Electrónico no.',
    )
