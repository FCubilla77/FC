# -*- coding: utf-8 -*-
"""Pruebas de la licencia que NO necesitan Odoo: se carga fe_py_recepcion_licencia.py
con un `odoo` simulado. Correr:  python3 -I tests/test_licencia_sin_odoo.py -v

Cubren la criptografía (con una clave de prueba, nunca la real), la lectura de la
versión desde el manifest y las exenciones. Los estados de la compañía y los bloqueos
sobre modelos reales están en test_licencia.py (requieren Odoo).
"""
import ast
import base64
import importlib.util
import json
import os
import sys
import types
import unittest
from datetime import date, timedelta
from unittest import mock

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_MODULO = os.path.join(RAIZ, 'models', 'fe_py_recepcion_licencia.py')
RUTA_MANIFEST = os.path.join(RAIZ, '__manifest__.py')


def _cargar_con_odoo_simulado(version_manifest=None):
    """Carga el módulo de licencia con un paquete `odoo` mínimo y devuelve (módulo, stub)."""
    odoo = types.ModuleType('odoo')
    odoo.release = types.SimpleNamespace(major_version='19.0')
    excepciones = types.ModuleType('odoo.exceptions')

    class UserError(Exception):
        pass
    excepciones.UserError = UserError
    modulos = types.ModuleType('odoo.modules')
    module = types.ModuleType('odoo.modules.module')
    module.current_test = None
    module.get_manifest = lambda nombre: {'version': version_manifest} if version_manifest else {}
    modulos.module = module
    odoo.exceptions, odoo.modules = excepciones, modulos
    simulados = {'odoo': odoo, 'odoo.exceptions': excepciones, 'odoo.modules': modulos,
                 'odoo.modules.module': module}
    with mock.patch.dict(sys.modules, simulados):
        spec = importlib.util.spec_from_file_location('licencia_bajo_prueba', RUTA_MODULO)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod, module, UserError


