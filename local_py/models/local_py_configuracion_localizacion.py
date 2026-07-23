# -*- coding: utf-8 -*-

from odoo import fields, models


class LocalPyConfiguracionLocalizacion(models.Model):
    _name = 'local_py.configuracion_localizacion'
    _description = 'Configuraciones de Localización Paraguay'

    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company,
    )
    renumeracion_ids = fields.One2many(
        'local_py.configuracion_localizacion.renumeracion', 'config_id',
        string='Renumeración de Asiento',
    )

    _sql_constraints = [
        ('company_uniq', 'unique(company_id)',
         'Ya existe una Configuración de Localización para esta compañía.'),
    ]


class LocalPyConfiguracionLocalizacionRenumeracion(models.Model):
    _name = 'local_py.configuracion_localizacion.renumeracion'
    _description = 'Renumeración de Asiento (por Año)'
    _order = 'anio'

    config_id = fields.Many2one(
        'local_py.configuracion_localizacion', string='Configuración',
        required=True, ondelete='cascade',
    )
    anio = fields.Integer(string='Año')
    numero_inicial = fields.Integer(string='Número Asiento Fiscal Inicial')
    ultimo_nro_utilizado = fields.Integer(string='Ultimo Nro. Utilizado', readonly=True)
    ultima_fecha_procesada = fields.Date(string='Ultima fecha procesada', readonly=True)

    def action_limpiar_numeracion(self):
        self.ensure_one()
        return {
            'name': 'Limpiar numeración',
            'type': 'ir.actions.act_window',
            'res_model': 'local_py.limpiar_numeracion.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_row_id': self.id,
                'default_fecha_hasta': self.ultima_fecha_procesada,
            },
        }
