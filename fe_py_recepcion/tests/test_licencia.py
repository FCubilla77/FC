# -*- coding: utf-8 -*-
"""2026.19.002: licencia OPL-1 y control de licencia atado a la base de datos.

Pruebas de Odoo (se ejecutan con --test-enable). La criptografía se prueba con una
clave de prueba ajena a la del módulo (nunca la real); el bloqueo se prueba forzando
el control con el contexto `fe_py_recepcion_licencia_forzar_test`.
"""
import ast
import base64
import json
from datetime import date, timedelta
from unittest import mock, skipIf

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from odoo.exceptions import UserError
from odoo.modules import module as odoo_module
from odoo.tests import TransactionCase, tagged

from odoo.addons.fe_py_recepcion.models import fe_py_recepcion_licencia as licencia_mod
from odoo.addons.fe_py_recepcion.models.fe_py_recepcion_licencia import (
    fe_py_recepcion_decodificar_licencia, fe_py_recepcion_version_odoo_instalada)


def _firmar(clave_privada, uuid_, cliente, vence, producto="fe_py_recepcion", version_odoo=None):
    """Genera un código de licencia como lo haría el script de FC_Py, pero firmado con
    una clave de prueba (no la clave privada real del módulo)."""
    if version_odoo is None:
        version_odoo = fe_py_recepcion_version_odoo_instalada()
    payload = {"p": producto, "u": uuid_, "c": cliente, "v": vence, "m": version_odoo}
    datos = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    firma = clave_privada.sign(
        datos,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256())
    b64 = lambda data: base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")
    return "FC_PY1.%s.%s" % (b64(datos), b64(firma))


SALTAR_PARTNER = skipIf(
    not licencia_mod.FE_PY_RECEPCION_LICENCIA_OBLIGATORIA,
    "Build de partner: el control de licencia está desactivado por diseño.")


