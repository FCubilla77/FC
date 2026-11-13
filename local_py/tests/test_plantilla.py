# -*- coding: utf-8 -*-
"""Plantilla Excel de configuración de local_py: formato, validación y aplicación.

Las pruebas del motor (generación, lectura y validación) no necesitan base de datos,
porque `local_py_plantilla_excel` no usa el ORM; las de aplicación sí, y corren sobre
una compañía nueva con un plan de cuentas mínimo creado a mano, para no depender de
que esté instalado l10n_py ni ningún otro plan.
"""
import io

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.local_py.models import local_py_plantilla_excel as excel


@tagged('post_install', '-at_install')
class TestPlantillaFormato(TransactionCase):
    """Formato y validación, sin tocar la base."""

    def _contenido(self, contexto=None):
        return excel.generar_libro(excel.datos_ejemplo(), contexto or {})

    def test_01_la_plantilla_de_ejemplo_se_genera_y_se_lee_sin_errores(self):
        from openpyxl import load_workbook
        contenido = self._contenido()
        libro = load_workbook(io.BytesIO(contenido))
        esperadas = ([excel.HOJA_INSTRUCCIONES, excel.HOJA_LISTAS]
                     + list(excel.ENCABEZADOS) )
        self.assertEqual(libro.sheetnames, esperadas)
        for hoja, encabezado in excel.ENCABEZADOS.items():
            fila = next(libro[hoja].iter_rows(min_row=1, max_row=1, max_col=len(encabezado)))
            self.assertEqual([c.value for c in fila], encabezado,
                             "Encabezados distintos en la hoja «%s»" % hoja)
        _datos, errores, _avisos = excel.leer_libro(contenido)
        self.assertFalse(errores, "La plantilla recién generada no debería tener errores: %s"
                         % errores)

    def test_02_las_filas_de_ejemplo_no_cargan_nada(self):
        """La planilla recién descargada se tiene que poder subir tal cual: las filas de
        ejemplo de las hojas de lista llevan «#» y se ignoran."""
        datos, errores, _avisos = excel.leer_libro(self._contenido())
        self.assertFalse(errores)
        for clave in ('diarios_fiscales', 'series_recibo', 'rubricas', 'chequeras',
                      'detalle_inventario', 'renumeracion', 'no_retencion'):
            self.assertEqual(datos[clave], [], "«%s» no debería traer nada" % clave)
        # Las hojas de clave/valor sí traen los valores de ejemplo.
        self.assertEqual(len(datos['cuentas']), len(excel.CUENTAS))
        self.assertEqual(len(datos['diarios']), len(excel.DIARIOS))
        self.assertEqual(len(datos['parametros']), len(excel.PARAMETROS))

    def test_03_un_archivo_que_no_es_excel_da_un_error_claro(self):
        datos, errores, _avisos = excel.leer_libro(b'esto no es un xlsx')
        self.assertIsNone(datos)
        self.assertTrue(errores and 'Excel' in errores[0])

    def test_04_una_cuenta_que_no_esta_en_el_plan_es_un_error(self):
        contexto = {'cuentas': {'X': 'expense'}}
        _datos, errores, _avisos = excel.leer_libro(self._contenido(), contexto)
        self.assertTrue(any('no existe en el plan de cuentas' in e for e in errores),
                        "Debería avisar que los códigos de ejemplo no están en el plan: %s"
                        % errores)

    def test_05_los_campos_de_la_configuracion_existen(self):
        """Un typo en el nombre de campo de las tablas de la plantilla no se vería hasta
        aplicarla, con la configuración a medio escribir."""
        campos = self.env['local_py.configuracion_localizacion']._fields
        for definicion in excel.CUENTAS:
            self.assertIn(definicion[5], campos)
        for definicion in excel.DIARIOS:
            self.assertIn(definicion[6], campos)
            self.assertIn(definicion[2], ('general', 'bank', 'sale', 'purchase', 'cash', 'credit'))
        for clave, _desc, _tipo, _std, campo in excel.PARAMETROS:
            if campo:
                self.assertIn(campo, campos)
            else:
                self.assertEqual(clave, 'imputacion_tributaria')


