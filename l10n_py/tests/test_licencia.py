# -*- coding: utf-8 -*-
"""Licencia OPL-1 de l10n_py y control de licencia atado a la base de datos."""
import ast
import base64
import json
import os
import re
from datetime import date, timedelta
from unittest import mock

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from odoo import release
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.l10n_py.models import l10n_py_licencia as _mod
from odoo.addons.l10n_py.models.l10n_py_licencia import (
    l10n_py_decodificar_licencia,
    l10n_py_licencia_exenta,
    l10n_py_version_odoo_instalada,
)


def _firmar(clave_privada, uuid_, cliente, vence, producto="l10n_py", version_odoo=None,
            prefijo="L10NPY1"):
    """Genera un código de licencia como lo haría el script de FC_Py, pero firmado con
    una clave de prueba (nunca la clave privada real).

    Por defecto usa la versión de Odoo realmente instalada, para que las pruebas que no
    prueban el control de versión no se vean afectadas por él.
    """
    if version_odoo is None:
        version_odoo = l10n_py_version_odoo_instalada()
    payload = {"p": producto, "u": uuid_, "c": cliente, "v": vence, "m": version_odoo}
    datos = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    firma = clave_privada.sign(
        datos,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256())
    b64 = lambda data: base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")
    return "%s.%s.%s" % (prefijo, b64(datos), b64(firma))


