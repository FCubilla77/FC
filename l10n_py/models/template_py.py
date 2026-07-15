# -*- coding: utf-8 -*-
from odoo import models
from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    @template('py')
    def _get_py_template_data(self):
        """Datos base de la plantilla de plan de cuentas de Paraguay.

        NOTA sobre 'code_digits': el plan de cuentas de Paraguay usa códigos
        con formato de segmentos punteados de largo variable (ej.
        '1.01.03.05.01', 13 caracteres con puntos), no el formato numérico
        plano que este campo espera nativamente en Odoo (que asume el
        auto-padding de nuevos códigos como enteros de largo fijo, sin
        puntos). Se mantiene igual como fue confirmado por el cliente; la
        única consecuencia conocida es que la sugerencia automática de
        "próximo código" al crear una cuenta nueva manualmente puede no
        salir perfectamente formateada y requerir un ajuste manual.
        """
        return {
            'name': 'Paraguay - Plan de Cuentas',
            'code_digits': '13',
            'property_account_receivable_id': 'py_1_01_03_01',
            'property_account_payable_id': 'py_2_01_01_01',
            # Cuenta de ingreso/gasto por defecto para categorías de producto
            # sin cuenta propia asignada (confirmado por el cliente).
            'property_account_income_categ_id': 'py_4_01_01_01',
            'property_account_expense_categ_id': 'py_5_01_01_01',
        }

    @template('py', 'res.company')
    def _get_py_res_company(self):
        return {
            self.env.company.id: {
                'account_fiscal_country_id': 'base.py',
                'currency_id': 'base.PYG',
                'bank_account_code_prefix': '1.01.01.',
                'cash_account_code_prefix': '1.01.01.',
                'transfer_account_id': 'py_1_01_01_05',
                'income_currency_exchange_account_id': 'py_6_01_01_05',
                'expense_currency_exchange_account_id': 'py_6_01_01_05',
                'default_cash_difference_income_account_id': 'py_7_02_18_02',
                'default_cash_difference_expense_account_id': 'py_7_02_18_02',
                'account_sale_tax_id': 'tax_iva_10_ventas',
                'account_purchase_tax_id': 'tax_iva_10_compras',
            },
        }
