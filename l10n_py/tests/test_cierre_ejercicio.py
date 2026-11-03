# -*- coding: utf-8 -*-
"""Cierre y Apertura de Ejercicio, con el paquete fiscal Paraguay realmente cargado."""
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestCierreEjercicioL10nPy(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({
            'name': 'Empresa Paraguay Test',
            'country_id': cls.env.ref('base.py').id,
            'currency_id': cls.env.ref('base.PYG').id,
        })
        # Dentro de las pruebas el control de licencia está exento (a menos que se
        # fuerce), así que el paquete se asigna igual que lo hace Odoo al cargarlo.
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

    def _asiento(self, fecha, debe, haber, monto):
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.diario.id,
            'company_id': self.company.id,
            'date': fecha,
            'line_ids': [
                (0, 0, {'account_id': debe.id, 'debit': monto, 'credit': 0.0}),
                (0, 0, {'account_id': haber.id, 'debit': 0.0, 'credit': monto}),
            ],
        })
        move.action_post()
        return move

    def _saldo(self, cuenta, hasta):
        lineas = self.env['account.move.line'].search([
            ('account_id', '=', cuenta.id), ('parent_state', '=', 'posted'),
            ('date', '<=', hasta)])
        return sum(lineas.mapped('balance'))

    def test_01_el_paquete_se_cargo_con_las_cuentas_del_cierre(self):
        self.assertEqual(self.company.chart_template, 'py')
        self.assertTrue(self.cuenta_resultado)
        self.assertTrue(self.diario)

    def test_02_cierre_con_ganancia_cuadra_y_se_puede_deshacer(self):
        self._asiento('%s-06-15' % self.anio, self.cuenta_cliente, self.cuenta_ingreso, 1000000.0)
        self._asiento('%s-07-10' % self.anio, self.cuenta_gasto, self.cuenta_cliente, 300000.0)
        fin = '%s-12-31' % self.anio

        cierre = self.env['l10n_py.cierre_ejercicio'].action_cerrar_ejercicio(self.company, self.anio)

        self.assertEqual(cierre.state, 'cerrado')
        self.assertEqual(cierre.resultado_ejercicio, 700000.0)
        for move in (cierre.move_cierre_id, cierre.move_apertura_id):
            self.assertEqual(move.state, 'posted')
            self.assertEqual(sum(move.line_ids.mapped('debit')), sum(move.line_ids.mapped('credit')))
        # Ingresos y gastos quedan en cero; la ganancia queda acreedora en
        # "RESULTADO DEL EJERCICIO".
        self.assertEqual(self._saldo(self.cuenta_ingreso, fin), 0.0)
        self.assertEqual(self._saldo(self.cuenta_gasto, fin), 0.0)
        self.assertEqual(self._saldo(self.cuenta_resultado, fin), -700000.0)
        self.assertEqual(str(self.company.fiscalyear_lock_date), fin)

        with self.assertRaises(UserError):
            self.env['l10n_py.cierre_ejercicio'].action_cerrar_ejercicio(self.company, self.anio)

        cierre.action_deshacer()
        self.assertEqual(cierre.state, 'deshecho')
        self.assertFalse(self.company.fiscalyear_lock_date)

    def test_03_cierre_con_perdida(self):
        self._asiento('%s-03-01' % self.anio, self.cuenta_cliente, self.cuenta_ingreso, 200000.0)
        self._asiento('%s-04-01' % self.anio, self.cuenta_gasto, self.cuenta_cliente, 500000.0)
        cierre = self.env['l10n_py.cierre_ejercicio'].action_cerrar_ejercicio(self.company, self.anio)
        self.assertEqual(cierre.resultado_ejercicio, -300000.0)
        self.assertEqual(self._saldo(self.cuenta_resultado, '%s-12-31' % self.anio), 300000.0)

    def test_04_sin_movimientos_no_corresponde_cerrar(self):
        with self.assertRaises(UserError):
            self.env['l10n_py.cierre_ejercicio'].action_cerrar_ejercicio(self.company, self.anio)
