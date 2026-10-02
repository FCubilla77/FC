# -*- coding: utf-8 -*-
from odoo import fields, models

from odoo.addons.l10n_py.models.balance_general_report import fmt_pyg


class L10nPyBalanceGeneralWizard(models.TransientModel):
    _name = 'l10n_py.balance_general.wizard'
    _description = 'Asistente Balance General x Grupos de Cuentas'

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company,
    )
    fecha = fields.Date(
        string='Fecha', required=True,
        default=lambda self: fields.Date.context_today(self),
    )

    def action_ver(self):
        """Reconstruye la tabla de reporte y la abre en vista Pivote
        (principal) + Lista jerárquica, ambas nativas de Odoo — permite
        arrastrar/soltar dimensiones (Nivel 1, Grupo, Cuenta) y expandir/
        colapsar, igual que cualquier Pivote estándar."""
        self.ensure_one()
        Report = self.env['l10n_py.balance_general.report']
        Report._rebuild(self.company_id, self.fecha)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Balance General x Grupos de Cuentas al %s' % self.fecha.strftime('%d/%m/%Y'),
            'res_model': 'l10n_py.balance_general.report',
            'view_mode': 'pivot,list',
        }

    def _render_data(self):
        Report = self.env['l10n_py.balance_general.report']
        rows = Report._build_balance_general_rows(self.company_id, self.fecha)
        return {
            'doc_ids': self.ids,
            'doc_model': 'l10n_py.balance_general.wizard',
            'docs': self,
            'company': self.company_id,
            'fecha': self.fecha,
            'rows': rows,
            'fmt_pyg': fmt_pyg,
        }

    def action_imprimir(self):
        """Genera el PDF oficial (A4, márgenes estándar del proyecto)."""
        self.ensure_one()
        return self.env.ref('l10n_py.action_report_balance_general_pdf').with_context(
            l10n_py_balance_general_render_data=self._render_data(),
        ).report_action(self)

    def action_ver_html(self):
        """Vista en pantalla (HTML, de control) con el mismo cálculo que el PDF."""
        self.ensure_one()
        return self.env.ref('l10n_py.action_report_balance_general_html').with_context(
            l10n_py_balance_general_render_data=self._render_data(),
        ).report_action(self)
