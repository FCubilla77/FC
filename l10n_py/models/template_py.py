# -*- coding: utf-8 -*-
from odoo import models
from odoo.addons.account.models.chart_template import template

from . import plantilla_excel as excel


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    # ------------------------------------------------------------------
    # Cuentas "con función" (roles). Con el plan estándar salen de los ids fijos
    # del módulo; con el plan del cliente, de la hoja «Configuración» del Excel.
    # Un rol vacío en el Excel no se informa: Odoo crea entonces su propia cuenta.
    # ------------------------------------------------------------------
    def _py_cuenta_rol(self, clave):
        datos = self._l10n_py_datos_plantilla()
        if datos is None:
            return excel.ROLES_POR_CLAVE[clave][4]
        return excel.id_rol(datos, clave)

    def _py_impuesto_defecto(self, uso):
        datos = self._l10n_py_datos_plantilla()
        if datos is None:
            return {'Venta': 'tax_iva_10_ventas', 'Compra': 'tax_iva_10_compras'}[uso]
        return excel.id_impuesto_defecto(datos, uso)

    def _py_parametro(self, clave, estandar):
        datos = self._l10n_py_datos_plantilla()
        return estandar if datos is None else datos['parametros'].get(clave) or None

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
        datos = self._l10n_py_datos_plantilla()
        # Con el plan del cliente el relleno de ceros de Odoo se anula: 'code_digits' es el
        # largo del código más largo, así ningún código se altera.
        valores = {
            'name': 'Paraguay - Plan de Cuentas',
            'code_digits': '13' if datos is None else str(excel.code_digits(datos)),
            'property_account_receivable_id': self._py_cuenta_rol('cuenta_cobrar'),
            'property_account_payable_id': self._py_cuenta_rol('cuenta_pagar'),
        }
        return {k: v for k, v in valores.items() if v}

    @template('py', 'res.company')
    def _get_py_res_company(self):
        datos_cia = {
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
                'income_account_id': self._py_cuenta_rol('cuenta_ingreso'),
                'expense_account_id': self._py_cuenta_rol('cuenta_gasto'),

                # Prefijos de banco/caja: DISPONIBILIDADES (1.01.01) se separó
                # en 3 sub-grupos en el plan V3 (CAJAS/FONDOS FIJOS/BANCOS).
                # Prefijo de banco apunta específicamente al grupo BANCOS,
                # prefijo de caja al grupo CAJAS. Fondos Fijos queda fuera de
                # la auto-generación (asignación manual si se crea un diario
                # de ese tipo) — confirmado por el cliente.
                'bank_account_code_prefix': self._py_parametro('prefijo_banco', '1.01.01.03.'),
                'cash_account_code_prefix': self._py_parametro('prefijo_caja', '1.01.01.01.'),

                'transfer_account_id': self._py_cuenta_rol('cuenta_transferencia'),

                # Diferencia de cambio: a partir de esta versión, Ganancia y
                # Pérdida usan CUENTAS DISTINTAS (decisión explícita del
                # cliente, cambio de criterio respecto a versiones previas
                # donde ambas compartían una sola cuenta).
                'income_currency_exchange_account_id': self._py_cuenta_rol('dif_cambio_ganancia'),
                'expense_currency_exchange_account_id': self._py_cuenta_rol('dif_cambio_perdida'),

                # Redondeo: ambos signos comparten la misma cuenta
                # (confirmado, sin cambios).
                'default_cash_difference_income_account_id': self._py_cuenta_rol('dif_efectivo_ganancia'),
                'default_cash_difference_expense_account_id': self._py_cuenta_rol('dif_efectivo_perdida'),

                'account_sale_tax_id': self._py_impuesto_defecto('Venta'),
                'account_purchase_tax_id': self._py_impuesto_defecto('Compra'),

                # Descuento por pronto pago. "Loss" = descuento que LA
                # EMPRESA concede a un cliente que paga antes de tiempo
                # (reduce nuestra venta). "Gain" = descuento que UN
                # PROVEEDOR nos concede a nosotros por pagar antes de
                # tiempo (reduce nuestro costo/gasto).
                'account_journal_early_pay_discount_loss_account_id': self._py_cuenta_rol('descuento_pronto_pago_perdida'),
                'account_journal_early_pay_discount_gain_account_id': self._py_cuenta_rol('descuento_pronto_pago_ganancia'),

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
                'account_stock_valuation_id': self._py_cuenta_rol('valoracion_inventario'),

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

                # Cuenta transitoria de bancos (suspense) a nivel COMPAÑÍA: Odoo
                # la espera aquí (como l10n_es, l10n_fr, etc.). Si no se define, crea
                # por su cuenta "Bank Suspense Account" con el prefijo de bancos.
                'account_journal_suspense_account_id': self._py_cuenta_rol('cuenta_transitoria_banco'),

                # Cuenta que recibe el resultado en el Cierre de Ejercicio.
                'l10n_py_cuenta_resultado_ejercicio_id': self._py_cuenta_rol('cuenta_resultado_ejercicio'),

                # Recibos/Pagos Pendientes ("Outstanding Receipts/Payments"): NO
                # son campos de la compañía en Odoo 19 y no se pueden indicar aquí.
                # Odoo los busca por xmlid 'account.<id_compañía>_account_journal_
                # payment_debit_account_id' / '..._credit_account_id' y, si no
                # existen, crea los suyos en inglés. Por eso nuestras cuentas
                # RECIBOS PENDIENTES (1.01.01.03.005) y PAGOS PENDIENTES
                # (1.01.01.03.006) se declaran en account.account-py.csv con
                # EXACTAMENTE esos ids: Odoo las encuentra y no crea duplicados.
        }
        # Un rol sin cuenta (plan del cliente) no se informa.
        return {self.env.company.id: {k: v for k, v in datos_cia.items() if v is not None}}

    @template('py', 'account.journal')
    def _get_py_account_journal(self):
        """Diario de banco de EJEMPLO — un único diario ('Banco'), con sus
        cuentas ya asignadas, para que sirva de plantilla/patrón al crear
        los diarios de banco reales de cada empresa (confirmado con el
        cliente: las cuentas BANCOS 1 PYG / BANCOS 2 USD del plan son solo
        ejemplos ilustrativos, no journals reales — cada empresa crea sus
        propias cuentas de banco).
        """
        return {
            # Clave 'bank' (no 'bank_py'): personaliza el diario de banco que Odoo
            # ya crea por defecto, en lugar de agregar un segundo diario "Bank"
            # (con su propia cuenta 1.01.01.03.007 sobrante).
            'bank': {k: v for k, v in {
                'name': 'Banco',
                'type': 'bank',
                'default_account_id': self._py_cuenta_rol('cuenta_banco_defecto'),
                # Cuenta transitoria de conciliación (suspense_account_id
                # SÍ es un campo directo del diario en Odoo 19, a diferencia
                # de Recibos/Pagos Pendientes — ver nota en _get_py_res_company).
                'suspense_account_id': self._py_cuenta_rol('cuenta_transitoria_banco'),
            }.items() if v is not None},
        }