@tagged('post_install', '-at_install')
class TestLicencia(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.clave_prueba = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.company = cls.env.company
        cls.uuid_base = cls.env['res.company']._fe_py_recepcion_licencia_uuid_actual()
        cls.manana = (date.today() + timedelta(days=1)).isoformat()
        cls.ayer = (date.today() - timedelta(days=1)).isoformat()
        cls.partner = cls.env['res.partner'].create({'name': 'Proveedor de prueba'})
        cls.producto = cls.env['product.product'].create({'name': 'Producto de prueba'})

    def _mock_clave_publica(self):
        return mock.patch.object(
            licencia_mod, '_fe_py_recepcion_obtener_clave_publica',
            return_value=self.clave_prueba.public_key())

    def _activar(self, **kw):
        codigo = _firmar(self.clave_prueba, kw.pop('uuid_', self.uuid_base), "Cliente X",
                         kw.pop('vence', self.manana), **kw)
        self.company.fe_py_recepcion_licencia_codigo = codigo
        return codigo

    def _forzar(self):
        return self.env['fe_py_recepcion.documento'].with_context(
            fe_py_recepcion_licencia_forzar_test=True)

    def _vals_documento(self):
        return {'cdc': '1' * 44, 'itide': '1', 'company_id': self.company.id}

    # -- Criptografía ------------------------------------------------------------
    def test_01_firma_de_otra_clave_no_valida(self):
        codigo = _firmar(self.clave_prueba, self.uuid_base, "Cliente X", self.manana)
        with self.assertRaisesRegex(ValueError, "firma"):
            fe_py_recepcion_decodificar_licencia(codigo)

    def test_02_formato_incorrecto(self):
        for malo in ("", "   ", "cualquier-cosa", "FC_PY1.solo-dos-partes"):
            with self.assertRaises(ValueError):
                fe_py_recepcion_decodificar_licencia(malo)

    def test_03_sin_campo_de_version_no_valida(self):
        payload = {"p": "fe_py_recepcion", "u": self.uuid_base, "c": "X", "v": self.manana}
        datos = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        firma = self.clave_prueba.sign(
            datos, padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                               salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
        b64 = lambda data: base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")
        codigo = "FC_PY1.%s.%s" % (b64(datos), b64(firma))
        with self._mock_clave_publica():
            with self.assertRaisesRegex(ValueError, "contenido"):
                fe_py_recepcion_decodificar_licencia(codigo)

    def test_04_codigo_de_otro_producto(self):
        codigo = _firmar(self.clave_prueba, self.uuid_base, "X", self.manana, producto="local_py")
        with self._mock_clave_publica():
            with self.assertRaisesRegex(ValueError, "otro_producto"):
                fe_py_recepcion_decodificar_licencia(codigo)

    def test_05_codigo_valido_devuelve_sus_datos(self):
        codigo = _firmar(self.clave_prueba, self.uuid_base, "Cliente X", self.manana)
        with self._mock_clave_publica():
            datos = fe_py_recepcion_decodificar_licencia(codigo)
        self.assertEqual(datos['uuid'], self.uuid_base)
        self.assertEqual(datos['cliente'], "Cliente X")
        self.assertEqual(datos['vence'], self.manana)
        self.assertEqual(datos['version_odoo'], fe_py_recepcion_version_odoo_instalada())

    def test_06_version_instalada_contra_el_manifest(self):
        # Prueba independiente: lee el manifest directamente, sin usar la función que se
        # prueba para construir el valor esperado.
        ruta = odoo_module.get_module_path('fe_py_recepcion') + '/__manifest__.py'
        with open(ruta, encoding='utf-8') as archivo:
            manifest = ast.literal_eval(archivo.read())
        esperado = int(manifest['version'].split('.')[-2])
        self.assertEqual(esperado, 19)
        self.assertEqual(fe_py_recepcion_version_odoo_instalada(), esperado)

    # -- Estados de la compañía --------------------------------------------------
    def test_07_estado_sin_licencia(self):
        self.company.fe_py_recepcion_licencia_codigo = False
        self.assertEqual(self.company.fe_py_recepcion_licencia_estado, 'sin_licencia')
        self.assertFalse(self.company._fe_py_recepcion_licencia_valida())

    def test_08_estado_invalida_con_clave_ajena(self):
        self._activar()
        self.assertEqual(self.company.fe_py_recepcion_licencia_estado, 'invalida')

    def test_09_estados_con_clave_de_prueba(self):
        with self._mock_clave_publica():
            self._activar()
            self.assertEqual(self.company.fe_py_recepcion_licencia_estado, 'valida')
            self._activar(vence=self.ayer)
            self.assertEqual(self.company.fe_py_recepcion_licencia_estado, 'vencida')
            self._activar(version_odoo=fe_py_recepcion_version_odoo_instalada() + 1)
            self.assertEqual(self.company.fe_py_recepcion_licencia_estado, 'otra_version')
            self._activar(uuid_='otra-base')
            self.assertEqual(self.company.fe_py_recepcion_licencia_estado, 'invalida')

    def test_10_codigo_de_la_base_trae_version_y_uuid(self):
        valor = self.company.fe_py_recepcion_licencia_uuid
        version, _sep, uuid = valor.partition('|')
        self.assertEqual(int(version), fe_py_recepcion_version_odoo_instalada())
        self.assertEqual(uuid, self.uuid_base)

    # -- Bloqueos ----------------------------------------------------------------
    @SALTAR_PARTNER
    def test_11_sin_licencia_no_se_crea_una_recepcion(self):
        self.company.fe_py_recepcion_licencia_codigo = False
        with self.assertRaises(UserError):
            self._forzar().create(self._vals_documento())

    @SALTAR_PARTNER
    def test_12_sin_licencia_no_se_crea_una_equivalencia(self):
        self.company.fe_py_recepcion_licencia_codigo = False
        with self.assertRaises(UserError):
            self.env['fe_py_recepcion.equivalencia'].with_context(
                fe_py_recepcion_licencia_forzar_test=True).create({
                    'partner_id': self.partner.id, 'codigo': 'A1',
                    'producto_id': self.producto.id, 'company_id': self.company.id})

    @SALTAR_PARTNER
    def test_13_con_licencia_se_crea_y_sin_licencia_no_se_edita_la_recepcion(self):
        with self._mock_clave_publica():
            self._activar()
            doc = self._forzar().create(self._vals_documento())
            doc.write({'partner_id': self.partner.id})
            self.company.fe_py_recepcion_licencia_codigo = False
        with self.assertRaises(UserError):
            doc.with_context(fe_py_recepcion_licencia_forzar_test=True).write(
                {'partner_id': self.partner.id})

    @SALTAR_PARTNER
    def test_14_un_maestro_ya_creado_se_puede_editar_sin_licencia(self):
        with self._mock_clave_publica():
            self._activar()
            equivalencia = self.env['fe_py_recepcion.equivalencia'].with_context(
                fe_py_recepcion_licencia_forzar_test=True).create({
                    'partner_id': self.partner.id, 'codigo': 'A1',
                    'producto_id': self.producto.id, 'company_id': self.company.id})
            self.company.fe_py_recepcion_licencia_codigo = False
        equivalencia.with_context(fe_py_recepcion_licencia_forzar_test=True).write(
            {'descripcion': 'Corregido sin licencia'})
        self.assertEqual(equivalencia.descripcion, 'Corregido sin licencia')

    @SALTAR_PARTNER
    def test_15_el_regreso_a_cargado_no_se_bloquea(self):
        with self._mock_clave_publica():
            self._activar()
            doc = self._forzar().create(self._vals_documento())
            self.company.fe_py_recepcion_licencia_codigo = False
        doc.with_context(fe_py_recepcion_licencia_forzar_test=True,
                         fe_py_recepcion_licencia_omitir=True).write({'state': 'cargado'})

    def test_16_interruptor_de_partner(self):
        self.company.fe_py_recepcion_licencia_codigo = False
        with mock.patch.object(licencia_mod, 'FE_PY_RECEPCION_LICENCIA_OBLIGATORIA', False):
            doc = self._forzar().create(self._vals_documento())
        self.assertTrue(doc)
