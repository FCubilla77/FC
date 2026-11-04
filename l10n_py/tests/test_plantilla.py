# -*- coding: utf-8 -*-
"""La plantilla del paquete fiscal Paraguay se puede resolver completa.

Regresión: el decorador @template('py', ...) de Odoo llama a cada método solo con
`self` (ya conoce el código de plantilla); un método que declare `template_code`
como argumento obligatorio hace fallar la carga del paquete con TypeError."""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestPlantillaL10nPy(TransactionCase):

    def test_01_los_datos_de_la_plantilla_py_se_resuelven(self):
        datos = self.env['account.chart.template']._get_chart_template_data('py')
        self.assertIn('account.journal', datos)
        self.assertIn('bank', datos['account.journal'])
        self.assertIn('res.company', datos)
        self.assertEqual(datos['template_data']['name'], 'Paraguay - Plan de Cuentas')

    def test_02_al_cargar_el_paquete_solo_existen_las_cuentas_del_modulo(self):
        """Odoo crea por su cuenta cuentas "utilitarias" (transitoria, recibos y pagos
        pendientes, cuenta de un diario "Bank" extra) cuando la plantilla no le indica
        las propias. Con el paquete Paraguay completo no debe sobrar ninguna."""
        import csv
        import os
        ruta = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data', 'template', 'account.account-py.csv')
        with open(ruta, encoding='utf-8') as f:
            codigos_modulo = {fila['code'] for fila in csv.DictReader(f)}
        compania = self.env['res.company'].create({
            'name': 'Empresa PY plantilla',
            'country_id': self.env.ref('base.py').id,
            'currency_id': self.env.ref('base.PYG').id,
        })
        self.env['account.chart.template'].with_company(compania).try_loading('py', compania)
        cuentas = self.env['account.account'].with_company(compania).search(
            [('company_ids', 'in', compania.id)])
        self.assertEqual(set(cuentas.mapped('code')), codigos_modulo)

        ref = self.env['account.chart.template'].with_company(compania).ref
        self.assertEqual(compania.account_journal_suspense_account_id, ref('py_1_01_01_03_004'))
        recibos = ref('account_journal_payment_debit_account_id')
        pagos = ref('account_journal_payment_credit_account_id')
        self.assertEqual((recibos.code, pagos.code), ('1.01.01.03.005', '1.01.01.03.006'))
        self.assertTrue(recibos.reconcile and pagos.reconcile)

        bancos = self.env['account.journal'].search(
            [('company_id', '=', compania.id), ('type', '=', 'bank')])
        self.assertEqual(len(bancos), 1)
        self.assertEqual(bancos.name, 'Banco')
        self.assertEqual(bancos.default_account_id, ref('py_1_01_01_03_003'))
        self.assertEqual(bancos.suspense_account_id, ref('py_1_01_01_03_004'))
        # Es lo que Odoo usa al registrar un pago: debe resolver a nuestras cuentas.
        pago = self.env['account.payment'].new({'company_id': compania.id})
        self.assertEqual(pago._get_outstanding_account('inbound'), recibos)
        self.assertEqual(pago._get_outstanding_account('outbound'), pagos)

    def _filas_plan(self):
        import csv
        import os
        ruta = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data', 'template', 'account.account-py.csv')
        with open(ruta, encoding='utf-8') as f:
            return list(csv.DictReader(f))

    def test_03_los_nombres_de_las_cuentas_son_unicos(self):
        from collections import Counter
        repetidos = [n for n, v in Counter(f['name'] for f in self._filas_plan()).items() if v > 1]
        self.assertFalse(repetidos, "Nombres de cuenta repetidos: %s" % repetidos)

    def test_04_tipos_y_monedas_corregidos(self):
        plan = {f['code']: f for f in self._filas_plan()}
        # Banco en dólares: moneda USD (el resto del plan sigue en PYG).
        self.assertEqual(plan['1.01.01.03.002']['currency_id'], 'base.USD')
        # Previsiones de activo corriente no son "Banco y efectivo" ni "Activo fijo".
        for codigo in ('1.01.03.04.001', '1.01.04.04.011'):
            self.assertEqual(plan[codigo]['account_type'], 'asset_current')
        # Préstamos: corriente / no corriente, no "A pagar" (proveedores).
        for sufijo in ('001', '002', '003', '004', '005'):
            self.assertEqual(plan['2.01.02.01.' + sufijo]['account_type'], 'liability_current')
            self.assertEqual(plan['2.02.02.01.' + sufijo]['account_type'], 'liability_non_current')
        # Cuentas a cobrar que no son de clientes no integran la cartera de clientes.
        for codigo in ('1.01.03.01.002', '1.01.03.01.003', '1.01.03.01.004',
                       '1.02.02.01.002', '1.02.02.01.003', '1.02.02.01.004'):
            self.assertEqual(plan[codigo]['account_type'], 'asset_current')
            self.assertEqual(plan[codigo]['reconcile'], 'True')
        # Los deudores por ventas y los proveedores sí.
        for codigo in ('1.01.03.01.001', '1.02.02.01.001'):
            self.assertEqual(plan[codigo]['account_type'], 'asset_receivable')
        for codigo in ('2.01.01.01.001', '2.02.01.01.001'):
            self.assertEqual(plan[codigo]['account_type'], 'liability_payable')
        self.assertEqual(plan['1.01.03.02.004']['tag_ids'], 'l10n_py.tag_iva_credito_fiscal')
