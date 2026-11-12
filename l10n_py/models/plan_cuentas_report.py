# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .balance_general_report import _info_grupo

# Misma lista de valores que account.account.account_type (Odoo 19), copiada
# aquí para no depender de que ese modelo esté cargado al definir el campo.
PLAN_ACCOUNT_TYPE_SELECTION = [
    ('asset_receivable', 'Receivable'),
    ('asset_cash', 'Bank and Cash'),
    ('asset_current', 'Current Assets'),
    ('asset_non_current', 'Non-current Assets'),
    ('asset_prepayments', 'Prepayments'),
    ('asset_fixed', 'Fixed Assets'),
    ('liability_payable', 'Payable'),
    ('liability_credit_card', 'Credit Card'),
    ('liability_current', 'Current Liabilities'),
    ('liability_non_current', 'Non-current Liabilities'),
    ('equity', 'Equity'),
    ('equity_unaffected', 'Current Year Earnings'),
    ('income', 'Income'),
    ('income_other', 'Other Income'),
    ('expense', 'Expenses'),
    ('expense_other', 'Other Expenses'),
    ('expense_depreciation', 'Depreciation'),
    ('expense_direct_cost', 'Cost of Revenue'),
    ('off_balance', 'Off-Balance Sheet'),
]

class L10nPyPlanCuentasReport(models.Model):
    """Listado único y ordenado del plan de cuentas: Títulos (account.group) e
    Imputables (account.account) intercalados por código, con filtro por Grupo raíz
    (el grupo de nivel 1 de cada cuenta, según la jerarquía de grupos).

    Tabla 'scratch': se vacía y reconstruye cada vez que se abre el reporte, a
    partir de los datos actuales, sin importar qué módulo cargó el plan.

    No depende de local_py: usa únicamente modelos nativos de 'account'. Es un
    informe de consulta: nunca se bloquea por licencia."""
    _name = 'l10n_py.plan_cuentas.report'
    _description = 'Reporte Plan de Cuentas (Paraguay)'
    _order = 'code'
    _rec_name = 'code'

    company_id = fields.Many2one('res.company', string='Compañía', readonly=True)
    code = fields.Char(string='Código', readonly=True)
    name = fields.Char(string='Nombre', readonly=True)
    tipo = fields.Selection(
        [('title', 'Título'), ('imputable', 'Imputable')],
        string='Tipo', readonly=True,
    )
    nivel = fields.Integer(string='Nivel', readonly=True)
    account_type = fields.Selection(PLAN_ACCOUNT_TYPE_SELECTION, string='Tipo de cuenta', readonly=True)
    group_name = fields.Char(string='Grupo', readonly=True)
    raiz_id = fields.Many2one('account.group', string='Grupo raíz', readonly=True)
    account_id = fields.Many2one('account.account', string='Cuenta', readonly=True)
    group_id = fields.Many2one('account.group', string='Grupo de cuentas', readonly=True)

    def action_open_account(self):
        """Abre la ficha de la cuenta contable real (account.account) para poder
        modificar su configuración. Solo aplica a filas Imputables."""
        self.ensure_one()
        if not self.account_id:
            return {'type': 'ir.actions.act_window_close'}
        return {
            'type': 'ir.actions.act_window',
            'name': self.account_id.display_name,
            'res_model': 'account.account',
            'res_id': self.account_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def _rebuild(self):
        """Reconstruye el reporte a partir del plan de cuentas actual
        (account.group + account.account) de todas las compañías; cada usuario ve
        solo las filas de sus compañías activas (regla de registro). Usa sudo()
        para no depender de los permisos de escritura de quien lo ejecuta."""
        self = self.sudo()
        self.search([]).unlink()

        vals_list = []
        grupos = self.env['account.group'].sudo().search([], order='code_prefix_start')
        for grupo in grupos:
            code = grupo.code_prefix_start or ''
            nivel, raiz = _info_grupo(grupo)
            vals_list.append({
                'company_id': grupo.company_id.id,
                'code': code,
                'name': grupo.name,
                'tipo': 'title',
                'nivel': nivel,
                'group_name': grupo.parent_id.name or '',
                'raiz_id': raiz.id,
                'group_id': grupo.id,
            })

        # El código de una cuenta depende de la compañía (en Odoo 19 se resuelve
        # contra la compañía del entorno), por eso se recorre compañía por compañía.
        for compania in self.env['res.company'].sudo().search([]):
            cuentas = self.env['account.account'].sudo().with_company(compania).search(
                [('company_ids', 'in', compania.id)], order='code')
            for cuenta in cuentas:
                code = cuenta.code or ''
                nivel, raiz = _info_grupo(cuenta.group_id)
                vals_list.append({
                    'company_id': compania.id,
                    'code': code,
                    'name': cuenta.name,
                    'tipo': 'imputable',
                    'nivel': nivel + 1,
                    'account_type': cuenta.account_type,
                    'group_name': cuenta.group_id.name or '',
                    'raiz_id': raiz.id,
                    'account_id': cuenta.id,
                })

        self.create(vals_list)

    @api.model
    def action_open_report(self):
        """Punto de entrada del menú: reconstruye el listado con los datos de
        ese momento y lo abre (así nunca muestra un plan desactualizado)."""
        self._rebuild()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Plan de Cuentas',
            'res_model': self._name,
            'view_mode': 'list',
            'views': [(False, 'list')],
            'search_view_id': [self.env.ref('l10n_py.view_l10n_py_plan_cuentas_report_search').id, 'search'],
            'target': 'current',
        }

    def action_manual_refresh(self):
        """Botón 'Actualizar' de la lista: vuelve a generar el reporte y recarga
        la vista. Es un botón 'object', por lo que cualquier usuario con acceso de
        lectura al modelo puede usarlo."""
        self._rebuild()
        return {'type': 'ir.actions.client', 'tag': 'reload'}
