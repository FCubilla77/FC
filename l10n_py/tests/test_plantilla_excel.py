# -*- coding: utf-8 -*-
"""Plantilla Excel del plan de cuentas del cliente: generación, lectura, validación y carga."""
import copy
import io

from odoo import fields
from odoo.exceptions import UserError
from odoo.modules.module import get_module_path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.l10n_py.models import plantilla_excel as excel


def _plan_propio():
    """Un plan chico, con otra numeración (sin puntos, de 5 dígitos) y todos los roles
    obligatorios."""
    def cuenta(codigo, nombre, tipo, conciliable=False, moneda='PYG', etiqueta=''):
        return {'codigo': codigo, 'nombre': nombre, 'tipo': tipo, 'conciliable': conciliable,
                'moneda': moneda, 'etiqueta': etiqueta}
    return {
        'grupos': [
            {'desde': '1', 'hasta': '1', 'nombre': 'ACTIVO PROPIO'},
            {'desde': '11', 'hasta': '11', 'nombre': 'ACTIVO CORRIENTE PROPIO'},
            {'desde': '2', 'hasta': '2', 'nombre': 'PASIVO PROPIO'},
            {'desde': '3', 'hasta': '3', 'nombre': 'PATRIMONIO PROPIO'},
            {'desde': '4', 'hasta': '4', 'nombre': 'INGRESOS PROPIOS'},
            {'desde': '5', 'hasta': '5', 'nombre': 'GASTOS PROPIOS'},
        ],
        'cuentas': [
            cuenta('11001', 'CAJA PROPIA', 'asset_cash'),
            cuenta('11002', 'CLIENTES PROPIOS', 'asset_receivable', True),
            cuenta('11003', 'IVA CREDITO PROPIO', 'asset_current', False, 'PYG', 'Crédito fiscal'),
            cuenta('11004', 'BANCO PROPIO', 'asset_cash'),
            cuenta('11005', 'TRANSITORIA PROPIA', 'asset_current'),
            cuenta('11006', 'RECIBOS PENDIENTES PROPIOS', 'asset_current', True),
            cuenta('11007', 'PAGOS PENDIENTES PROPIOS', 'asset_current', True),
            cuenta('21001', 'PROVEEDORES PROPIOS', 'liability_payable', True),
            cuenta('21002', 'IVA DEBITO PROPIO', 'liability_current', False, 'PYG', 'Débito fiscal'),
            cuenta('31001', 'CAPITAL PROPIO', 'equity'),
            cuenta('31002', 'RESULTADO PROPIO', 'equity_unaffected'),
            cuenta('41001', 'VENTAS PROPIAS', 'income'),
            cuenta('51001', 'GASTOS GENERALES PROPIOS', 'expense'),
        ],
        'roles': {
            'cuenta_cobrar': '11002', 'cuenta_pagar': '21001', 'cuenta_ingreso': '41001',
            'cuenta_gasto': '51001', 'cuenta_resultado_ejercicio': '31002',
            'cuenta_banco_defecto': '11004', 'cuenta_transitoria_banco': '11005',
            'cuenta_recibos_pendientes': '11006', 'cuenta_pagos_pendientes': '11007',
        },
        'parametros': {'prefijo_banco': '1100', 'prefijo_caja': '1100'},
        'grupos_impuestos': [{'nombre': 'IVA 10% PROPIO'}],
        'impuestos': [
            {'nombre': 'IVA 10% Ventas Propio', 'uso': 'Venta', 'importe': 10.0,
             'tipo_importe': 'Porcentaje', 'precio_incluido': True, 'incluir_base': False,
             'descripcion': 'IVA 10%', 'grupo': 'IVA 10% PROPIO', 'cuenta': '21002',
             'posiciones': [], 'reemplaza': [], 'defecto': True},
            {'nombre': 'IVA 10% Compras Propio', 'uso': 'Compra', 'importe': 10.0,
             'tipo_importe': 'Porcentaje', 'precio_incluido': True, 'incluir_base': False,
             'descripcion': 'IVA 10%', 'grupo': 'IVA 10% PROPIO', 'cuenta': '11003',
             'posiciones': [], 'reemplaza': [], 'defecto': True},
        ],
        'posiciones_fiscales': [{'nombre': 'Exterior Propia', 'automatica': False,
                                 'ruc_requerido': False}],
        'plazos_pago': [
            {'nombre': 'Contado Propio', 'lineas': [{'porcentaje': 100.0, 'dias': 0}]},
            {'nombre': 'Treinta y sesenta Propio',
             'lineas': [{'porcentaje': 50.0, 'dias': 30}, {'porcentaje': 50.0, 'dias': 60}]},
        ],
    }


