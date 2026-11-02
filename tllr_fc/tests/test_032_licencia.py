# -*- coding: utf-8 -*-
"""2026.19.032: licencia OPL-1 y control de licencia atada a la base de datos."""
import base64
import json
from datetime import date, timedelta

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.tllr_fc.models import tllr_fc_licencia as _tllr_fc_licencia_mod
from odoo.addons.tllr_fc.models.tllr_fc_licencia import (
    tllr_fc_decodificar_licencia, tllr_fc_licencia_exenta)

from .common import TallerCommon


def _firmar(clave_privada, uuid_, cliente, vence, producto="tllr_fc"):
    """Genera un código de licencia como lo haría el script de FC_Py, pero firmado
    con una clave de prueba (no la clave privada real del módulo)."""
    payload = {"p": producto, "u": uuid_, "c": cliente, "v": vence}
    datos = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    firma = clave_privada.sign(
        datos,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256())
    b64 = lambda data: base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")
    return "TLLRFC1.%s.%s" % (b64(datos), b64(firma))


@tagged('post_install', '-at_install')
class Test032Licencia(TallerCommon):
    """Criptografía de la licencia (clave de prueba) y bloqueo de creación/edición
    (clave real del módulo, forzando el control dentro de las pruebas)."""

    parchear_cierre = False

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Clave de prueba propia: nunca es la clave pública embebida en el módulo,
        # así que estas licencias firmadas con ella deben darse siempre por inválidas.
        cls.clave_prueba = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.uuid_base = cls.env['res.company']._tllr_fc_licencia_uuid_actual()

    # -- Criptografía: con una clave que NO es la del módulo, nunca valida --------

    def test_01_codigo_firmado_con_otra_clave_no_valida(self):
        codigo = _firmar(self.clave_prueba, self.uuid_base, "Cliente X", "2099-01-01")
        with self.assertRaisesRegex(ValueError, "firma"):
            tllr_fc_decodificar_licencia(codigo)

    def test_02_codigo_vacio_o_con_formato_incorrecto(self):
        for malo in ("", "   ", "cualquier-cosa", "TLLRFC1.solo-dos-partes"):
            with self.assertRaises(ValueError):
                tllr_fc_decodificar_licencia(malo)

    def test_03_estado_de_la_compania_sin_codigo(self):
        self.env.company.tllr_fc_licencia_codigo = False
        self.assertEqual(self.env.company.tllr_fc_licencia_estado, 'sin_licencia')
        self.assertFalse(self.env.company._tllr_fc_licencia_valida())

    def test_04_estado_de_la_compania_con_codigo_de_otra_clave(self):
        codigo = _firmar(self.clave_prueba, self.uuid_base, "Cliente X", "2099-01-01")
        self.env.company.tllr_fc_licencia_codigo = codigo
        self.assertEqual(self.env.company.tllr_fc_licencia_estado, 'invalida')
        self.assertFalse(self.env.company._tllr_fc_licencia_valida())

    # -- Bloqueo de creación y edición: se fuerza el control dentro de la prueba --

    def _forzar(self):
        return self.env.companies.with_context(tllr_fc_licencia_forzar_test=True)

    def test_05_sin_licencia_no_se_puede_crear(self):
        self.env.company.tllr_fc_licencia_codigo = False
        with self.assertRaises(UserError):
            self._forzar().env['tllr_fc.marca'].create({'name': "Marca sin licencia"})

    def test_06_licencia_de_otra_base_no_sirve(self):
        codigo = _firmar(self.clave_prueba, "otra-base-distinta", "Cliente X", "2099-01-01")
        self.env.company.with_context(tllr_fc_licencia_forzar_test=True).write({
            'tllr_fc_licencia_codigo': codigo})
        with self.assertRaises(UserError):
            self._forzar().env['tllr_fc.marca'].create({'name': "Marca de otra base"})

    def test_07_sin_control_forzado_la_creacion_no_se_bloquea(self):
        # Fuera de `tllr_fc_licencia_forzar_test`, las pruebas quedan exentas
        # (así las otras ~300 pruebas del módulo no necesitan simular una licencia).
        self.env.company.tllr_fc_licencia_codigo = False
        marca = self.env['tllr_fc.marca'].create({'name': "Marca sin forzar control"})
        self.assertTrue(marca.id)

    def test_08_edicion_de_ot_en_curso_tambien_se_bloquea(self):
        self.env.company.tllr_fc_licencia_codigo = False
        ot = self._ot_planificada()
        with self.assertRaises(UserError):
            ot.with_context(tllr_fc_licencia_forzar_test=True).descripcion_trabajos = "x"

    def test_09_edicion_de_un_maestro_no_se_bloquea_aunque_la_creacion_si(self):
        # Decisión de alcance: el control de edición (write) solo se aplica a los
        # documentos de trabajo en curso (OT, recepción, entrega, control de
        # calidad, turno), no a los maestros (marca, vehículo, personal...): una
        # licencia vencida no debería impedir corregir un dato ya cargado.
        marca = self.env['tllr_fc.marca'].create({'name': "Marca ya creada"})
        self.env.company.tllr_fc_licencia_codigo = False
        marca.with_context(tllr_fc_licencia_forzar_test=True).name = "Marca corregida"
        self.assertEqual(marca.name, "Marca corregida")

    # -- Interruptor de build de partner (2026.19.033) --------------------------

    def test_10_build_de_partner_sin_control_de_licencia(self):
        # El ZIP que se entrega a un partner con reventa ilimitada cambia esta
        # constante a False al armarse: el control queda enteramente a cargo del
        # contrato, no de la base de datos de cada cliente del partner.
        self.env.company.tllr_fc_licencia_codigo = False
        original = _tllr_fc_licencia_mod.TLLR_FC_LICENCIA_OBLIGATORIA
        _tllr_fc_licencia_mod.TLLR_FC_LICENCIA_OBLIGATORIA = False
        try:
            self.assertTrue(tllr_fc_licencia_exenta(self.env))
            marca = self._forzar().env['tllr_fc.marca'].create(
                {'name': "Marca en build de partner"})
            self.assertTrue(marca.id)
        finally:
            _tllr_fc_licencia_mod.TLLR_FC_LICENCIA_OBLIGATORIA = original
