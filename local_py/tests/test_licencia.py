# -*- coding: utf-8 -*-
"""Licencia OPL-1 de local_py y control de licencia atado a la base de datos."""
import ast
import base64
import json
import os
import re
from datetime import date, timedelta
from unittest import mock, skipIf

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from odoo import release
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.local_py.models import local_py_licencia as _mod
from odoo.addons.local_py.models.local_py_licencia import (
    local_py_decodificar_licencia,
    local_py_licencia_exenta,
    local_py_version_odoo_instalada,
)

SIN_CONTROL = not _mod.LOCAL_PY_LICENCIA_OBLIGATORIA
MOTIVO_SIN_CONTROL = (
    "Build de partner: LOCAL_PY_LICENCIA_OBLIGATORIA = False, el control de "
    "licencia está desactivado por diseño y no hay nada que bloquear aquí.")


def _firmar(clave_privada, uuid_, cliente, vence, producto="local_py",
            version_odoo=None, prefijo="FC_PY1"):
    """Genera un código de licencia como lo haría el script de FC_Py, pero firmado
    con una clave de prueba (nunca la clave privada real).

    Por defecto usa la versión de Odoo realmente instalada, para que las pruebas que
    no prueban el control de versión no se vean afectadas por él.
    """
    if version_odoo is None:
        version_odoo = local_py_version_odoo_instalada()
    payload = {"p": producto, "u": uuid_, "c": cliente, "v": vence, "m": version_odoo}
    datos = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    firma = clave_privada.sign(
        datos,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256())
    b64 = lambda data: base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")
    return "%s.%s.%s" % (prefijo, b64(datos), b64(firma))


