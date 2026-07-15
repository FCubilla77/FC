# -*- coding: utf-8 -*-
from odoo import api, fields, models

# Misma lista de valores que account.account.account_type (Odoo 19), copiada
# aquí para no depender de que ese modelo esté cargado al definir el campo.
ACCOUNT_TYPE_SELECTION = [
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


# Etiquetas fijas para el filtro por Nivel 1 del reporte (se calculan a
# partir del primer segmento del código de cuenta, no dependen de que
# existan account.group de nivel 1 raíz).
NIVEL_1_LABELS = [
    ('1', '1 - Activo'),
    ('2', '2 - Pasivo'),
    ('3', '3 - Patrimonio Neto'),
    ('4', '4 - Ingresos Operativos'),
    ('5', '5 - Costos Operativos'),
    ('6', '6 - Otros Ingresos'),
    ('7', '7 - Gastos'),
]

# Códigos válidos para el filtro Nivel 1 (deben coincidir con NIVEL_1_LABELS).
VALID_NIVEL_1_CODES = {code for code, _label in NIVEL_1_LABELS}


def _safe_nivel_1(code):
    """Devuelve el primer segmento del código como valor de 'nivel_1' SOLO
    si coincide con una de las 7 raíces esperadas del plan de Paraguay
    (NIVEL_1_LABELS). Cualquier otra cuenta/grupo (por ejemplo, cuentas
    técnicas que Odoo o algún otro módulo instalado puedan crear con una
    codificación distinta, como códigos numéricos largos sin puntos) queda
    sin clasificar (False) en vez de romper el campo Selection."""
    if not code:
        return False
    primer_segmento = code.split('.')[0]
    return primer_segmento if primer_segmento in VALID_NIVEL_1_CODES else False


class L10nPyPlanCuentasReport(models.Model):
    _name = 'local_py.plan_cuentas.report'
    _description = 'Reporte Plan de Cuentas Paraguay'
    _order = 'code'
    _rec_name = 'code'

    code = fields.Char(string='Código', readonly=True)
    name = fields.Char(string='Nombre', readonly=True)
    tipo = fields.Selection(
        [('title', 'Título'), ('imputable', 'Imputable')],
        string='Tipo', readonly=True,
    )
    nivel = fields.Integer(string='Nivel', readonly=True)
    account_type = fields.Selection(ACCOUNT_TYPE_SELECTION, string='Tipo de cuenta', readonly=True)
    group_name = fields.Char(string='Grupo', readonly=True)
    nivel_1 = fields.Selection(NIVEL_1_LABELS, string='Nivel 1', readonly=True)
    account_id = fields.Many2one('account.account', string='Cuenta', readonly=True)
    group_id = fields.Many2one('account.group', string='Grupo de cuentas', readonly=True)

    def action_open_account(self):
        """Abre la ficha de la cuenta contable real (account.account) para
        poder modificar su configuración. Solo aplica a filas Imputables."""
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
        (account.group + account.account). Se invoca automáticamente al
        aplicar/restablecer la configuración de Paraguay (hooks.py), y
        también puede dispararse a mano con el botón 'Actualizar' de la
        lista. Usa sudo() para no depender de los permisos de escritura del
        usuario que la ejecuta."""
        self = self.sudo()
        self.search([]).unlink()

        vals_list = []
        groups = self.env['account.group'].sudo().search([], order='code_prefix_start')
        for group in groups:
            code = group.code_prefix_start or ''
            vals_list.append({
                'code': code,
                'name': group.name,
                'tipo': 'title',
                'nivel': code.count('.') + 1 if code else 0,
                'group_name': group.parent_id.name or '',
                'nivel_1': _safe_nivel_1(code),
                'group_id': group.id,
            })

        accounts = self.env['account.account'].sudo().search([], order='code')
        for account in accounts:
            code = account.code or ''
            vals_list.append({
                'code': code,
                'name': account.name,
                'tipo': 'imputable',
                'nivel': code.count('.') + 1 if code else 0,
                'account_type': account.account_type,
                'group_name': account.group_id.name or '',
                'nivel_1': _safe_nivel_1(code),
                'account_id': account.id,
            })

        self.create(vals_list)

    def action_manual_refresh(self):
        """Botón 'Actualizar' de la lista: vuelve a generar el reporte y
        recarga la vista. Es un botón de tipo 'object' (no ejecuta código de
        servidor), por lo que cualquier usuario con acceso de lectura al
        modelo puede usarlo sin necesitar permisos de Administración."""
        self._rebuild()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
