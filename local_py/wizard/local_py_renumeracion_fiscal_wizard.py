# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo import fields, models
from odoo.exceptions import UserError


class LocalPyRenumeracionFiscalWizard(models.TransientModel):
    _name = 'local_py.renumeracion_fiscal.wizard'
    _description = 'Renumeración Fiscal de Asientos'

    fecha_inicial = fields.Date(string='Fecha Inicial', required=True)
    fecha_final = fields.Date(string='Fecha Final', required=True)

    def action_ejecutar(self):
        self.ensure_one()
        company = self.env.company
        fecha_inicial = self.fecha_inicial
        fecha_final = self.fecha_final

        if fecha_inicial.year != fecha_final.year:
            raise UserError('La Fecha Inicial y la Fecha Final deben pertenecer al mismo año.')
        if fecha_final < fecha_inicial:
            raise UserError('La Fecha Final no puede ser anterior a la Fecha Inicial.')

        year = fecha_inicial.year

        config = self.env['local_py.configuracion_localizacion'].search(
            [('company_id', '=', company.id)], limit=1
        )
        if not config:
            raise UserError(
                'No existe una Configuración de Localización para esta compañía. '
                'Configure primero la Renumeración de Asiento antes de continuar.'
            )
        row = config.renumeracion_ids.filtered(lambda r: r.anio == year)
        if not row:
            raise UserError(
                'No existe una fila de configuración para el año %s. Configure primero el '
                '"Número Asiento Fiscal Inicial" de ese año antes de continuar.' % year
            )
        row = row[0]
        if not row.numero_inicial:
            raise UserError(
                'El "Número Asiento Fiscal Inicial" del año %s está vacío. Complételo antes '
                'de continuar.' % year
            )

        if row.ultima_fecha_procesada:
            esperado = row.ultima_fecha_procesada + timedelta(days=1)
            if fecha_inicial != esperado:
                raise UserError(
                    'La Fecha Inicial debe ser %s (el día siguiente a la última fecha ya '
                    'procesada para el año %s). No se permiten huecos ni superposición.'
                    % (esperado.strftime('%d/%m/%Y'), year)
                )
            start_num = row.ultimo_nro_utilizado + 1
        else:
            esperado = date(year, 1, 1)
            if fecha_inicial != esperado:
                raise UserError(
                    'La primera renumeración del año %s debe comenzar el 1° de enero de ese '
                    'año (%s).' % (year, esperado.strftime('%d/%m/%Y'))
                )
            start_num = row.numero_inicial

        moves = self.env['account.move'].search([
            ('company_id', '=', company.id),
            ('state', '=', 'posted'),
            ('date', '>=', fecha_inicial),
            ('date', '<=', fecha_final),
            ('l10n_py_nro_fiscal', '=', False),
        ], order='date asc, id asc')

        next_num = start_num
        for move in moves:
            move.with_context(l10n_py_allow_nro_fiscal_write=True).write({
                'l10n_py_nro_fiscal': next_num,
            })
            next_num += 1

        vals = {'ultima_fecha_procesada': fecha_final}
        if moves:
            vals['ultimo_nro_utilizado'] = next_num - 1
        row.write(vals)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Renumeración Fiscal',
                'message': '%s asiento(s) renumerado(s) correctamente.' % len(moves),
                'type': 'success',
                'sticky': False,
            },
        }
