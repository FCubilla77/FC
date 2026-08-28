# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.exceptions import UserError

MAX_RANGO = 5000


class LocalPyDocumentoAnuladoRangoWizard(models.TransientModel):
    _name = 'local_py.documento_anulado_rango_wizard'
    _description = 'Registrar Documentos Anulados por Rango'

    diario_id = fields.Many2one(
        'account.journal', string='Diario', required=True,
        domain="[('type', '=', 'sale'), ('local_py_tipo_fiscal_id.local_py_es_fisico', '=', True)]",
    )
    numero_desde = fields.Char(string='Número Desde', size=15, required=True)
    numero_hasta = fields.Char(string='Número Hasta', size=15, required=True)
    motivo = fields.Char(string='Motivo', required=True)
    fecha_registro = fields.Date(
        string='Fecha de Registro', required=True, default=fields.Date.context_today,
    )

    def action_confirmar(self):
        self.ensure_one()
        Journal = self.env['account.journal']
        correlativo_desde = Journal._l10n_py_correlativo(self.numero_desde)
        correlativo_hasta = Journal._l10n_py_correlativo(self.numero_hasta)
        if correlativo_desde is None or correlativo_hasta is None:
            raise UserError(
                'Número Desde y Número Hasta tienen que tener el formato completo '
                '999-999-9999999.'
            )
        if self.numero_desde[:7] != self.numero_hasta[:7]:
            raise UserError(
                'Número Desde y Número Hasta tienen que compartir el mismo '
                'Establecimiento y Punto de Expedición.'
            )
        if correlativo_hasta < correlativo_desde:
            raise UserError('Número Hasta tiene que ser mayor o igual a Número Desde.')
        if correlativo_hasta - correlativo_desde + 1 > MAX_RANGO:
            raise UserError('El rango no puede superar los %s números por vez.' % MAX_RANGO)

        prefijo = self.numero_desde[:8]
        vals_list = [{
            'diario_id': self.diario_id.id,
            'timbrado': self.diario_id.l10n_py_timbrado,
            'numero': '%s%07d' % (prefijo, correlativo),
            'tipo_fiscal_id': self.diario_id.local_py_tipo_fiscal_id.id,
            'motivo': self.motivo,
            'fecha_registro': self.fecha_registro,
        } for correlativo in range(correlativo_desde, correlativo_hasta + 1)]

        # Todo o nada: si algún número del rango no pasa las validaciones del
        # modelo (fuera de rango, ya usado, duplicado), Odoo revierte la
        # creación completa en un solo flush — no queda una carga a medias.
        registros = self.env['local_py.documento_anulado'].create(vals_list)

        return {
            'name': 'Documentos Anulados creados',
            'type': 'ir.actions.act_window',
            'res_model': 'local_py.documento_anulado',
            'view_mode': 'list,form',
            'domain': [('id', 'in', registros.ids)],
        }
