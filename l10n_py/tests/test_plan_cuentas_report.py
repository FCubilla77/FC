# -*- coding: utf-8 -*-
"""Reporte Plan de Cuentas (Títulos + Imputables) con el paquete Paraguay cargado."""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestPlanCuentasReportL10nPy(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({
            'name': 'Empresa Plan Test',
            'country_id': cls.env.ref('base.py').id,
            'currency_id': cls.env.ref('base.PYG').id,
        })
        cls.env['account.chart.template'].with_company(cls.company).try_loading(
            'py', cls.company)
        cls.Reporte = cls.env['l10n_py.plan_cuentas.report']

    def test_01_el_reporte_combina_titulos_e_imputables(self):
        self.Reporte._rebuild()
        filas = self.Reporte.search([('company_id', '=', self.company.id)])
        titulos = filas.filtered(lambda f: f.tipo == 'title')
        imputables = filas.filtered(lambda f: f.tipo == 'imputable')
        self.assertEqual(len(titulos), 201)
        self.assertEqual(len(imputables), 228)
        # Las 7 raíces de nivel 1 están presentes y las cuentas se clasifican.
        self.assertEqual(set(filas.mapped('nivel_1')) - {False}, set('1234567'))
        # Cada imputable apunta a su cuenta real y trae el tipo de cuenta.
        fila = imputables.filtered(lambda f: f.code == '1.01.03.01.001')
        self.assertEqual(fila.name, 'DEUDORES POR VENTAS')
        self.assertEqual(fila.account_type, 'asset_receivable')
        self.assertTrue(fila.account_id)
        self.assertEqual(fila.action_open_account()['res_id'], fila.account_id.id)
        # Un título no abre ninguna cuenta.
        self.assertEqual(titulos[:1].action_open_account()['type'], 'ir.actions.act_window_close')

    def test_02_reconstruir_no_duplica_filas(self):
        self.Reporte._rebuild()
        cantidad = self.Reporte.search_count([])
        self.Reporte._rebuild()
        self.assertEqual(self.Reporte.search_count([]), cantidad)

    def test_03_el_menu_reconstruye_y_abre_el_listado(self):
        self.Reporte.sudo().search([]).unlink()
        accion = self.Reporte.action_open_report()
        self.assertEqual(accion['res_model'], 'l10n_py.plan_cuentas.report')
        self.assertTrue(self.Reporte.search_count([]))

    def test_04_un_usuario_de_contabilidad_lo_puede_abrir_sin_ser_admin(self):
        usuario = self.env['res.users'].create({
            'name': 'Contador Plan',
            'login': 'contador_plan_py',
            'company_id': self.company.id,
            'company_ids': [(6, 0, self.company.ids)],
            'group_ids': [(6, 0, [self.env.ref('account.group_account_readonly').id])],
        })
        accion_servidor = self.env.ref('l10n_py.action_l10n_py_plan_cuentas_report')
        resultado = accion_servidor.with_user(usuario).with_context(
            active_model='l10n_py.plan_cuentas.report').run()
        self.assertEqual(resultado['res_model'], 'l10n_py.plan_cuentas.report')
        filas = self.Reporte.with_user(usuario).search([])
        self.assertTrue(filas)
        # Solo ve las filas de sus compañías.
        self.assertEqual(filas.mapped("company_id"), self.company)
