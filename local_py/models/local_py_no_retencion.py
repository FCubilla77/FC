# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class LocalPyNoRetencion(models.Model):
    _name = 'local_py.no_retencion'
    _description = 'Resolución de No Retención'
    _order = 'fecha_desde desc'

    config_id = fields.Many2one(
        'local_py.configuracion_localizacion', string='Configuración', required=True, ondelete='cascade',
    )
    partner_id = fields.Many2one('res.partner', string='Proveedor', required=True)
    fecha_desde = fields.Date(string='Fecha Desde', required=True)
    fecha_hasta = fields.Date(string='Fecha Hasta', required=True)
    nro_resolucion = fields.Char(
        string='Nro. Resolución', required=True, size=15,
        help='Dato de referencia, tal como figura en la Resolución de la DNIT (puede '
             'incluir guiones, barras o letras).',
    )
    tipo_retencion = fields.Selection(
        [('iva', 'IVA'), ('renta', 'Renta')], string='Tipo de Retención', required=True,
    )

    @api.constrains('fecha_desde', 'fecha_hasta')
    def _check_fechas(self):
        for registro in self:
            if registro.fecha_desde > registro.fecha_hasta:
                raise ValidationError(
                    'La Fecha Desde no puede ser posterior a la Fecha Hasta en la '
                    'Resolución de No Retención de "%s".' % registro.partner_id.display_name
                )

