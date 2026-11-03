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
        self.assertIn('bank_py', datos['account.journal'])
        self.assertIn('res.company', datos)
        self.assertEqual(datos['template_data']['name'], 'Paraguay - Plan de Cuentas')
