# -*- coding: utf-8 -*-
from datetime import date

from odoo import fields, models
from odoo.exceptions import UserError


class LocalPyLimpiarNumeracionWizard(models.TransientModel):
    _name = 'local_py.limpiar_numeracion.wizard'
    _description = 'Limpiar Numeración Fiscal'

    row_id = fields.Many2one(
        'local_py.configuracion_localizacion.renumeracion',
        string='Fila de configuración', required=True,
    )
    fecha_hasta = fields.Date(string='Fecha Hasta', readonly=True)
    fecha_desde = fields.Date(string='Fecha Desde a limpiar', required=True)

    def action_confirmar(self):
        self.ensure_one()
        row = self.row_id
        company = row.config_id.company_id
        year = row.anio

        if not row.ultima_fecha_procesada:
            raise UserError('Este año todavía no tiene ninguna numeración aplicada para limpiar.')
        if self.fecha_desde > row.ultima_fecha_procesada:
            raise UserError('"Fecha Desde" no puede ser posterior a la Última fecha procesada.')
        if self.fecha_desde.year != year:
            raise UserError('"Fecha Desde" debe pertenecer al año %s.' % year)

        moves = self.env['account.move'].search([
            ('company_id', '=', company.id),
            ('date', '>=', self.fecha_desde),
            ('date', '<=', row.ultima_fecha_procesada),
            ('l10n_py_nro_fiscal', '!=', False),
        ])
        moves.with_context(l10n_py_allow_nro_fiscal_write=True).write({
            'l10n_py_nro_fiscal': False,
        })

        remaining = self.env['account.move'].search([
            ('company_id', '=', company.id),
            ('date', '>=', date(year, 1, 1)),
            ('date', '<=', date(year, 12, 31)),
            ('l10n_py_nro_fiscal', '!=', False),
        ], order='date desc, l10n_py_nro_fiscal desc', limit=1)

        if remaining:
            row.write({
                'ultima_fecha_procesada': remaining.date,
                'ultimo_nro_utilizado': remaining.l10n_py_nro_fiscal,
            })
        else:
            row.write({
                'ultima_fecha_procesada': False,
                'ultimo_nro_utilizado': False,
            })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Limpiar numeración',
                'message': '%s asiento(s) actualizados.' % len(moves),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
