# -*- coding: utf-8 -*-
"""Pruebas del control de licencia de FE_Py.

La criptografía se prueba con un par de claves generado acá mismo, AJENO al del
módulo: la clave privada real de FC_Py nunca está en el repositorio, así que no
se puede firmar un código que valide contra la clave pública embebida. Para
probar los estados se reemplaza temporalmente la clave pública del módulo por la
de prueba (y se limpia la caché), y al terminar se restaura.

El bloqueo se prueba forzando el control con el contexto
`fe_py_licencia_forzar_test`, porque `fe_py_control_activo` lo desactiva durante
las pruebas automáticas para no obligar a simular una licencia en el resto de la
suite del módulo.
"""
import ast
import base64
import json
import pathlib
import unittest
from datetime import date, timedelta

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.FE_Py.models import fe_py_licencia as lic

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    CRYPTO = True
except Exception:  # pragma: no cover
    CRYPTO = False


def _b64(datos):
    return base64.urlsafe_b64encode(datos).decode('ascii').rstrip('=')


@tagged('post_install', '-at_install')
class TestFePyLicencia(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not CRYPTO:
            raise unittest.SkipTest("falta la librería cryptography")
        # Par de claves EXCLUSIVO de las pruebas.
        cls.privada_test = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        cls.pem_test = cls.privada_test.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo)
        cls.company = cls.env.company
        cls.uuid_base = cls.env['ir.config_parameter'].sudo().get_param('database.uuid')

    def setUp(self):
        super().setUp()
        # Sustituir la clave pública del módulo por la de prueba.
        self._pem_original = lic.FE_PY_CLAVE_PUBLICA_PEM
        lic.FE_PY_CLAVE_PUBLICA_PEM = self.pem_test
        lic._fe_py_clave_publica_cache = None
        self.addCleanup(self._restaurar_clave)

    def _restaurar_clave(self):
        lic.FE_PY_CLAVE_PUBLICA_PEM = self._pem_original
        lic._fe_py_clave_publica_cache = None

    # -- utilidades ------------------------------------------------------
    def _firmar(self, producto=None, uuid=None, cliente="Cliente de Prueba",
                vence=None, version=None):
        payload = {
            'p': lic.FE_PY_LICENCIA_PRODUCTO if producto is None else producto,
            'u': self.uuid_base if uuid is None else uuid,
            'c': cliente,
            'v': (vence or (date.today() + timedelta(days=30))).isoformat()
            if not isinstance(vence, str) else vence,
            'm': lic.fe_py_version_odoo_instalada() if version is None else version,
        }
        datos = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        firma = self.privada_test.sign(
            datos,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256())
        return "%s.%s.%s" % (lic.FE_PY_LICENCIA_PREFIJO, _b64(datos), _b64(firma))

    def _forzado(self, modelo):
        return self.env[modelo].with_context(fe_py_licencia_forzar_test=True)

    # -- 1. criptografía -------------------------------------------------
    def test_01_codigo_valido_se_decodifica(self):
        datos = lic.fe_py_decodificar_licencia(self._firmar())
        self.assertEqual(datos['uuid'], self.uuid_base)
        self.assertEqual(datos['cliente'], "Cliente de Prueba")
        self.assertEqual(datos['version_odoo'], lic.fe_py_version_odoo_instalada())

    def test_02_codigos_rechazados(self):
        for etiqueta, codigo in [
            ("vacío", ""),
            ("prefijo ajeno", "OTRO1.aaa.bbb"),
            ("partes insuficientes", "FC_PY1.aaa"),
            ("base64 inválido", "FC_PY1.!!!.###"),
        ]:
            with self.subTest(etiqueta):
                with self.assertRaises(ValueError):
                    lic.fe_py_decodificar_licencia(codigo)

    def test_03_firma_alterada_se_rechaza(self):
        codigo = self._firmar()
        prefijo, datos, firma = codigo.split('.')
        alterada = firma[:-4] + ('AAAA' if firma[-4:] != 'AAAA' else 'BBBB')
        with self.assertRaises(ValueError):
            lic.fe_py_decodificar_licencia('%s.%s.%s' % (prefijo, datos, alterada))

    def test_04_codigo_de_otro_producto_no_sirve(self):
        """Un código emitido para local_py no activa FE_Py, aunque esté firmado
        con la misma clave: es lo que mantiene las licencias independientes."""
        with self.assertRaises(ValueError):
            lic.fe_py_decodificar_licencia(self._firmar(producto='local_py'))

    # -- 2. estados de la compañía ---------------------------------------
    def test_10_estado_sin_licencia(self):
        self.company.fe_py_licencia_codigo = False
        self.assertEqual(self.company.fe_py_licencia_estado, 'sin_licencia')
        self.assertFalse(self.company._fe_py_licencia_valida())

    def test_11_estado_valida(self):
        self.company.fe_py_licencia_codigo = self._firmar()
        self.assertEqual(self.company.fe_py_licencia_estado, 'valida')
        self.assertEqual(self.company.fe_py_licencia_cliente, "Cliente de Prueba")
        self.assertTrue(self.company._fe_py_licencia_valida())

    def test_12_estado_vencida(self):
        self.company.fe_py_licencia_codigo = self._firmar(
            vence=date.today() - timedelta(days=1))
        self.assertEqual(self.company.fe_py_licencia_estado, 'vencida')

    def test_13_estado_invalida_por_otra_base(self):
        self.company.fe_py_licencia_codigo = self._firmar(uuid='otra-base-de-datos')
        self.assertEqual(self.company.fe_py_licencia_estado, 'invalida')

    def test_14_estado_invalida_por_codigo_roto(self):
        self.company.fe_py_licencia_codigo = "FC_PY1.roto.roto"
        self.assertEqual(self.company.fe_py_licencia_estado, 'invalida')

    def test_15_estado_otra_version(self):
        version_actual = lic.fe_py_version_odoo_instalada()
        self.company.fe_py_licencia_codigo = self._firmar(
            version=(version_actual or 0) + 1)
        self.assertEqual(self.company.fe_py_licencia_estado, 'otra_version')

    def test_16_codigo_de_la_base_trae_version_y_uuid(self):
        valor = self.company.fe_py_licencia_uuid
        self.assertIn('|', valor)
        version, uuid = valor.split('|', 1)
        self.assertEqual(uuid, self.uuid_base)
        self.assertEqual(version, str(lic.fe_py_version_odoo_instalada()))

    # -- 3. version del manifest, verificada de forma INDEPENDIENTE -------
    def test_20_version_odoo_instalada_contra_el_manifest(self):
        """No usa `fe_py_version_odoo_instalada` para construir el esperado: lee
        el manifest del módulo directamente del disco con `ast.literal_eval`.
        En Taller, un bug sistemático en esa función (devolvía 0 en vez de 19)
        pasó inadvertido porque la prueba la comparaba contra sí misma."""
        ruta = pathlib.Path(__file__).resolve().parent.parent / '__manifest__.py'
        texto = ruta.read_text(encoding='utf-8')
        manifest = ast.literal_eval(texto[texto.index('{'):texto.rindex('}') + 1])
        version_declarada = str(manifest['version'])
        esperado = int(version_declarada.split('.')[1])
        self.assertEqual(lic.fe_py_version_odoo_instalada(), esperado)
        self.assertGreater(esperado, 0, "el número central no puede ser 0")

    # -- 4. bloqueos ------------------------------------------------------
    def test_30_sin_licencia_bloquea_crear_catalogo(self):
        self.company.fe_py_licencia_codigo = False
        with self.assertRaises(UserError):
            self._forzado('fe_py.tipo_operacion').create({
                'codigo': 'ZZ', 'name': 'Prueba sin licencia'})

    def test_31_con_licencia_permite_crear_catalogo(self):
        self.company.fe_py_licencia_codigo = self._firmar()
        registro = self._forzado('fe_py.tipo_operacion').create({
            'codigo': 'ZY', 'name': 'Prueba con licencia'})
        self.assertTrue(registro.id)

    def test_32_catalogo_ya_creado_se_puede_seguir_editando(self):
        """Una licencia vencida no debe impedir corregir un dato ya cargado."""
        self.company.fe_py_licencia_codigo = self._firmar()
        registro = self._forzado('fe_py.tipo_operacion').create({
            'codigo': 'ZX', 'name': 'Creado con licencia'})
        self.company.fe_py_licencia_codigo = False
        registro.with_context(fe_py_licencia_forzar_test=True).write(
            {'name': 'Corregido sin licencia'})
        self.assertEqual(registro.name, 'Corregido sin licencia')

    def test_33_sin_licencia_bloquea_editar_configuracion(self):
        self.company.fe_py_licencia_codigo = False
        config = self.env['fe_py.configuracion'].sudo().search(
            [('company_id', '=', self.company.id)], limit=1)
        if not config:
            self.skipTest("la compañía no tiene Configuración FEPy")
        with self.assertRaises(UserError):
            config.with_context(fe_py_licencia_forzar_test=True).write(
                {'timeout': 45})

    # -- 5. exenciones ----------------------------------------------------
    def test_40_sin_forzar_el_control_no_actua_en_pruebas(self):
        """Sin el contexto de forzado, el resto de la suite del módulo puede
        crear registros sin simular una licencia."""
        self.company.fe_py_licencia_codigo = False
        registro = self.env['fe_py.tipo_operacion'].create({
            'codigo': 'ZW', 'name': 'Sin forzar el control'})
        self.assertTrue(registro.id)

    def test_41_interruptor_de_build_de_partner(self):
        """Con FE_PY_LICENCIA_OBLIGATORIA en False el control queda desactivado
        por completo, incluso forzándolo."""
        self.company.fe_py_licencia_codigo = False
        original = lic.FE_PY_LICENCIA_OBLIGATORIA
        lic.FE_PY_LICENCIA_OBLIGATORIA = False
        try:
            registro = self._forzado('fe_py.tipo_operacion').create({
                'codigo': 'ZV', 'name': 'Build de partner'})
            self.assertTrue(registro.id)
            self.assertTrue(lic.fe_py_licencia_vigente(self.env, self.company))
        finally:
            lic.FE_PY_LICENCIA_OBLIGATORIA = original

    def test_42_build_normal_tiene_el_control_activo(self):
        """Resguardo: que no se entregue por error un ZIP con el interruptor de
        partner apagado."""
        self.assertTrue(lic.FE_PY_LICENCIA_OBLIGATORIA)
