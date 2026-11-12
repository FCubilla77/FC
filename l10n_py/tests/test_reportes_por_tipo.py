# -*- coding: utf-8 -*-
"""Balance General, Cierre de Ejercicio y Plan de Cuentas guiados por el TIPO de
cuenta y la jerarquía de grupos (no por el código): sirven con el plan Paraguay y
con un plan propio del cliente con otra numeración."""
from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestReportesPorTipoL10nPy(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({
            'name': 'Empresa Por Tipo Test',
            'country_id': cls.env.ref('base.py').id,
            'currency_id': cls.env.ref('base.PYG').id,
        })
        cls.env['account.chart.template'].with_company(cls.company).try_loading(
            'py', cls.company, install_demo=False)
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=cls.company.ids))
        ref = cls.env['account.chart.template'].with_company(cls.company).ref
        cls.cuenta_cliente = ref('py_1_01_03_01_001')
        cls.cuenta_ingreso = ref('py_4_01_01_01_001')
        cls.cuenta_gasto = ref('py_5_01_01_01_001')
        cls.cuenta_resultado = ref('py_3_03_01_01_002')
        cls.diario = cls.env['account.journal'].search([
            ('company_id', '=', cls.company.id), ('type', '=', 'general')], limit=1)
        cls.anio = fields.Date.today().year
        cls.Report = cls.env['l10n_py.balance_general.report']

    def _fin(self):
        return fields.Date.from_string('%s-12-31' % self.anio)

    def _asiento(self, fecha, debe, haber, monto):
        move = self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.diario.id,
            'company_id': self.company.id, 'date': fecha,
            'line_ids': [
                (0, 0, {'account_id': debe.id, 'debit': monto, 'credit': 0.0}),
                (0, 0, {'account_id': haber.id, 'debit': 0.0, 'credit': monto}),
            ],
        })
        move.action_post()
        return move

    def _cuenta(self, code, tipo, name=None):
        return self.env['account.account'].with_company(self.company).create({
            'code': code, 'name': name or ('Cuenta %s' % code), 'account_type': tipo,
            'company_ids': [(6, 0, self.company.ids)],
        })

    def _saldo(self, cuenta, hasta):
        lineas = self.env['account.move.line'].search([
            ('account_id', '=', cuenta.id), ('parent_state', '=', 'posted'),
            ('date', '<=', hasta)])
        return sum(lineas.mapped('balance'))

    # -- Plan estándar: el resultado no cambia respecto del criterio por prefijo ----

    def test_01_niveles_y_raices_del_plan_estandar(self):
        self._asiento('%s-05-10' % self.anio, self.cuenta_cliente, self.cuenta_ingreso, 100.0)
        filas = self.Report._build_balance_general_rows(self.company, self._fin())
        for fila in filas:
            if fila['tipo'] == 'especial':
                continue
            # El nivel por jerarquía coincide con el que daban los puntos del código.
            self.assertEqual(fila['nivel'], fila['code'].count('.') + 1, fila['code'])
        Plan = self.env['l10n_py.plan_cuentas.report']
        Plan._rebuild()
        todas = Plan.search([('company_id', '=', self.company.id)])
        for fila in todas:
            self.assertEqual(fila.nivel, fila.code.count('.') + 1, fila.code)
        raices = set(todas.mapped('raiz_id.name'))
        self.assertEqual(raices, {
            'ACTIVO', 'PASIVO', 'PATRIMONIO NETO', 'INGRESOS', 'COSTOS',
            'OTROS INGRESOS', 'GASTOS'})

    def test_02_balance_general_con_resultado_en_curso_dentro_de_patrimonio(self):
        capital = self.env['account.account'].with_company(self.company).search([
            ('company_ids', 'in', self.company.id), ('account_type', '=', 'equity')], limit=1)
        self._asiento('%s-01-05' % self.anio, self.cuenta_cliente, capital, 500.0)
        self._asiento('%s-05-10' % self.anio, self.cuenta_cliente, self.cuenta_ingreso, 1000.0)
        self._asiento('%s-06-10' % self.anio, self.cuenta_gasto, self.cuenta_cliente, 300.0)
        filas = self.Report._build_balance_general_rows(self.company, self._fin())
        cliente = next(f for f in filas if f['account_id'] == self.cuenta_cliente.id)
        self.assertEqual(cliente['saldo'], 1200.0)
        especial = next(f for f in filas if f['tipo'] == 'especial')
        self.assertEqual(especial['saldo'], 700.0)
        fila_capital = next(f for f in filas if f['account_id'] == capital.id)
        # Va en el grupo raíz de Patrimonio, después de sus cuentas.
        self.assertEqual(especial['raiz_id'], fila_capital['raiz_id'])
        self.assertGreater(filas.index(especial), filas.index(fila_capital))
        # Ninguna cuenta de resultados aparece en el balance.
        self.assertFalse([f for f in filas if f['account_id'] in (
            self.cuenta_ingreso.id, self.cuenta_gasto.id)])

    # -- Plan propio: códigos fuera de 1-7 y otra numeración -------------------------

    def test_03_el_cierre_incluye_cuentas_con_cualquier_numeracion(self):
        ingreso = self._cuenta('8.01.001', 'income', 'INGRESO FUERA DE 1-7')
        gasto = self._cuenta('9.01.001', 'expense', 'GASTO FUERA DE 1-7')
        self._asiento('%s-03-01' % self.anio, self.cuenta_cliente, ingreso, 500.0)
        self._asiento('%s-04-01' % self.anio, gasto, self.cuenta_cliente, 200.0)
        cierre = self.env['l10n_py.cierre_ejercicio'].action_cerrar_ejercicio(self.company, self.anio)
        fin = '%s-12-31' % self.anio
        self.assertEqual(cierre.resultado_ejercicio, 300.0)
        self.assertEqual(self._saldo(ingreso, fin), 0.0)
        self.assertEqual(self._saldo(gasto, fin), 0.0)
        self.assertEqual(self._saldo(self.cuenta_resultado, fin), -300.0)

    def test_04_el_cierre_usa_la_cuenta_resultado_configurada(self):
        propia = self._cuenta('PN.RES', 'equity', 'RESULTADO PROPIO')
        self.company.l10n_py_cuenta_resultado_ejercicio_id = propia
        self._asiento('%s-03-01' % self.anio, self.cuenta_cliente, self.cuenta_ingreso, 800.0)
        self.env['l10n_py.cierre_ejercicio'].action_cerrar_ejercicio(self.company, self.anio)
        fin = '%s-12-31' % self.anio
        self.assertEqual(self._saldo(propia, fin), -800.0)
        self.assertEqual(self._saldo(self.cuenta_resultado, fin), 0.0)

    def test_05_sin_rol_se_usa_la_cuenta_ganancias_del_anio(self):
        self.company.l10n_py_cuenta_resultado_ejercicio_id = False
        self.assertEqual(self.company._l10n_py_cuenta_resultado_ejercicio(), self.cuenta_resultado)

    def test_06_sin_ninguna_cuenta_de_resultado_avisa(self):
        self.company.l10n_py_cuenta_resultado_ejercicio_id = False
        self.cuenta_resultado.account_type = 'equity'
        with self.assertRaises(UserError):
            self.company._l10n_py_cuenta_resultado_ejercicio()

    def test_07_la_cuenta_resultado_se_valida(self):
        with self.assertRaises(ValidationError):
            self.company.l10n_py_cuenta_resultado_ejercicio_id = self.cuenta_ingreso
        otra = self.env['res.company'].create({'name': 'Otra Empresa Test'})
        cuenta_ajena = self.env['account.account'].with_company(otra).create({
            'code': 'AJ.1', 'name': 'Ajena', 'account_type': 'equity',
            'company_ids': [(6, 0, otra.ids)]})
        with self.assertRaises(ValidationError):
            self.company.l10n_py_cuenta_resultado_ejercicio_id = cuenta_ajena

    def test_08_el_paquete_asigna_la_cuenta_resultado(self):
        self.assertEqual(self.company.l10n_py_cuenta_resultado_ejercicio_id, self.cuenta_resultado)

    def test_09_balance_con_plan_propio_sin_grupos(self):
        # Cuentas sin grupo y con códigos libres: aparecen igual, en nivel 1.
        activo = self._cuenta('A.100', 'asset_current', 'ACTIVO PROPIO')
        capital = self._cuenta('C.100', 'equity', 'CAPITAL PROPIO')
        self._asiento('%s-01-02' % self.anio, activo, capital, 250.0)
        filas = self.Report._build_balance_general_rows(self.company, self._fin())
        fila = next(f for f in filas if f['account_id'] == activo.id)
        self.assertEqual(fila['saldo'], 250.0)
        self.assertEqual(fila['nivel'], 1)
        self.assertFalse(fila['raiz_id'])

    def test_10_reconstruir_y_renderizar_el_balance(self):
        self._asiento('%s-05-10' % self.anio, self.cuenta_cliente, self.cuenta_ingreso, 100.0)
        fecha = self._fin()
        self.Report._rebuild(self.company, fecha)
        filas = self.Report.search([('company_id', '=', self.company.id)])
        self.assertEqual(filas.mapped('orden'), sorted(filas.mapped('orden')))
        self.assertEqual(len(filas.filtered(lambda f: f.tipo == 'especial')), 1)
        self.assertTrue(all(filas.filtered(lambda f: f.tipo != 'especial').mapped('raiz_id')))
        # El PDF y la vista HTML usan las mismas filas.
        asistente = self.env['l10n_py.balance_general.wizard'].create({
            'company_id': self.company.id, 'fecha': fecha})
        datos = asistente._render_data()
        self.assertEqual(len(datos['rows']), len(filas))