def _firmar(clave, uuid_, cliente, vence, producto='fe_py_recepcion', m=19, omitir=()):
    payload = {'p': producto, 'u': uuid_, 'c': cliente, 'v': vence, 'm': m}
    for campo in omitir:
        payload.pop(campo)
    datos = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
    firma = clave.sign(datos, padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                          salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
    b64 = lambda d: base64.urlsafe_b64encode(d).decode('ascii').rstrip('=')
    return 'FC_PY1.%s.%s' % (b64(datos), b64(firma))


class TestLicenciaSinOdoo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.mod, cls.odoo_module, cls.UserError = _cargar_con_odoo_simulado('19.0.2026.19.002')
        cls.manana = (date.today() + timedelta(days=1)).isoformat()

    def _con_clave_de_prueba(self):
        return mock.patch.object(self.mod, '_fe_py_recepcion_obtener_clave_publica',
                                 return_value=self.clave.public_key())

    def test_01_la_clave_embebida_es_valida_y_publica(self):
        self.assertIn(b'BEGIN PUBLIC KEY', self.mod.FE_PY_RECEPCION_CLAVE_PUBLICA_PEM)
        self.assertNotIn(b'PRIVATE', self.mod.FE_PY_RECEPCION_CLAVE_PUBLICA_PEM)
        self.assertEqual(self.mod._fe_py_recepcion_obtener_clave_publica().key_size, 3072)

    def test_02_firma_de_otra_clave_no_valida(self):
        with self.assertRaisesRegex(ValueError, 'firma'):
            self.mod.fe_py_recepcion_decodificar_licencia(_firmar(self.clave, 'u', 'X', self.manana))

    def test_03_formatos_incorrectos(self):
        for malo in ('', '   ', 'cualquier-cosa', 'FC_PY1.solo-dos-partes', 'OTRO.a.b'):
            with self.assertRaises(ValueError):
                self.mod.fe_py_recepcion_decodificar_licencia(malo)

    def test_04_codigo_valido_devuelve_sus_datos(self):
        codigo = _firmar(self.clave, 'uuid-1', 'Cliente X', self.manana)
        with self._con_clave_de_prueba():
            self.assertEqual(self.mod.fe_py_recepcion_decodificar_licencia(codigo), {
                'uuid': 'uuid-1', 'cliente': 'Cliente X', 'vence': self.manana, 'version_odoo': 19})

    def test_05_otro_producto(self):
        codigo = _firmar(self.clave, 'u', 'X', self.manana, producto='local_py')
        with self._con_clave_de_prueba(), self.assertRaisesRegex(ValueError, 'otro_producto'):
            self.mod.fe_py_recepcion_decodificar_licencia(codigo)

    def test_06_faltan_campos(self):
        for campo in ('p', 'u', 'c', 'v', 'm'):
            codigo = _firmar(self.clave, 'u', 'X', self.manana, omitir=(campo,))
            with self._con_clave_de_prueba(), self.assertRaisesRegex(ValueError, 'contenido'):
                self.mod.fe_py_recepcion_decodificar_licencia(codigo)

    def test_07_version_y_fecha_mal_formadas(self):
        for kwargs in ({'m': '19'}, {'m': True}, {'vence': 'no-es-fecha'}):
            vence = kwargs.get('vence', self.manana)
            codigo = _firmar(self.clave, 'u', 'X', vence, m=kwargs.get('m', 19))
            with self._con_clave_de_prueba(), self.assertRaisesRegex(ValueError, 'contenido'):
                self.mod.fe_py_recepcion_decodificar_licencia(codigo)

    def test_08_version_instalada_normalizada_por_odoo(self):
        # Odoo antepone su serie: «2026.19.002» se expone como «19.0.2026.19.002».
        for version, esperado in (('19.0.2026.19.002', 19), ('2026.19.002', 19),
                                  ('19.0.2026.20.003', 20), ('2026.21.010', 21)):
            mod, _m, _e = _cargar_con_odoo_simulado(version)
            self.assertEqual(mod.fe_py_recepcion_version_odoo_instalada(), esperado, version)

    def test_09_version_instalada_contra_el_manifest_real(self):
        # Prueba independiente: el valor esperado se lee del manifest con ast, sin usar
        # la función bajo prueba (un bug sistemático no puede pasar inadvertido).
        with open(RUTA_MANIFEST, encoding='utf-8') as archivo:
            version = ast.literal_eval(archivo.read())['version']
        esperado = int(version.split('.')[-2])
        self.assertEqual(esperado, 19)
        mod, _m, _e = _cargar_con_odoo_simulado('19.0.' + version)
        self.assertEqual(mod.fe_py_recepcion_version_odoo_instalada(), esperado)

    def test_10_version_sin_manifest_es_none(self):
        mod, _m, _e = _cargar_con_odoo_simulado(None)
        self.assertIsNone(mod.fe_py_recepcion_version_odoo_instalada())

    def test_11_control_y_exenciones(self):
        mod = self.mod
        env = types.SimpleNamespace(context={}, registry=types.SimpleNamespace(ready=True))
        self.assertTrue(mod.fe_py_recepcion_control_activo(env))
        self.assertFalse(mod.fe_py_recepcion_licencia_exenta(env))
        # durante la instalación (registro no listo)
        env.registry.ready = False
        self.assertTrue(mod.fe_py_recepcion_licencia_exenta(env))
        env.registry.ready = True
        # paso interno del sistema
        env.context = {'fe_py_recepcion_licencia_omitir': True}
        self.assertTrue(mod.fe_py_recepcion_licencia_exenta(env))
        env.context = {}
        # pruebas automáticas: inactivo salvo que se fuerce
        self.odoo_module.current_test = object()
        try:
            self.assertFalse(mod.fe_py_recepcion_control_activo(env))
            env.context = {'fe_py_recepcion_licencia_forzar_test': True}
            self.assertTrue(mod.fe_py_recepcion_control_activo(env))
        finally:
            self.odoo_module.current_test = None
        # interruptor de partner
        with mock.patch.object(mod, 'FE_PY_RECEPCION_LICENCIA_OBLIGATORIA', False):
            self.assertFalse(mod.fe_py_recepcion_control_activo(env))
            self.assertTrue(mod.fe_py_recepcion_licencia_exenta(env))

    def test_12_verificar_lanza_error_sin_licencia(self):
        mod = self.mod
        company = types.SimpleNamespace(_fe_py_recepcion_licencia_valida=lambda: False)
        env = types.SimpleNamespace(context={}, registry=types.SimpleNamespace(ready=True),
                                    company=company)
        with self.assertRaises(self.UserError):
            mod.fe_py_recepcion_licencia_verificar(env)
        company._fe_py_recepcion_licencia_valida = lambda: True
        mod.fe_py_recepcion_licencia_verificar(env)  # no lanza


if __name__ == '__main__':
    unittest.main()
