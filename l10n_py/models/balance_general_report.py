# -*- coding: utf-8 -*-
from odoo import api, fields, models

# Clasificación por TIPO de cuenta (account.account.account_type), no por el
# código: así el informe sirve con el plan Paraguay y con un plan propio del
# cliente con otra numeración.
TIPOS_BALANCE = (
    'asset_receivable', 'asset_cash', 'asset_current', 'asset_non_current',
    'asset_prepayments', 'asset_fixed',
    'liability_payable', 'liability_credit_card', 'liability_current',
    'liability_non_current',
    'equity', 'equity_unaffected',
)
TIPOS_INGRESO = ('income', 'income_other')
TIPOS_RESULTADO = TIPOS_INGRESO + (
    'expense', 'expense_other', 'expense_depreciation', 'expense_direct_cost',
)


def _info_grupo(grupo):
    """(nivel, raíz) de un account.group según su jerarquía de padres: nivel 1 para
    un grupo raíz, 2 para su hijo, etc. Sin grupo: (0, vacío)."""
    nivel = 0
    raiz = grupo
    vistos = set()
    while grupo and grupo.id not in vistos:
        vistos.add(grupo.id)
        nivel += 1
        raiz = grupo
        grupo = grupo.parent_id
    return nivel, raiz


def fmt_pyg(value):
    """Formato Guaraníes: sin decimales, separador de miles '.', signo
    negativo entre paréntesis (convención contable)."""
    value = round(value or 0.0)
    texto = '{:,.0f}'.format(abs(value)).replace(',', '.')
    if value < 0:
        return '(%s)' % texto
    return texto