@tagged('post_install', '-at_install')
class TestPlantillaAplicacion(TransactionCase):
    """Aplicación sobre una compañía con un plan de cuentas propio, de numeración libre
    (justamente lo que la plantilla tiene que soportar)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({'name': 'Plantilla Test SA'})
        # Plan propio SIN puntos: con el criterio viejo (prefijo del código) nada de esto
        # habría entrado en los reportes ni se habría podido configurar.
        cls.cuentas = {}
        for codigo, nombre, tipo in (
                ('11001', 'Caja', 'asset_cash'),
                ('11002', 'Retenido a confirmar', 'asset_current'),
                ('11003', 'Retenciones recibidas IVA', 'asset_current'),
                ('11004', 'Retenciones recibidas Renta', 'asset_current'),
                ('11005', 'Cheques rechazados', 'asset_current'),
                ('21001', 'Retenciones a pagar', 'liability_current'),
                ('51001', 'Gasto por absorción', 'expense'),
        ):
            cls.cuentas[codigo] = cls.env['account.account'].create({
                'code': codigo, 'name': nombre, 'account_type': tipo,
                'company_ids': [(6, 0, [cls.company.id])]})

    def _plantilla(self, ajustes=None):
        """Crea una plantilla ya validada con un juego de datos propio de este plan."""
        datos = excel.datos_ejemplo()
        datos['cuentas'] = {
            'cuenta_gasto_absorcion': '51001',
            'cuenta_gasto_absorcion_renta': '51001',
            'cuenta_retencion_a_confirmar': '11002',
            'cuenta_retenciones_recibidas_iva': '11003',
            'cuenta_retenciones_recibidas_renta': '11004',
            'cuenta_retenciones_diferencia': '51001',
            'cuenta_cheques_rechazados': '11005',
        }
        datos['diarios'] = {
            'diario_retencion_iva': {'nombre': 'Ret. IVA', 'codigo': 'TRIVA',
                                     'cuenta': '21001', 'tipo': 'general'},
            'diario_retencion_renta': {'nombre': 'Ret. Renta', 'codigo': 'TRRTA',
                                       'cuenta': '21001', 'tipo': 'general'},
            'diario_retencion_recibida': {'nombre': 'Ret. Recibida', 'codigo': 'TRREC',
                                          'cuenta': '11002', 'tipo': 'general'},
            'diario_cheque_cliente': {'nombre': 'Cheques Clientes', 'codigo': 'TCHCL',
                                      'cuenta': '11001', 'tipo': 'bank'},
        }
        datos['parametros'] = {
            'retencion_iva': True, 'retencion_iva_porcentaje': 30.0,
            'retencion_iva_minimo': 0.0, 'retencion_renta': True,
            'pagos_proveedores_activo': False, 'pagos_clientes_activo': False,
            'asiento_ajuste_inventario': True, 'imputacion_tributaria': [],
        }
        datos['detalle_inventario'] = [
            {'cuenta': '11001', 'criterio': 'contacto', 'nivel': 'top', 'cantidad': 5}]
        datos['renumeracion'] = [{'anio': 2026, 'numero_inicial': 100}]
        datos['diarios_fiscales'] = []
        datos['series_recibo'] = []
        datos['rubricas'] = []
        datos['chequeras'] = []
        datos['no_retencion'] = []
        datos['conceptos_inr'] = []
        if ajustes:
            datos.update(ajustes)
        import json
        return self.env['local_py.plantilla'].create({
            'company_id': self.company.id, 'nombre_archivo': 'prueba.xlsx',
            'state': 'validada', 'datos': json.dumps(datos)})

    def test_01_aplicar_crea_los_diarios_y_completa_la_configuracion(self):
        plantilla = self._plantilla()
        plantilla.aplicar()
        self.assertEqual(plantilla.state, 'aplicada')
        config = self.env['local_py.configuracion_localizacion'].search(
            [('company_id', '=', self.company.id)], limit=1)
        self.assertTrue(config, "Debería existir la Configuración de la compañía.")
        self.assertEqual(config.local_py_cuenta_retencion_a_confirmar_id,
                         self.cuentas['11002'])
        self.assertEqual(config.local_py_cuenta_gasto_absorcion_id, self.cuentas['51001'])
        self.assertEqual(config.local_py_diario_retencion_iva_id.code, 'TRIVA')
        self.assertEqual(config.local_py_diario_retencion_iva_id.type, 'general')
        self.assertEqual(config.local_py_diario_cheque_cliente_id.type, 'bank')
        self.assertTrue(config.local_py_retencion_iva)
        self.assertEqual(config.local_py_retencion_iva_porcentaje, 30.0)
        self.assertFalse(config.local_py_pagos_proveedores_activo)
        self.assertEqual(len(config.libro_inventario_detalle_ids), 1)
        self.assertEqual(config.libro_inventario_detalle_ids.cantidad_top, 5)
        self.assertEqual(config.renumeracion_ids.anio, 2026)

    def test_02_aplicar_dos_veces_no_duplica_nada(self):
        plantilla = self._plantilla()
        plantilla.aplicar()
        config = self.env['local_py.configuracion_localizacion'].search(
            [('company_id', '=', self.company.id)], limit=1)
        plantilla.aplicar()
        self.assertEqual(len(self.env['account.journal'].search(
            [('code', '=', 'TRIVA'), ('company_id', '=', self.company.id)])), 1)
        self.assertEqual(len(config.libro_inventario_detalle_ids), 1)
        self.assertEqual(len(config.renumeracion_ids), 1)
        self.assertEqual(len(self.env['local_py.configuracion_localizacion'].search(
            [('company_id', '=', self.company.id)])), 1)

    def test_03_aplicar_no_pisa_una_cuenta_elegida_a_mano(self):
        """Las cuentas y los diarios se completan solo si están vacíos: pisar una
        elección hecha a mano sería destructivo."""
        config = self.env['local_py.configuracion_localizacion'].create({
            'company_id': self.company.id,
            'local_py_cuenta_retencion_a_confirmar_id': self.cuentas['11001'].id})
        self._plantilla().aplicar()
        self.assertEqual(config.local_py_cuenta_retencion_a_confirmar_id,
                         self.cuentas['11001'],
                         "La cuenta elegida a mano no se tiene que pisar.")

    def test_04_una_plantilla_con_errores_no_se_puede_aplicar(self):
        from odoo.exceptions import UserError
        plantilla = self.env['local_py.plantilla'].create({
            'company_id': self.company.id, 'state': 'error', 'cantidad_errores': 1})
        with self.assertRaises(UserError):
            plantilla.aplicar()

    def test_05_el_contexto_de_validacion_trae_las_cuentas_de_la_compania(self):
        contexto = self.env['local_py.plantilla']._contexto(self.company)
        self.assertEqual(contexto['cuentas'].get('11001'), 'asset_cash')
        self.assertEqual(contexto['cuentas'].get('51001'), 'expense')
        for clave in ('diarios', 'tipos_fiscales', 'conceptos_iva', 'imputaciones',
                      'monedas', 'bancos', 'cuentas_bancarias', 'usuarios', 'rucs',
                      'codigos_inr', 'diarios_banco'):
            self.assertIn(clave, contexto)

    def test_06_la_plantilla_descargable_se_genera_contra_la_base(self):
        contenido = self.env['local_py.plantilla']._contenido_plantilla_ejemplo(self.company)
        self.assertGreater(len(contenido), 5000)
        datos, errores, _avisos = excel.leer_libro(
            contenido, self.env['local_py.plantilla']._contexto(self.company))
        # Los códigos de ejemplo son del plan estándar de Paraguay, que esta compañía no
        # tiene: tienen que salir como error, no pasar en silencio.
        self.assertTrue(any('no existe en el plan de cuentas' in e for e in errores))
        self.assertIsNotNone(datos)

    def test_07_los_conceptos_de_renta_no_residente_ajustan_porcentajes(self):
        concepto = self.env['local_py.concepto_renta_no_residente'].search([], limit=1)
        if not concepto:
            self.skipTest("La base no tiene conceptos de Renta No Residente cargados.")
        plantilla = self._plantilla({'conceptos_inr': [{
            'codigo': concepto.codigo, 'porcentaje_imputacion': 42.0,
            'porcentaje': 7.0, 'porcentaje_absorcion': 3.0}]})
        plantilla.aplicar()
        self.assertEqual(concepto.porcentaje_imputacion, 42.0)
        self.assertEqual(concepto.porcentaje, 7.0)
        self.assertEqual(concepto.porcentaje_absorcion, 3.0)


@tagged('post_install', '-at_install')
class TestReportesPorTipoDeCuenta(TransactionCase):
    """Libro Inventario y Estado de Resultados se guían por el tipo de cuenta y la
    jerarquía de Grupos, no por el código: tienen que funcionar con un plan de
    numeración libre."""

    def test_01_los_tipos_cubren_todo_el_plan_menos_las_cuentas_de_orden(self):
        from odoo.addons.local_py.models.local_py_libro_report import (
            TIPOS_BALANCE, TIPOS_INGRESO, TIPOS_RESULTADO,
        )
        todos = set(dict(self.env['account.account']._fields['account_type'].selection))
        self.assertFalse(set(TIPOS_BALANCE) & set(TIPOS_RESULTADO),
                         "Una cuenta no puede entrar en los dos reportes.")
        self.assertEqual(set(TIPOS_BALANCE) | set(TIPOS_RESULTADO), todos - {'off_balance'},
                         "Los dos reportes juntos tienen que cubrir todo el plan, salvo "
                         "las cuentas de orden.")
        self.assertTrue(set(TIPOS_INGRESO) <= set(TIPOS_RESULTADO))

    def test_02_el_nivel_sale_de_la_jerarquia_de_grupos(self):
        """Se prueba con objetos mínimos en vez de account.group reales: en Odoo el
        `parent_id` del grupo es calculado y de solo lectura (lo deriva de los prefijos
        de código), así que armar a mano una jerarquía de 3 niveles con registros reales
        probaría ese cálculo de Odoo, no el nivel que calcula este módulo."""
        from odoo.addons.local_py.models.local_py_libro_report import _nivel_grupo

        class _Grupo:
            def __init__(self, identificador, padre=None):
                self.id, self.parent_id = identificador, padre

        raiz = _Grupo(1)
        hijo = _Grupo(2, raiz)
        nieto = _Grupo(3, hijo)
        self.assertEqual(_nivel_grupo(self.env['account.group']), 0)
        self.assertEqual(_nivel_grupo(None), 0)
        self.assertEqual(_nivel_grupo(raiz), 1)
        self.assertEqual(_nivel_grupo(hijo), 2)
        self.assertEqual(_nivel_grupo(nieto), 3)
        # Una jerarquía circular (datos corruptos) no puede colgar el reporte.
        bucle_a = _Grupo(10)
        bucle_b = _Grupo(11, bucle_a)
        bucle_a.parent_id = bucle_b
        self.assertEqual(_nivel_grupo(bucle_a), 2)
