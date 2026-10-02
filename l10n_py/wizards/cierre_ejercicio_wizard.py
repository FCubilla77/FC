# -*- coding: utf-8 -*-
from odoo import fields, models


class L10nPyCierreEjercicioWizard(models.TransientModel):
    _name = 'l10n_py.cierre_ejercicio.wizard'
    _description = 'Asistente de Cierre de Ejercicio (Paraguay)'

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company,
    )
    anio = fields.Integer(
        string='Ejercicio a cerrar', required=True,
        default=lambda self: fields.Date.context_today(self).year - 1,
        help='Año calendario a cerrar (asume ejercicio fiscal = año calendario, '
             'según la configuración de Fin de Ejercicio Fiscal de la compañía).',
    )

    def action_confirmar(self):
        self.ensure_one()
        cierre = self.env['l10n_py.cierre_ejercicio'].action_cerrar_ejercicio(self.company_id, self.anio)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_py.cierre_ejercicio',
            'res_id': cierre.id,
            'view_mode': 'form',
            'target': 'current',
        }