class L10nPyBalanceGeneralReport(models.Model):
    """Tabla 'scratch' con el último Balance General x Grupos de Cuentas
    generado (se vacía y reconstruye en cada 'Ver' del wizard, para la
    compañía/fecha elegidas). Pensada para explorarse con la vista Pivote
    nativa de Odoo (agrupar por Grupo raíz / Grupo / Cuenta) y también en
    lista jerárquica (Títulos e Imputables intercalados, indentados por 'nivel').

    No depende de local_py: usa únicamente modelos nativos de 'account'."""
    _name = 'l10n_py.balance_general.report'
    _description = 'Balance General x Grupos de Cuentas (Paraguay)'
    _order = 'orden, id'
    _rec_name = 'name'

    company_id = fields.Many2one('res.company', string='Compañía', readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda', readonly=True)
    fecha = fields.Date(string='Fecha', readonly=True)
    orden = fields.Integer(string='Orden', readonly=True)
    code = fields.Char(string='Código', readonly=True)
    name = fields.Char(string='Nombre', readonly=True)
    tipo = fields.Selection(
        [('titulo', 'Título'), ('imputable', 'Imputable'), ('especial', 'Línea especial')],
        string='Tipo', readonly=True,
    )
    nivel = fields.Integer(string='Nivel', readonly=True)
    raiz_id = fields.Many2one('account.group', string='Grupo raíz', readonly=True)
    group_id = fields.Many2one('account.group', string='Grupo de cuentas', readonly=True)
    account_id = fields.Many2one('account.account', string='Cuenta', readonly=True)
    saldo = fields.Monetary(string='Saldo', readonly=True, currency_field='currency_id')

    def action_open_account(self):
        """Abre la ficha de la cuenta contable real. Solo aplica a filas Imputables."""
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

    # ------------------------------------------------------------------
    # Construcción de filas (compartida entre la vista en pantalla/pivote
    # y el reporte QWeb en PDF — ambos llaman a este mismo método para
    # garantizar que PDF y pantalla muestren siempre el mismo número).
    # ------------------------------------------------------------------
    @api.model
    def _compute_saldo_cuentas(self, company, fecha_desde, fecha_hasta, tipos, tipos_signo_invertido=()):
        """Devuelve {account: saldo} para las cuentas de la compañía cuyo tipo de
        cuenta esté en 'tipos', con movimiento validado entre fecha_desde y
        fecha_hasta (incluidas). Para los tipos en 'tipos_signo_invertido' el
        saldo se calcula Crédito-Débito (Ingresos, para mostrarlos en positivo);
        para el resto, Débito-Crédito."""
        self = self.with_company(company)
        grupos = self.env['account.move.line']._read_group(
            [
                ('company_id', '=', company.id),
                ('parent_state', '=', 'posted'),
                ('date', '>=', fecha_desde),
                ('date', '<=', fecha_hasta),
                ('account_id.account_type', 'in', list(tipos)),
            ],
            groupby=['account_id'],
            aggregates=['debit:sum', 'credit:sum'],
        )
        saldo_por_cuenta = {}
        for account, debito, credito in grupos:
            if account.account_type in tipos_signo_invertido:
                saldo = credito - debito
            else:
                saldo = debito - credito
            if saldo:
                saldo_por_cuenta[account] = saldo
        return saldo_por_cuenta

    @api.model
    def _build_titulo_imputable_rows(self, saldo_por_cuenta):
        """A partir de {account: saldo}, sube cada saldo a todos sus
        account.group ancestros y devuelve la lista combinada de filas
        Título + Imputable ordenada por código (mismo criterio que
        local_py._build_balance_style_rows)."""
        saldo_por_grupo = {}
        for account, saldo in saldo_por_cuenta.items():
            grupo = account.group_id
            vistos = set()
            while grupo and grupo.id not in vistos:
                vistos.add(grupo.id)
                saldo_por_grupo[grupo] = saldo_por_grupo.get(grupo, 0.0) + saldo
                grupo = grupo.parent_id

        nodos = []
        for grupo, saldo in saldo_por_grupo.items():
            nivel, raiz = _info_grupo(grupo)
            nodos.append({
                'code': grupo.code_prefix_start or '',
                'tipo': 'titulo',
                'name': grupo.name,
                'nivel': nivel,
                'raiz_id': raiz.id,
                'group_id': grupo.id,
                'account_id': False,
                'saldo': saldo,
            })
        for account, saldo in saldo_por_cuenta.items():
            nivel, raiz = _info_grupo(account.group_id)
            nodos.append({
                'code': account.code or '',
                'tipo': 'imputable',
                'name': account.name,
                'nivel': nivel + 1,
                'raiz_id': raiz.id,
                'group_id': account.group_id.id,
                'account_id': account.id,
                'saldo': saldo,
            })
        nodos.sort(key=lambda n: n['code'])
        return nodos

    @api.model
    def _build_balance_general_rows(self, company, fecha):
        """Devuelve la lista de filas (dict) del Balance General x Grupos
        de Cuentas a 'fecha', para 'company':

        - Activo/Pasivo/Patrimonio (cuentas de tipo Activo, Pasivo y Patrimonio):
          saldo Débito-Crédito acumulado desde el inicio del ejercicio fiscal que
          contiene 'fecha' (vía Asiento de Apertura) hasta 'fecha'.
        - Una fila especial adicional, al final del grupo raíz de Patrimonio:
          "RESULTADO DEL EJERCICIO EN CURSO", con el resultado (cuentas de
          Ingresos menos Costos/Gastos, por tipo de cuenta) del ejercicio en
          curso hasta 'fecha'. Representa el resultado que todavía NO fue
          cerrado contablemente (eso solo ocurre al ejecutar el proceso de
          Cierre de Ejercicio, al final del año) — por lo tanto nunca está
          ya incluido en el saldo real de ninguna cuenta de Patrimonio.
        """
        self = self.with_company(company)
        company = company.with_company(company)
        fy = company.compute_fiscalyear_dates(fecha)
        fecha_desde = fy['date_from']

        saldo_balance = self._compute_saldo_cuentas(company, fecha_desde, fecha, tipos=TIPOS_BALANCE)
        rows = self._build_titulo_imputable_rows(saldo_balance)

        saldo_resultado = self._compute_saldo_cuentas(
            company, fecha_desde, fecha, tipos=TIPOS_RESULTADO,
            tipos_signo_invertido=TIPOS_INGRESO,
        )
        # Los saldos de Ingresos vienen en positivo (Crédito-Débito) y los de Costos/
        # Gastos también (Débito-Crédito): el resultado es Ingresos MENOS Costos/Gastos.
        resultado_en_curso = sum(
            saldo if account.account_type in TIPOS_INGRESO else -saldo
            for account, saldo in saldo_resultado.items())

        # La fila va dentro del grupo raíz de la cuenta Resultado del Ejercicio
        # (Patrimonio); si no se puede determinar, queda al final.
        cuenta = company.l10n_py_cuenta_resultado_ejercicio_id
        if not cuenta:
            cuenta = self.env['account.account'].search([
                ('company_ids', 'in', company.id),
                ('account_type', '=', 'equity_unaffected')], limit=1)
        nivel, raiz = _info_grupo(cuenta.group_id) if cuenta else (0, self.env['account.group'])
        fila = {
            'code': '',
            'tipo': 'especial',
            'name': 'RESULTADO DEL EJERCICIO EN CURSO (no cerrado)',
            'nivel': 2 if raiz else 1,
            'raiz_id': raiz.id,
            'group_id': False,
            'account_id': False,
            'saldo': resultado_en_curso,
        }
        posicion = len(rows)
        if raiz:
            indices = [i for i, r in enumerate(rows) if r['raiz_id'] == raiz.id]
            if indices:
                posicion = indices[-1] + 1
        rows.insert(posicion, fila)
        return rows

    @api.model
    def _rebuild(self, company, fecha):
        """Vacía la tabla y la reconstruye para 'company'/'fecha'. Usa
        sudo() para no depender de los permisos de escritura del usuario
        que la ejecuta (igual criterio que local_py.plan_cuentas.report)."""
        self = self.sudo()
        self.search([]).unlink()
        rows = self._build_balance_general_rows(company, fecha)
        vals_list = []
        for orden, row in enumerate(rows):
            vals_list.append({
                'orden': orden,
                'company_id': company.id,
                'fecha': fecha,
                'code': row['code'],
                'name': row['name'],
                'tipo': row['tipo'],
                'nivel': row['nivel'],
                'raiz_id': row['raiz_id'],
                'group_id': row['group_id'],
                'account_id': row['account_id'],
                'saldo': row['saldo'],
            })
        return self.create(vals_list)


class ReportBalanceGeneral(models.AbstractModel):
    """Proveedor de datos del QWeb (PDF y vista en pantalla). Recibe las
    filas ya calculadas por el wizard vía contexto — no vuelve a golpear
    la base — así se garantiza que PDF/pantalla y la vista Pivote muestren
    siempre exactamente el mismo cálculo."""
    _name = 'report.l10n_py.report_balance_general_document'
    _description = 'Reporte Balance General x Grupos de Cuentas'

    def _get_report_values(self, docids, data=None):
        return self.env.context.get('l10n_py_balance_general_render_data', {})