@tagged('post_install', '-at_install')
class TestLicenciaL10nPy(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Clave de prueba propia: nunca es la clave pública embebida en el módulo, así
        # que los códigos firmados con ella deben darse siempre por inválidos, salvo
        # que la prueba reemplace temporalmente la clave pública (_mock_clave_publica).
        cls.clave_prueba = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.uuid_base = cls.env['res.company']._l10n_py_licencia_uuid_actual()
        cls.company = cls.env.company
        cls.manana = (date.today() + timedelta(days=30)).isoformat()

    def _mock_clave_publica(self):
        return mock.patch.object(
            _mod, '_l10n_py_obtener_clave_publica',
            return_value=self.clave_prueba.public_key())

    def _cargar_licencia_valida(self):
        codigo = _firmar(self.clave_prueba, self.uuid_base, "Cliente X", self.manana)
        self.company.l10n_py_licencia_codigo = codigo
        return codigo

    def _cierre_vals(self):
        return {
            'company_id': self.company.id,
            'anio': 2099,
            'fecha_cierre': '2099-12-31',
            'fecha_apertura': '2100-01-01',
        }

    def _cierre_forzado(self):
        return self.env['l10n_py.cierre_ejercicio'].with_context(
            l10n_py_licencia_forzar_test=True)

    # -- Criptografía ---------------------------------------------------------

    def test_01_codigo_firmado_con_otra_clave_no_valida(self):
        codigo = _firmar(self.clave_prueba, self.uuid_base, "Cliente X", self.manana)
        with self.assertRaisesRegex(ValueError, "firma"):
            l10n_py_decodificar_licencia(codigo)

    def test_02_codigo_vacio_o_con_formato_incorrecto(self):
        for malo in ("", "   ", "cualquier-cosa", "L10NPY1.solo-dos-partes",
                     "TLLRFC1.a.b", "OTRO.a.b"):
            with self.assertRaises(ValueError):
                l10n_py_decodificar_licencia(malo)

    def test_02b_codigo_sin_campo_de_version_no_valida(self):
        payload = {"p": "l10n_py", "u": self.uuid_base, "c": "Cliente X", "v": self.manana}
        datos = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        firma = self.clave_prueba.sign(
            datos,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256())
        b64 = lambda data: base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")
        codigo = "L10NPY1.%s.%s" % (b64(datos), b64(firma))
        with self._mock_clave_publica():
            with self.assertRaisesRegex(ValueError, "contenido"):
                l10n_py_decodificar_licencia(codigo)

    def test_02c_codigo_de_otro_producto_no_valida(self):
        codigo = _firmar(self.clave_prueba, self.uuid_base, "Cliente X", self.manana,
                         producto="tllr_fc")
        with self._mock_clave_publica():
            with self.assertRaisesRegex(ValueError, "producto"):
                l10n_py_decodificar_licencia(codigo)

    def test_02d_codigo_firmado_correctamente_se_decodifica(self):
        codigo = _firmar(self.clave_prueba, self.uuid_base, "Cliente X", self.manana)
        with self._mock_clave_publica():
            datos = l10n_py_decodificar_licencia(codigo)
        self.assertEqual(datos['uuid'], self.uuid_base)
        self.assertEqual(datos['cliente'], "Cliente X")
        self.assertEqual(datos['vence'], self.manana)
        self.assertEqual(datos['version_odoo'], l10n_py_version_odoo_instalada())

    # -- Estados de la compañía -------------------------------------------------

    def test_03_estado_sin_codigo(self):
        self.company.l10n_py_licencia_codigo = False
        self.assertEqual(self.company.l10n_py_licencia_estado, 'sin_licencia')
        self.assertFalse(self.company._l10n_py_licencia_valida())

    def test_04_estado_con_codigo_de_otra_clave(self):
        self.company.l10n_py_licencia_codigo = _firmar(
            self.clave_prueba, self.uuid_base, "Cliente X", self.manana)
        self.assertEqual(self.company.l10n_py_licencia_estado, 'invalida')
        self.assertFalse(self.company._l10n_py_licencia_valida())

    def test_05_estado_valida(self):
        with self._mock_clave_publica():
            self._cargar_licencia_valida()
            self.assertEqual(self.company.l10n_py_licencia_estado, 'valida')
            self.assertEqual(self.company.l10n_py_licencia_cliente, "Cliente X")
            self.assertTrue(self.company._l10n_py_licencia_valida())

    def test_06_estado_vencida(self):
        ayer = (date.today() - timedelta(days=1)).isoformat()
        with self._mock_clave_publica():
            self.company.l10n_py_licencia_codigo = _firmar(
                self.clave_prueba, self.uuid_base, "Cliente X", ayer)
            self.assertEqual(self.company.l10n_py_licencia_estado, 'vencida')

    def test_07_estado_otra_base(self):
        with self._mock_clave_publica():
            self.company.l10n_py_licencia_codigo = _firmar(
                self.clave_prueba, "otra-base-distinta", "Cliente X", self.manana)
            self.assertEqual(self.company.l10n_py_licencia_estado, 'invalida')

    def test_08_estado_otra_version(self):
        with self._mock_clave_publica():
            self.company.l10n_py_licencia_codigo = _firmar(
                self.clave_prueba, self.uuid_base, "Cliente X", self.manana,
                version_odoo=l10n_py_version_odoo_instalada() + 1)
            self.assertEqual(self.company.l10n_py_licencia_estado, 'otra_version')

    def test_09_codigo_de_la_base_trae_version_y_uuid(self):
        esperado = "%s|%s" % (l10n_py_version_odoo_instalada(), self.uuid_base)
        self.assertEqual(self.company.l10n_py_licencia_uuid, esperado)

    # -- Versión: verificación INDEPENDIENTE de la función bajo prueba -----------

    def test_10_version_central_coincide_con_el_manifest(self):
        # Lee el manifest directamente (ast.literal_eval), sin usar la función
        # `l10n_py_version_odoo_instalada` para construir el valor esperado: una
        # prueba que compara la función contra sí misma no detectaría un error
        # sistemático en ella.
        ruta = os.path.join(os.path.dirname(os.path.dirname(__file__)), '__manifest__.py')
        with open(ruta, encoding='utf-8') as archivo:
            manifest = ast.literal_eval(archivo.read())
        version = manifest['version']
        coincidencia = re.match(r'^(\d+)\.0\.\d{4}\.\d+$', version)
        self.assertTrue(coincidencia, "Esquema de versión inesperado: %s" % version)
        esperado = int(coincidencia.group(1))
        self.assertEqual(esperado, int(release.major_version.split('.')[0]))
        self.assertEqual(l10n_py_version_odoo_instalada(), esperado)
        self.assertNotEqual(l10n_py_version_odoo_instalada(), 2026)

    # -- Bloqueo de creación y edición (se fuerza el control dentro de la prueba) -

    def test_11_sin_licencia_no_se_puede_crear_un_cierre(self):
        self.company.l10n_py_licencia_codigo = False
        with self.assertRaises(UserError):
            self._cierre_forzado().create(self._cierre_vals())

    def test_12_con_licencia_valida_se_puede_crear_y_editar(self):
        with self._mock_clave_publica():
            self._cargar_licencia_valida()
            cierre = self._cierre_forzado().create(self._cierre_vals())
            cierre.write({'resultado_ejercicio': 5.0})
            self.assertEqual(cierre.resultado_ejercicio, 5.0)

    def test_13_licencia_vencida_bloquea_la_edicion(self):
        with self._mock_clave_publica():
            self._cargar_licencia_valida()
            cierre = self._cierre_forzado().create(self._cierre_vals())
            self.company.l10n_py_licencia_codigo = False
            with self.assertRaises(UserError):
                cierre.with_context(l10n_py_licencia_forzar_test=True).write(
                    {'resultado_ejercicio': 9.0})

    def test_14_sin_control_forzado_no_se_bloquea_en_pruebas(self):
        self.company.l10n_py_licencia_codigo = False
        cierre = self.env['l10n_py.cierre_ejercicio'].create(self._cierre_vals())
        self.assertTrue(cierre.id)

    def test_15_la_consulta_no_se_bloquea(self):
        with self._mock_clave_publica():
            self._cargar_licencia_valida()
            cierre = self._cierre_forzado().create(self._cierre_vals())
            self.company.l10n_py_licencia_codigo = False
            leido = cierre.with_context(l10n_py_licencia_forzar_test=True)
            self.assertEqual(leido.anio, 2099)
            self.assertTrue(leido.display_name)

    def test_16_cerrar_ejercicio_sin_licencia_falla_temprano(self):
        self.company.l10n_py_licencia_codigo = False
        with self.assertRaises(UserError):
            self._cierre_forzado().action_cerrar_ejercicio(self.company, 2099)

    # -- Gate del paquete fiscal (try_loading) ----------------------------------

    def test_17_sin_licencia_no_se_asigna_el_paquete_py(self):
        self.company.l10n_py_licencia_codigo = False
        plantilla = self.env['account.chart.template'].with_context(
            l10n_py_licencia_forzar_test=True)
        with self.assertRaises(UserError):
            plantilla.try_loading('py', self.company)

    def test_18_carga_automatica_sin_licencia_se_omite_en_silencio(self):
        self.company.l10n_py_licencia_codigo = False
        plantilla = self.env['account.chart.template'].with_context(
            l10n_py_licencia_forzar_test=True, l10n_py_licencia_auto=True)
        self.assertIsNone(plantilla.try_loading('py', self.company))

    def test_19_con_licencia_valida_se_delega_en_la_carga_nativa(self):
        plantilla = self.env['account.chart.template'].with_context(
            l10n_py_licencia_forzar_test=True)
        with self._mock_clave_publica():
            self._cargar_licencia_valida()
            # Se reemplaza `_load` (lo que `try_loading` nativo invoca al final) para no
            # instalar de verdad el plan de cuentas dentro de la prueba.
            with mock.patch.object(
                    type(plantilla), '_load', return_value='cargado') as carga:
                resultado = plantilla.try_loading('py', self.company)
        self.assertEqual(resultado, 'cargado')
        carga.assert_called_once()

    # -- Interruptor de build de partner ---------------------------------------

    def test_20_build_de_partner_sin_control_de_licencia(self):
        self.company.l10n_py_licencia_codigo = False
        original = _mod.L10N_PY_LICENCIA_OBLIGATORIA
        _mod.L10N_PY_LICENCIA_OBLIGATORIA = False
        try:
            self.assertTrue(l10n_py_licencia_exenta(self.env))
            cierre = self._cierre_forzado().create(self._cierre_vals())
            self.assertTrue(cierre.id)
        finally:
            _mod.L10N_PY_LICENCIA_OBLIGATORIA = original
