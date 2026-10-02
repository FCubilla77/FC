# -*- coding: utf-8 -*-
from odoo import api, fields, models

# Mismas 7 raíces del plan de cuentas Paraguay. Se duplica acá (en vez de
# importar de local_py) a propósito: l10n_py no depende de local_py.
NIVEL_1_LABELS = [
    ('1', 'ACTIVO'),
    ('2', 'PASIVO'),
    ('3', 'PATRIMONIO NETO'),
    ('4', 'INGRESOS'),
    ('5', 'COSTOS'),
    ('6', 'OTROS INGRESOS'),
    ('7', 'GASTOS'),
]
VALID_NIVEL_1_CODES = {code for code, _label in NIVEL_1_LABELS}


def _safe_nivel_1(code):
    """Devuelve el primer segmento del código como 'nivel_1' solo si
    coincide con una de las 7 raíces esperadas. Cualquier otra cuenta
    (técnica, de otro módulo, etc.) queda sin clasificar (False) en vez de
    romper el campo Selection — mismo criterio que local_py.plan_cuentas.report."""
    if not code:
        return False
    primer_segmento = code.split('.')[0]
    return primer_segmento if primer_segmento in VALID_NIVEL_1_CODES else False


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
    nativa de Odoo (agrupar por Nivel 1 / Grupo / Cuenta) y también en
    lista jerárquica (igual criterio visual que local_py.plan_cuentas.report:
    Títulos e Imputables intercalados por código, indentados por 'nivel').

    No depende de local_py: usa únicamente modelos nativos de 'account'."""
    _name = 'l10n_py.balance_general.report'
    _description = 'Balance General x Grupos de Cuentas (Paraguay)'
    _order = 'code'
    _rec_name = 'name'

    company_id = fields.Many2one('res.company', string='Compañía', readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda', readonly=True)
    fecha = fields.Date(string='Fecha', readonly=True)
    code = fields.Char(string='Código', readonly=True)
    name = fields.Char(string='Nombre', readonly=True)
    tipo = fields.Selection(
        [('titulo', 'Título'), ('imputable', 'Imputable'), ('especial', 'Línea especial')],
        string='Tipo', readonly=True,
    )
    nivel = fields.Integer(string='Nivel', readonly=True)
    nivel_1 = fields.Selection(NIVEL_1_LABELS, string='Nivel 1', readonly=True)
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
    def _compute_saldo_cuentas(self, company, fecha_desde, fecha_hasta, prefijos, prefijos_signo_invertido=()):
        """Devuelve {account: saldo} para las cuentas imputables de la
        compañía cuyo primer segmento de código esté en 'prefijos', con
        movimiento validado entre fecha_desde y fecha_hasta (incluidas).
        Para los prefijos en 'prefijos_signo_invertido' el saldo se calcula
        Crédito-Débito (se usa en Ingresos, para mostrarlos en positivo);
        para el resto, Débito-Crédito."""
        accounts = self.env['account.account'].search([
            ('company_ids', 'in', company.id),
        ])
        accounts = accounts.filtered(
            lambda a: (a.code or '').split('.')[0] in prefijos
        )
        if not accounts:
            return {}

        domain_base = [
            ('move_id.company_id', '=', company.id),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', fecha_desde),
            ('date', '<=', fecha_hasta),
        ]
        saldo_por_cuenta = {}
        for account in accounts:
            lines = self.env['account.move.line'].search(
                domain_base + [('account_id', '=', account.id)]
            )
            if not lines:
                continue
            segmento = (account.code or '').split('.')[0]
            if segmento in prefijos_signo_invertido:
                saldo = sum(lines.mapped('credit')) - sum(lines.mapped('debit'))
            else:
                saldo = sum(lines.mapped('debit')) - sum(lines.mapped('credit'))
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
            code = grupo.code_prefix_start or ''
            nodos.append({
                'code': code,
                'tipo': 'titulo',
                'name': grupo.name,
                'nivel': code.count('.') + 1 if code else 0,
                'nivel_1': _safe_nivel_1(code),
                'group_id': grupo.id,
                'account_id': False,
                'saldo': saldo,
            })
        for account, saldo in saldo_por_cuenta.items():
            code = account.code or ''
            nodos.append({
                'code': code,
                'tipo': 'imputable',
                'name': account.name,
                'nivel': code.count('.') + 1 if code else 0,
                'nivel_1': _safe_nivel_1(code),
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

        - Activo/Pasivo/Patrimonio (prefijos 1,2,3): saldo Débito-Crédito
          acumulado desde el inicio del ejercicio fiscal que contiene
          'fecha' (vía Asiento de Apertura) hasta 'fecha'.
        - Una fila especial adicional, bajo Patrimonio: "RESULTADO DEL
          EJERCICIO EN CURSO", con el resultado (Ingresos - Costos/Gastos,
          prefijos 4/5/6/7, signo invertido en 4/6) del ejercicio en curso
          hasta 'fecha'. Representa el resultado que todavía NO fue
          cerrado contablemente (eso solo ocurre al ejecutar el proceso de
          Cierre de Ejercicio, al final del año) — por lo tanto nunca está
          ya incluido en el saldo real de ninguna cuenta de Patrimonio.
        """
        fy = company.compute_fiscalyear_dates(fecha)
        fecha_desde = fy['date_from']

        saldo_balance = self._compute_saldo_cuentas(company, fecha_desde, fecha, prefijos=('1', '2', '3'))
        rows = self._build_titulo_imputable_rows(saldo_balance)

        saldo_resultado = self._compute_saldo_cuentas(
            company, fecha_desde, fecha, prefijos=('4', '5', '6', '7'),
            prefijos_signo_invertido=('4', '6'),
        )
        resultado_en_curso = sum(saldo_resultado.values())
        rows.append({
            'code': '3.99',
            'tipo': 'especial',
            'name': 'RESULTADO DEL EJERCICIO EN CURSO (no cerrado)',
            'nivel': 2,
            'nivel_1': '3',
            'group_id': False,
            'account_id': False,
            'saldo': resultado_en_curso,
        })
        rows.sort(key=lambda n: n['code'])
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
        for row in rows:
            vals_list.append({
                'company_id': company.id,
                'fecha': fecha,
                'code': row['code'],
                'name': row['name'],
                'tipo': row['tipo'],
                'nivel': row['nivel'],
                'nivel_1': row['nivel_1'],
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