@tagged('post_install', '-at_install')
class TestLicenciaLocalPy(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Clave de prueba propia: nunca es la clave pública embebida en el módulo,
        # así que los códigos firmados con ella deben darse siempre por inválidos,
        # salvo que la prueba reemplace temporalmente la clave pública del módulo
        # (_mock_clave_publica).
        cls.clave_prueba = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        cls.company = cls.env.company
        cls.uuid_base = cls.env['ir.config_parameter'].sudo().get_param('database.uuid')
        cls.ayer = str(date.today() - timedelta(days=1))
        cls.manana = str(date.today() + timedelta(days=1))

    def setUp(self):
        super().setUp()
        self.company.local_py_licencia_codigo = False

    def _mock_clave_publica(self):
        return mock.patch.object(
            _mod, '_local_py_obtener_clave_publica',
            return_value=self.clave_prueba.public_key())

    def _cargar_licencia_valida(self):
        self.company.local_py_licencia_codigo = _firmar(
            self.clave_prueba, self.uuid_base, "Cliente de Prueba", self.manana)

    def _forzado(self, modelo):
        return self.env[modelo].with_context(local_py_licencia_forzar_test=True)

    # -- Criptografía (clave de prueba, nunca la real) -------------------------

    def test_01_codigo_vacio_o_mal_formado(self):
        for codigo in ('', '   ', 'cualquier-cosa', 'FC_PY1.solo-dos-partes',
                       'OTRO.aaa.bbb'):
            with self.assertRaises(ValueError):
                local_py_decodificar_licencia(codigo)

    def test_02_codigo_de_otro_producto_no_sirve(self):
        codigo = _firmar(self.clave_prueba, self.uuid_base, "Cliente X", self.manana,
                         producto="l10n_py")
        with self._mock_clave_publica():
            with self.assertRaisesRegex(ValueError, "otro_producto"):
                local_py_decodificar_licencia(codigo)

    def test_03_contenido_incompleto(self):
        # Payload sin el campo 'm' (versión de Odoo autorizada).
        payload = {"p": "local_py", "u": self.uuid_base, "c": "Cliente X",
                   "v": self.manana}
        datos = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        firma = self.clave_prueba.sign(
            datos,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256())
        b64 = lambda data: base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")
        codigo = "FC_PY1.%s.%s" % (b64(datos), b64(firma))
        with self._mock_clave_publica():
            with self.assertRaisesRegex(ValueError, "contenido"):
                local_py_decodificar_licencia(codigo)

    def test_04_codigo_bien_formado_devuelve_sus_datos(self):
        codigo = _firmar(self.clave_prueba, self.uuid_base, "Cliente X", self.manana)
        with self._mock_clave_publica():
            datos = local_py_decodificar_licencia(codigo)
        self.assertEqual(datos['uuid'], self.uuid_base)
        self.assertEqual(datos['cliente'], "Cliente X")
        self.assertEqual(datos['vence'], self.manana)
        self.assertEqual(datos['version_odoo'], local_py_version_odoo_instalada())

    # -- Estados de la licencia en la compañía --------------------------------

    def test_05_estado_sin_licencia(self):
        self.assertEqual(self.company.local_py_licencia_estado, 'sin_licencia')
        self.assertFalse(self.company._local_py_licencia_valida())

    def test_06_firma_de_otra_clave_es_invalida(self):
        # Sin mockear la clave pública: el módulo verifica con la clave REAL, así
        # que un código firmado con la clave de prueba tiene que ser inválido.
        self.company.local_py_licencia_codigo = _firmar(
            self.clave_prueba, self.uuid_base, "Cliente X", self.manana)
        self.assertEqual(self.company.local_py_licencia_estado, 'invalida')
        self.assertFalse(self.company._local_py_licencia_valida())

    def test_07_estado_valida(self):
        with self._mock_clave_publica():
            self._cargar_licencia_valida()
            self.assertEqual(self.company.local_py_licencia_estado, 'valida')
            self.assertEqual(self.company.local_py_licencia_cliente, "Cliente de Prueba")
            self.assertTrue(self.company._local_py_licencia_valida())

    def test_08_estado_vencida(self):
        with self._mock_clave_publica():
            self.company.local_py_licencia_codigo = _firmar(
                self.clave_prueba, self.uuid_base, "Cliente X", self.ayer)
            self.assertEqual(self.company.local_py_licencia_estado, 'vencida')

    def test_09_licencia_de_otra_base_es_invalida(self):
        with self._mock_clave_publica():
            self.company.local_py_licencia_codigo = _firmar(
                self.clave_prueba, "otra-base-distinta", "Cliente X", self.manana)
            self.assertEqual(self.company.local_py_licencia_estado, 'invalida')

    def test_10_estado_otra_version(self):
        with self._mock_clave_publica():
            self.company.local_py_licencia_codigo = _firmar(
                self.clave_prueba, self.uuid_base, "Cliente X", self.manana,
                version_odoo=local_py_version_odoo_instalada() + 1)
            self.assertEqual(self.company.local_py_licencia_estado, 'otra_version')

    def test_11_codigo_de_la_base_trae_version_y_uuid(self):
        esperado = "%s|%s" % (local_py_version_odoo_instalada(), self.uuid_base)
        self.assertEqual(self.company.local_py_licencia_uuid, esperado)

    # -- Versión: verificación INDEPENDIENTE de la función bajo prueba ---------

    def test_12_version_central_coincide_con_el_manifest(self):
        # Lee el manifest directamente (ast.literal_eval), sin usar la función
        # `local_py_version_odoo_instalada` para construir el valor esperado: una
        # prueba que compara la función contra sí misma no detectaría un error
        # sistemático en ella (en Taller, un bug así devolvía 0 y pasó inadvertido).
        ruta = os.path.join(os.path.dirname(os.path.dirname(__file__)), '__manifest__.py')
        with open(ruta, encoding='utf-8') as archivo:
            manifest = ast.literal_eval(archivo.read())
        version = manifest['version']
        coincidencia = re.match(r'^\d{4}\.(\d+)\.\d+$', version)
        self.assertTrue(coincidencia, "Esquema de versión inesperado: %s" % version)
        esperado = int(coincidencia.group(1))
        self.assertEqual(esperado, int(release.major_version.split('.')[0]))
        self.assertEqual(local_py_version_odoo_instalada(), esperado)
        self.assertNotEqual(local_py_version_odoo_instalada(), 2026)
        self.assertNotEqual(local_py_version_odoo_instalada(), 0)

    def test_13_la_licencia_declara_OPL_1(self):
        ruta = os.path.join(os.path.dirname(os.path.dirname(__file__)), '__manifest__.py')
        with open(ruta, encoding='utf-8') as archivo:
            manifest = ast.literal_eval(archivo.read())
        self.assertEqual(manifest['license'], 'OPL-1')

    # -- Bloqueo de creación y edición (se fuerza el control en la prueba) -----

    @skipIf(SIN_CONTROL, MOTIVO_SIN_CONTROL)
    def test_14_sin_licencia_no_se_puede_crear_un_maestro(self):
        with self.assertRaises(UserError):
            self._forzado('local_py.concepto_iva').create({
                'name': "Concepto sin licencia", 'codigo': "IVA.TEST"})

    @skipIf(SIN_CONTROL, MOTIVO_SIN_CONTROL)
    def test_15_maestro_ya_creado_se_puede_seguir_editando(self):
        # Decisión de alcance: el control de edición solo se aplica a los documentos
        # de trabajo en curso y a Configuraciones Localización Py, no a los maestros:
        # una licencia vencida no debe impedir corregir un dato ya cargado.
        concepto = self.env['local_py.concepto_iva'].create({
            'name': "Concepto ya creado", 'codigo': "IVA.TEST2"})
        concepto.with_context(local_py_licencia_forzar_test=True).name = "Corregido"
        self.assertEqual(concepto.name, "Corregido")

    @skipIf(SIN_CONTROL, MOTIVO_SIN_CONTROL)
    def test_16_sin_licencia_no_se_puede_crear_un_documento(self):
        banco = self.env['res.bank'].create({'name': "Banco de Prueba"})
        with self.assertRaises(UserError):
            self._forzado('local_py.cheque_cliente').create({
                'name': "0000001", 'bank_id': banco.id})

    @skipIf(SIN_CONTROL, MOTIVO_SIN_CONTROL)
    def test_17_sin_licencia_no_se_puede_editar_un_documento(self):
        banco = self.env['res.bank'].create({'name': "Banco de Prueba 2"})
        cheque = self.env['local_py.cheque_cliente'].create({
            'name': "0000002", 'bank_id': banco.id})
        with self.assertRaises(UserError):
            cheque.with_context(local_py_licencia_forzar_test=True).write(
                {'name': "0000003"})

    @skipIf(SIN_CONTROL, MOTIVO_SIN_CONTROL)
    def test_18_con_licencia_valida_se_puede_crear_y_editar(self):
        with self._mock_clave_publica():
            self._cargar_licencia_valida()
            concepto = self._forzado('local_py.concepto_iva').create({
                'name': "Concepto con licencia", 'codigo': "IVA.TEST3"})
            self.assertTrue(concepto.id)
            banco = self.env['res.bank'].create({'name': "Banco de Prueba 3"})
            cheque = self._forzado('local_py.cheque_cliente').create({
                'name': "0000004", 'bank_id': banco.id})
            cheque.with_context(local_py_licencia_forzar_test=True).write(
                {'name': "0000005"})
            self.assertEqual(cheque.name, "0000005")

    # -- Bloqueo quirúrgico del timbrado en los diarios -----------------------

    @skipIf(SIN_CONTROL, MOTIVO_SIN_CONTROL)
    def test_19_configurar_timbrado_en_un_diario_requiere_licencia(self):
        diario = self.env['account.journal'].create({
            'name': "Diario Timbrado Test", 'code': "TBTST", 'type': 'sale'})
        with self.assertRaises(UserError):
            diario.with_context(local_py_licencia_forzar_test=True).write(
                {'local_py_timbrado': 12345678})

    @skipIf(SIN_CONTROL, MOTIVO_SIN_CONTROL)
    def test_20_un_diario_comun_no_requiere_licencia(self):
        # El control es quirúrgico: crear o editar un diario sin tocar la
        # numeración fiscal nunca se bloquea (Odoo escribe en account.journal
        # internamente en muchos flujos).
        diario = self._forzado('account.journal').create({
            'name': "Diario Comun Test", 'code': "CMTST", 'type': 'bank'})
        self.assertTrue(diario.id)
        diario.with_context(local_py_licencia_forzar_test=True).write(
            {'name': "Diario Comun Renombrado"})
        self.assertEqual(diario.name, "Diario Comun Renombrado")

    @skipIf(SIN_CONTROL, MOTIVO_SIN_CONTROL)
    def test_21_el_asistente_de_configuracion_requiere_licencia(self):
        wizard = self.env['local_py.config_paraguay.wizard'].create({})
        with self.assertRaises(UserError):
            wizard.with_context(local_py_licencia_forzar_test=True).action_confirm()

    # -- Exenciones ------------------------------------------------------------

    def test_22_sin_forzar_el_control_las_pruebas_quedan_exentas(self):
        # Fuera de `local_py_licencia_forzar_test`, las pruebas quedan exentas, así
        # que el resto de las pruebas del módulo no necesita simular una licencia.
        self.assertTrue(local_py_licencia_exenta(self.env))
        concepto = self.env['local_py.concepto_iva'].create({
            'name': "Concepto sin forzar control", 'codigo': "IVA.TEST4"})
        self.assertTrue(concepto.id)

    def test_23_build_de_partner_sin_control_de_licencia(self):
        # El ZIP que se entrega a un partner con reventa ilimitada cambia esta
        # constante a False al armarse: el control queda enteramente a cargo del
        # contrato, no de la base de datos de cada cliente del partner.
        original = _mod.LOCAL_PY_LICENCIA_OBLIGATORIA
        _mod.LOCAL_PY_LICENCIA_OBLIGATORIA = False
        try:
            self.assertTrue(local_py_licencia_exenta(self.env))
            concepto = self._forzado('local_py.concepto_iva').create({
                'name': "Concepto build partner", 'codigo': "IVA.TEST5"})
            self.assertTrue(concepto.id)
        finally:
            _mod.LOCAL_PY_LICENCIA_OBLIGATORIA = original
