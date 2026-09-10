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
        '1.02.04.01.001'), no el formato numérico plano que este campo
        espera nativamente en Odoo. Se mantiene igual, confirmado por el
        cliente; la única consecuencia conocida es que la sugerencia
        automática de "próximo código" al crear una cuenta nueva manualmente
        puede no salir perfectamente formateada.
        """
        return {
            'name': 'Paraguay - Plan de Cuentas',
            'code_digits': '13',
            'property_account_receivable_id': 'py_1_01_03_01_001',
            'property_account_payable_id': 'py_2_01_01_01_001',
        }

    @template('py', 'res.company')
    def _get_py_res_company(self):
        return {
            self.env.company.id: {
                'account_fiscal_country_id': 'base.py',
                'currency_id': 'base.PYG',

                # Cuenta por Cobrar/Pagar: ver property_account_receivable_id/
                # payable_id arriba en _get_py_template_data(). Corto plazo,
                # confirmado (existe también versión largo plazo en el plan,
                # bajo Activo/Pasivo No Corriente, no usada como default).

                # Ingreso/Gasto por defecto para categorías de producto sin
                # cuenta propia. Campos correctos en res.company (Odoo 19):
                # 'income_account_id' / 'expense_account_id' — NO
                # 'property_account_income_categ_id' / '..._expense_categ_id'
                # (esos son campos de product.category, no de la compañía;
                # Odoo los propaga solo internamente vía ir.default a partir
                # de estos dos). Confirmado contra el código fuente real de
                # account/models/company.py y chart_template.py (19.0).
                'income_account_id': 'py_4_01_01_01_001',
                'expense_account_id': 'py_5_01_01_01_001',

                # Prefijos de banco/caja: DISPONIBILIDADES (1.01.01) se separó
                # en 3 sub-grupos en el plan V3 (CAJAS/FONDOS FIJOS/BANCOS).
                # Prefijo de banco apunta específicamente al grupo BANCOS,
                # prefijo de caja al grupo CAJAS. Fondos Fijos queda fuera de
                # la auto-generación (asignación manual si se crea un diario
                # de ese tipo) — confirmado por el cliente.
                'bank_account_code_prefix': '1.01.01.03.',
                'cash_account_code_prefix': '1.01.01.01.',

                'transfer_account_id': 'py_1_01_01_01_002',

                # Diferencia de cambio: a partir de esta versión, Ganancia y
                # Pérdida usan CUENTAS DISTINTAS (decisión explícita del
                # cliente, cambio de criterio respecto a versiones previas
                # donde ambas compartían una sola cuenta).
                'income_currency_exchange_account_id': 'py_6_01_01_01_005',
                'expense_currency_exchange_account_id': 'py_7_03_01_02_001',

                # Redondeo: ambos signos comparten la misma cuenta
                # (confirmado, sin cambios).
                'default_cash_difference_income_account_id': 'py_7_02_18_01_002',
                'default_cash_difference_expense_account_id': 'py_7_02_18_01_002',

                'account_sale_tax_id': 'tax_iva_10_ventas',
                'account_purchase_tax_id': 'tax_iva_10_compras',

                # Descuento por pronto pago. "Loss" = descuento que LA
                # EMPRESA concede a un cliente que paga antes de tiempo
                # (reduce nuestra venta). "Gain" = descuento que UN
                # PROVEEDOR nos concede a nosotros por pagar antes de
                # tiempo (reduce nuestro costo/gasto).
                'account_journal_early_pay_discount_loss_account_id': 'py_4_01_98_01_001',
                'account_journal_early_pay_discount_gain_account_id': 'py_6_01_01_01_003',

                # Contabilidad Anglo-Saxon: el costo se reconoce como activo
                # (Valoración de Inventario) al COMPRAR, y recién pasa a
                # Costo de Venta (gasto) al VENDER, descargando la
                # valoración. Confirmado explícitamente por el cliente — es
                # lo opuesto a "Continental" (donde el gasto se reconoce
                # directo al comprar), que había sido la respuesta inicial
                # pero no coincidía con el comportamiento que en realidad
                # pedía.
                'anglo_saxon_accounting': True,

                # Valorización de inventario: Automática (perpetua) +
                # Promedio Ponderado (AVCO). Ambos son, en Odoo 19, defaults
                # A NIVEL COMPAÑÍA que se propagan como valor inicial de la
                # categoría de producto "Bienes" (product.category ya no
                # tiene una única categoría raíz "Todos" en Odoo 19 — se
                # reemplazó por 3 categorías raíz: Bienes/Gastos/Servicios).
                # El usuario puede modificar esto por categoría cuando cree
                # las suyas propias — esto es solo el estándar de fábrica.
                'inventory_valuation': 'real_time',
                'cost_method': 'average',
                'account_stock_valuation_id': 'py_1_01_04_01_001',

                # Diario de valorización de inventario (account_stock_journal_id):
                # sin configurar a propósito — Odoo crea uno propio
                # automáticamente si no se define (confirmado por el
                # cliente).

                # Frecuencia del cierre periódico de ajuste de inventario
                # físico vs. contable (independiente del flujo normal de
                # compra/venta, que ya queda cubierto por Anglo-Saxon).
                'inventory_period': 'daily',

                # account_stock_variation_id / account_stock_expense_id NO
                # se configuran a propósito: el primero es un campo de
                # account.account (se define sobre la cuenta de Valoración
                # de cada categoría, no a nivel compañía) y el segundo es
                # específico del cierre de Continental (no aplica con
                # Anglo-Saxon). Ambos quedan a criterio del usuario cuando
                # cree sus propias categorías de producto.
            },
        }