@tagged('post_install', '-at_install')
class TestPlantillaExcelL10nPy(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.estandar = excel.datos_estandar(get_module_path('l10n_py'))
        cls.Plantilla = cls.env['l10n_py.plantilla']

    def _empresa(self, nombre='Empresa Plantilla Test'):
        return self.env['res.company'].create({
            'name': nombre, 'country_id': self.env.ref('base.py').id,
            'currency_id': self.env.ref('base.PYG').id})

    def _libro_modificado(self, datos, modificar):
        """Genera el Excel de `datos`, lo abre, aplica `modificar(libro)` y lo devuelve en bytes."""
        from openpyxl import load_workbook
        libro = load_workbook(io.BytesIO(excel.generar_libro(datos)))
        modificar(libro)
        salida = io.BytesIO()
        libro.save(salida)
        return salida.getvalue()

    # -- Generación y lectura ---------------------------------------------------------------

    def test_01_el_excel_del_plan_estandar_se_lee_sin_errores_y_sin_perder_datos(self):
        contenido = excel.generar_libro(self.estandar)
        datos, errores, _avisos = excel.leer_libro(contenido, {'PYG', 'USD'})
        self.assertEqual(errores, [])
        for clave in ('grupos', 'cuentas', 'roles', 'parametros', 'grupos_impuestos',
                      'impuestos', 'posiciones_fiscales', 'plazos_pago'):
            self.assertEqual(datos[clave], self.estandar[clave], clave)
        self.assertEqual(len(datos['cuentas']), 228)
        self.assertEqual(len(datos['grupos']), 201)

    def test_02_el_excel_trae_todas_las_hojas(self):
        from openpyxl import load_workbook
        libro = load_workbook(io.BytesIO(excel.generar_libro(self.estandar)))
        self.assertEqual(libro.sheetnames, [
            'Instrucciones', 'Grupos', 'Cuentas', 'Configuración', 'Grupos de impuestos',
            'Impuestos', 'Posiciones fiscales', 'Plazos de pago', 'Tipos de cuenta'])

    def test_02b_las_listas_desplegables_son_compatibles_con_excel(self):
        """Excel "repara" quitándolas las validaciones en línea de más de 255 caracteres."""
        from openpyxl import load_workbook
        libro = load_workbook(io.BytesIO(excel.generar_libro(self.estandar)))
        total = 0
        for hoja in libro.worksheets:
            for validacion in hoja.data_validations.dataValidation:
                total += 1
                formula = validacion.formula1
                if formula.startswith('"'):
                    self.assertLessEqual(len(formula) - 2, 255, (hoja.title, formula[:40]))
        self.assertGreater(total, 5)
        formulas = [v.formula1 for v in libro['Cuentas'].data_validations.dataValidation]
        self.assertIn("'Tipos de cuenta'!$A$2:$A$20", formulas)
        self.assertEqual(libro['Tipos de cuenta'].max_row, 20)

    def test_03_un_plan_propio_hace_el_recorrido_completo(self):
        datos, errores, _ = excel.leer_libro(excel.generar_libro(_plan_propio()), {'PYG'})
        self.assertEqual(errores, [])
        self.assertEqual(datos['roles']['cuenta_cobrar'], '11002')

    # -- Validaciones -----------------------------------------------------------------------

    def _errores(self, modificar, datos=None):
        contenido = self._libro_modificado(datos or copy.deepcopy(_plan_propio()), modificar)
        _datos, errores, avisos = excel.leer_libro(contenido, {'PYG', 'USD'})
        return errores, avisos

    def test_04_codigo_repetido_y_caracteres_invalidos(self):
        def modificar(libro):
            hoja = libro['Cuentas']
            hoja['A3'] = '11001'
            hoja['A4'] = 'AB-1'
        errores, _ = self._errores(modificar)
        self.assertTrue(any('repetido' in e for e in errores), errores)
        self.assertTrue(any('letras, números y puntos' in e for e in errores), errores)

    def test_05_tipo_de_cuenta_y_moneda_invalidos(self):
        def modificar(libro):
            libro['Cuentas']['C2'] = 'inventado'
            libro['Cuentas']['E3'] = 'XXX'
        errores, _ = self._errores(modificar)
        self.assertTrue(any('tipo de cuenta' in e for e in errores), errores)
        self.assertTrue(any('moneda' in e for e in errores), errores)

    def test_06_roles_obligatorios_y_tipos(self):
        def modificar(libro):
            hoja = libro['Configuración']
            for fila in hoja.iter_rows(min_row=2):
                if fila[0].value == 'cuenta_resultado_ejercicio':
                    fila[2].value = ''
                if fila[0].value == 'cuenta_cobrar':
                    fila[2].value = '41001'  # una cuenta de ingreso no puede ser "por cobrar"
                if fila[0].value == 'cuenta_pagar':
                    fila[2].value = '99999'  # no existe
        errores, _ = self._errores(modificar)
        self.assertTrue(any('cuenta_resultado_ejercicio' in e and 'obligatorio' in e for e in errores), errores)
        self.assertTrue(any('cuenta_cobrar' in e and 'tipo' in e for e in errores), errores)
        self.assertTrue(any('cuenta_pagar' in e and 'no existe' in e for e in errores), errores)

    def test_07_roles_opcionales_vacios_solo_avisan(self):
        errores, avisos = self._errores(lambda libro: None)
        self.assertEqual(errores, [])
        self.assertTrue(any('cuenta_transferencia' in a for a in avisos), avisos)

    def test_08_grupos_con_rangos_superpuestos(self):
        def modificar(libro):
            libro['Grupos'].append(['1', '1', 'OTRO ACTIVO'])
            libro['Grupos'].append(['2', '1', 'AL REVES'])
        errores, _ = self._errores(modificar)
        self.assertTrue(any('repetido' in e for e in errores), errores)
        self.assertTrue(any('mayor' in e for e in errores), errores)

    def test_08b_avisos_de_grupos(self):
        # El plan estándar y el plan propio de prueba no generan avisos de grupos.
        for datos in (self.estandar, _plan_propio()):
            _d, errores, avisos = excel.leer_libro(excel.generar_libro(datos), {'PYG', 'USD'})
            self.assertEqual(errores, [])
            self.assertFalse([a for a in avisos if any(t in a for t in (
                'no pertenecen a ningún grupo', 'falta un grupo raíz', 'no hay ningún grupo'))], avisos)

        def sin_raiz(libro):
            hoja = libro['Grupos']
            for fila in range(hoja.max_row, 1, -1):
                if hoja.cell(row=fila, column=1).value == '2':
                    hoja.delete_rows(fila)
        # Se quita la raíz «2» pero queda un grupo «21»: hace falta avisar.
        def sin_raiz_con_hijo(libro):
            sin_raiz(libro)
            libro['Grupos'].append(['21', '21', 'PASIVO CORRIENTE PROPIO'])
        errores, avisos = self._errores(sin_raiz_con_hijo)
        self.assertEqual(errores, [])
        self.assertTrue(any('falta un grupo raíz' in a and '21' in a for a in avisos), avisos)
        # Cuentas cuyo código no cae en ningún grupo.
        errores, avisos = self._errores(sin_raiz)
        self.assertTrue(any('no pertenecen a ningún grupo' in a and '21001' in a for a in avisos), avisos)

        def sin_grupos(libro):
            libro['Grupos'].delete_rows(2, libro['Grupos'].max_row)
        errores, avisos = self._errores(sin_grupos)
        self.assertEqual(errores, [])
        self.assertTrue(any('no hay ningún grupo' in a for a in avisos), avisos)

    def test_09_impuestos_plazos_y_posiciones(self):
        def modificar(libro):
            libro['Impuestos']['H2'] = 'Grupo inexistente'
            libro['Impuestos']['J3'] = 'Posicion inexistente'
            libro['Impuestos']['L3'] = 'SI'
            libro['Impuestos'].append(['Otro Venta', 'Venta', 10, 'Porcentaje', 'SI', 'NO', 'x',
                                       'IVA 10% PROPIO', '21002', '', '', 'SI'])
            libro['Plazos de pago']['B3'] = 40
        errores, _ = self._errores(modificar)
        self.assertTrue(any('grupo de impuestos' in e for e in errores), errores)
        self.assertTrue(any('posición fiscal' in e for e in errores), errores)
        self.assertTrue(any('Por defecto' in e for e in errores), errores)
        self.assertTrue(any('sumar 100' in e for e in errores), errores)

    def test_10_encabezados_hojas_y_archivo_invalidos(self):
        def modificar(libro):
            libro['Cuentas']['A1'] = 'Cod'
            del libro['Impuestos']
        errores, _ = self._errores(modificar)
        self.assertTrue(any('encabezados' in e for e in errores), errores)
        self.assertTrue(any('no se encontró la hoja' in e for e in errores), errores)
        _d, errores, _a = excel.leer_libro(b'esto no es un excel')
        self.assertTrue(errores)

    # -- Modelo de plantilla ----------------------------------------------------------------

    def test_11_se_guarda_validada_y_la_nueva_reemplaza_a_la_anterior(self):
        empresa = self._empresa()
        primera = self.Plantilla._validar_y_guardar(
            empresa, 'uno.xlsx', excel.generar_libro(_plan_propio()))
        self.assertEqual(primera.state, 'validada')
        self.assertEqual(empresa.l10n_py_plantilla_id, primera)
        self.assertIn('Resumen', primera.log)
        segunda = self.Plantilla._validar_y_guardar(
            empresa, 'dos.xlsx', excel.generar_libro(_plan_propio()))
        self.assertEqual(empresa.l10n_py_plantilla_id, segunda)
        self.assertFalse(primera.active)

    def test_12_con_errores_no_reemplaza_la_validada(self):
        empresa = self._empresa()
        buena = self.Plantilla._validar_y_guardar(
            empresa, 'ok.xlsx', excel.generar_libro(_plan_propio()))
        mala = self.Plantilla._validar_y_guardar(empresa, 'mala.xlsx', b'basura')
        self.assertEqual(mala.state, 'error')
        self.assertFalse(mala.datos)
        self.assertEqual(empresa.l10n_py_plantilla_id, buena)
        self.assertTrue(buena.active)

    def test_13_el_asistente_valida_el_archivo(self):
        import base64
        empresa = self._empresa()
        asistente = self.env['l10n_py.plantilla.wizard'].create({
            'company_id': empresa.id, 'nombre_archivo': 'plan.xlsx',
            'archivo': base64.b64encode(excel.generar_libro(_plan_propio()))})
        accion = asistente.action_validar()
        # Sin errores: se cierra la ventana y se confirma con un aviso.
        self.assertEqual(accion['tag'], 'display_notification')
        self.assertEqual(accion['params']['type'], 'success')
        self.assertEqual(accion['params']['next'], {'type': 'ir.actions.act_window_close'})
        self.assertEqual(empresa.l10n_py_plantilla_id.state, 'validada')
        # Con errores: la ventana queda abierta con el detalle.
        malo = self.env['l10n_py.plantilla.wizard'].create({
            'company_id': empresa.id, 'nombre_archivo': 'mal.xlsx',
            'archivo': base64.b64encode(b'no es excel')})
        accion = malo.action_validar()
        self.assertEqual(accion['res_id'], malo.id)
        self.assertEqual(malo.estado, 'error')
        self.assertIn('NO se guardó como válida', malo.resultado)
        self.assertEqual(empresa.l10n_py_plantilla_id.state, 'validada')
        with self.assertRaises(UserError):
            self.env['l10n_py.plantilla.wizard'].create({'company_id': empresa.id}).action_validar()

    def test_13b_la_plantilla_descargada_viene_ordenada_por_codigo(self):
        datos, errores, _ = excel.leer_libro(excel.generar_libro(self.estandar), {'PYG', 'USD'})
        self.assertEqual(errores, [])
        codigos = [c['codigo'] for c in datos['cuentas']]
        self.assertEqual(codigos, sorted(codigos))
        rangos = [(g['desde'], g['hasta']) for g in datos['grupos']]
        self.assertEqual(rangos, sorted(rangos))
        self.assertLess(codigos.index('1.01.01.03.003'), codigos.index('1.01.03.01.001'))

    def test_14_la_descarga_genera_un_excel_valido(self):
        ajustes = self.env['res.config.settings'].create({})
        accion = ajustes.action_l10n_py_descargar_plantilla()
        self.assertIn('/web/content/', accion['url'])
        adjunto = self.env['ir.attachment'].browse(int(accion['url'].split('/')[3].split('?')[0]))
        _datos, errores, _ = excel.leer_libro(adjunto.raw, {'PYG', 'USD'})
        self.assertEqual(errores, [])

    # -- Carga ------------------------------------------------------------------------------

    def _cargar_plan_propio(self):
        empresa = self._empresa()
        empresa.l10n_py_modo_plan = 'plantilla'
        plantilla = self.Plantilla._validar_y_guardar(
            empresa, 'plan.xlsx', excel.generar_libro(_plan_propio()))
        self.assertEqual(plantilla.state, 'validada', plantilla.log)
        self.env['account.chart.template'].with_company(empresa).try_loading('py', empresa)
        return empresa, plantilla

    def test_15_carga_del_plan_propio(self):
        empresa, plantilla = self._cargar_plan_propio()
        self.assertEqual(empresa.chart_template, 'py')
        self.assertEqual(plantilla.state, 'cargada')
        Cuenta = self.env['account.account'].with_company(empresa)
        codigos = set(Cuenta.search([('company_ids', 'in', empresa.id)]).mapped('code'))
        for c in _plan_propio()['cuentas']:
            self.assertIn(c['codigo'], codigos)
        # Nada del plan estándar.
        self.assertNotIn('1.01.01.01.001', codigos)
        self.assertFalse(Cuenta.search([('company_ids', 'in', empresa.id), ('code', '=like', '%.%')]))
        # Grupos propios.
        grupos = self.env['account.group'].search([('company_id', '=', empresa.id)])
        self.assertEqual(set(grupos.mapped('name')), {g['nombre'] for g in _plan_propio()['grupos']})
        # Cuentas "con función".
        ref = self.env['account.chart.template'].with_company(empresa).ref
        self.assertEqual(empresa.with_company(empresa).l10n_py_cuenta_resultado_ejercicio_id.code, '31002')
        self.assertEqual(ref('account_journal_payment_debit_account_id').with_company(empresa).code, '11006')
        self.assertEqual(ref('account_journal_payment_credit_account_id').with_company(empresa).code, '11007')
        self.assertEqual(empresa.with_company(empresa).account_journal_suspense_account_id.code, '11005')
        self.assertEqual(empresa.with_company(empresa).income_account_id.code, '41001')
        self.assertEqual(empresa.with_company(empresa).expense_account_id.code, '51001')
        self.assertEqual(empresa.bank_account_code_prefix, '1100')
        banco = self.env['account.journal'].search([
            ('company_id', '=', empresa.id), ('type', '=', 'bank')])
        self.assertEqual(banco.with_company(empresa).default_account_id.code, '11004')
        # Impuestos, posiciones fiscales y plazos del Excel.
        impuestos = self.env['account.tax'].search([('company_id', '=', empresa.id)])
        self.assertEqual(set(impuestos.mapped('name')),
                         {'IVA 10% Ventas Propio', 'IVA 10% Compras Propio'})
        self.assertEqual(empresa.account_sale_tax_id.name, 'IVA 10% Ventas Propio')
        self.assertEqual(empresa.account_purchase_tax_id.name, 'IVA 10% Compras Propio')
        venta = impuestos.filtered(lambda t: t.type_tax_use == 'sale')
        self.assertTrue(venta.price_include_override == 'tax_included')
        cuenta_iva = venta.invoice_repartition_line_ids.filtered(
            lambda l: l.repartition_type == 'tax').account_id
        self.assertEqual(cuenta_iva.with_company(empresa).code, '21002')
        posiciones = self.env['account.fiscal.position'].search([('company_id', '=', empresa.id)])
        self.assertEqual(posiciones.mapped('name'), ['Exterior Propia'])
        plazos = self.env['account.payment.term'].search([('company_id', '=', empresa.id)])
        self.assertEqual(set(plazos.mapped('name')), {'Contado Propio', 'Treinta y sesenta Propio'})
        plazo = plazos.filtered(lambda p: p.name.startswith('Treinta'))
        self.assertEqual(sorted(plazo.line_ids.mapped('nb_days')), [30, 60])

    def test_16_con_el_plan_propio_funcionan_el_cierre_y_el_balance(self):
        empresa, _ = self._cargar_plan_propio()
        env = self.env(context=dict(self.env.context, allowed_company_ids=empresa.ids))
        Cuenta = env['account.account'].with_company(empresa)
        cuenta = lambda codigo: Cuenta.search([('code', '=', codigo), ('company_ids', 'in', empresa.id)])
        diario = env['account.journal'].search([('company_id', '=', empresa.id), ('type', '=', 'general')], limit=1)
        anio = fields.Date.today().year

        def asiento(fecha, debe, haber, monto):
            mov = env['account.move'].create({
                'move_type': 'entry', 'journal_id': diario.id, 'company_id': empresa.id, 'date': fecha,
                'line_ids': [(0, 0, {'account_id': cuenta(debe).id, 'debit': monto, 'credit': 0.0}),
                             (0, 0, {'account_id': cuenta(haber).id, 'debit': 0.0, 'credit': monto})]})
            mov.action_post()
        asiento('%s-03-01' % anio, '11002', '41001', 1000.0)
        asiento('%s-04-01' % anio, '51001', '11002', 400.0)
        filas = env['l10n_py.balance_general.report']._build_balance_general_rows(
            empresa, fields.Date.from_string('%s-12-31' % anio))
        especial = next(f for f in filas if f['tipo'] == 'especial')
        self.assertEqual(especial['saldo'], 600.0)
        cierre = env['l10n_py.cierre_ejercicio'].action_cerrar_ejercicio(empresa, anio)
        self.assertEqual(cierre.resultado_ejercicio, 600.0)
        lineas = env['account.move.line'].search([
            ('account_id', '=', cuenta('31002').id), ('parent_state', '=', 'posted'),
            ('date', '<=', '%s-12-31' % anio)])
        self.assertEqual(sum(lineas.mapped('balance')), -600.0)

    def test_17_no_se_puede_cargar_sin_plantilla_validada_ni_recargar(self):
        empresa = self._empresa('Sin Plantilla')
        empresa.l10n_py_modo_plan = 'plantilla'
        with self.assertRaises(UserError):
            self.env['account.chart.template'].with_company(empresa).try_loading('py', empresa)
        self.assertFalse(empresa.chart_template)
        # Cargada la plantilla, recargar no está permitido (solo carga inicial).
        empresa2, _ = self._cargar_plan_propio()
        with self.assertRaises(UserError):
            self.env['account.chart.template'].with_company(empresa2).try_loading('py', empresa2)
        # Y no se acepta subir otra plantilla.
        with self.assertRaises(UserError):
            self.Plantilla._validar_y_guardar(empresa2, 'otra.xlsx', excel.generar_libro(_plan_propio()))

    def test_18_el_plan_estandar_no_cambia_y_ahora_carga_los_plazos_de_pago(self):
        empresa = self._empresa('Estandar Plazos')
        self.env['account.chart.template'].with_company(empresa).try_loading('py', empresa)
        self.assertEqual(empresa.l10n_py_modo_plan, 'estandar')
        cuentas = self.env['account.account'].with_company(empresa).search(
            [('company_ids', 'in', empresa.id)])
        self.assertEqual(len(cuentas), 228)
        self.assertEqual(empresa.with_company(empresa).l10n_py_cuenta_resultado_ejercicio_id.code, '3.03.01.01.002')
        plazos = self.env['account.payment.term'].search([('company_id', '=', empresa.id)])
        self.assertIn('30 - 60 - 90 días', plazos.mapped('name'))
        self.assertEqual(len(plazos), 6)

    def test_19_permisos_contables_automaticos_del_administrador(self):
        """Los usuarios «Contabilidad / Administrador» ven y editan el plan de cuentas, los
        grupos y las cuentas de productos y de clientes/proveedores sin ajustes manuales."""
        manager = self.env.ref('account.group_account_manager')
        self.assertIn(self.env.ref('account.group_account_user'), manager.implied_ids)
        usuario = self.env['res.users'].create({
            'name': 'Administrador Contable Test', 'login': 'adm_contable_py_test',
            'group_ids': [(6, 0, [manager.id])]})
        for xmlid in ('account.group_account_user', 'account.group_account_readonly',
                      'account.group_account_invoice'):
            self.assertTrue(usuario.has_group(xmlid), xmlid)
