# -*- coding: utf-8 -*-
"""Pruebas de las funciones puras de la 2026.19.008: ZIP, correos sin XML, remitente y tolerancia.
Se ejecutan sin Odoo:   python3 -m unittest tests/test_adjuntos_remitente.py"""
import importlib.util
import io
import os
import unittest
import zipfile
from email.message import EmailMessage

AQUI = os.path.dirname(os.path.abspath(__file__))
MODELOS = os.path.join(os.path.dirname(AQUI), 'models')


def _cargar(nombre):
    spec = importlib.util.spec_from_file_location(nombre, os.path.join(MODELOS, nombre + '.py'))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


util = _cargar('utilidades')


def _zip(archivos):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:
        for nombre, contenido in archivos.items():
            z.writestr(nombre, contenido)
    return buffer.getvalue()


class TestAdjuntos(unittest.TestCase):
    def test_xml_y_pdf_sueltos(self):
        r = util.expandir_adjuntos([('a.XML', '<a/>'), ('a.pdf', b'%PDF')])
        self.assertEqual(r['xmls'], [('a.XML', b'<a/>')])
        self.assertEqual(len(r['pdfs']), 1)

    def test_zip_con_xml_y_carpeta(self):
        z = _zip({'facturas/f1.xml': '<f/>', 'facturas/f1.pdf': 'pdf', 'leeme.txt': 'x'})
        r = util.expandir_adjuntos([('envio.zip', z)])
        self.assertEqual([n for n, _c in r['xmls']], ['f1.xml'])
        self.assertEqual([n for n, _c in r['pdfs']], ['f1.pdf'])

    def test_zip_sin_xml(self):
        r = util.expandir_adjuntos([('envio.zip', _zip({'leeme.txt': 'x'}))])
        self.assertFalse(r['xmls'])
        self.assertEqual(util.motivo_sin_xml(r), 'El correo no trae archivos XML.')

    def test_zip_danado(self):
        r = util.expandir_adjuntos([('roto.zip', b'esto no es un zip')])
        self.assertEqual(r['zip_danados'], ['roto.zip'])
        self.assertIn('dañado', util.motivo_sin_xml(r))

    def test_rar_no_soportado(self):
        r = util.expandir_adjuntos([('envio.RAR', b'Rar!')])
        self.assertEqual(r['no_soportados'], ['RAR'])
        self.assertIn('RAR', util.motivo_sin_xml(r))

    def test_sin_adjuntos(self):
        self.assertEqual(util.motivo_sin_xml(util.expandir_adjuntos([])), 'El correo no trae adjuntos.')

    def test_zip_con_archivo_demasiado_grande_se_omite(self):
        anterior = util.MAX_BYTES_MIEMBRO
        util.MAX_BYTES_MIEMBRO = 10
        try:
            r = util.expandir_adjuntos([('g.zip', _zip({'grande.xml': 'x' * 100}))])
        finally:
            util.MAX_BYTES_MIEMBRO = anterior
        self.assertFalse(r['xmls'])
        self.assertTrue(r['zip_omitidos'])
        self.assertIn('límites', util.motivo_sin_xml(r))

    def test_zip_con_demasiados_archivos(self):
        anterior = util.MAX_MIEMBROS_ZIP
        util.MAX_MIEMBROS_ZIP = 2
        try:
            archivos = {'f%d.xml' % i: '<f/>' for i in range(5)}
            r = util.expandir_adjuntos([('m.zip', _zip(archivos))])
        finally:
            util.MAX_MIEMBROS_ZIP = anterior
        self.assertEqual(len(r['xmls']), 2)
        self.assertTrue(r['zip_omitidos'])

    def test_zip_dentro_de_zip_no_se_abre(self):
        interno = _zip({'f.xml': '<f/>'})
        r = util.expandir_adjuntos([('externo.zip', _zip({'interno.zip': interno}))])
        self.assertFalse(r['xmls'])


class TestCorreoCrudo(unittest.TestCase):
    def _correo(self, adjuntos):
        mensaje = EmailMessage()
        mensaje['From'] = 'a@b.com'
        mensaje['To'] = 'c@d.com'
        mensaje['Subject'] = 'Factura'
        mensaje.set_content('hola')
        for nombre, contenido, tipo in adjuntos:
            mensaje.add_attachment(contenido, maintype='application', subtype=tipo, filename=nombre)
        return mensaje.as_bytes()

    def test_con_xml(self):
        self.assertTrue(util.correo_trae_xml(self._correo([('f.xml', b'<f/>', 'xml')])))

    def test_con_xml_en_zip(self):
        self.assertTrue(util.correo_trae_xml(self._correo([('f.zip', _zip({'f.xml': '<f/>'}), 'zip')])))

    def test_sin_xml(self):
        self.assertFalse(util.correo_trae_xml(self._correo([('f.pdf', b'%PDF', 'pdf')])))

    def test_sin_adjuntos(self):
        self.assertFalse(util.correo_trae_xml(self._correo([])))


class TestRemitente(unittest.TestCase):
    def test_direccion_exacta(self):
        self.assertTrue(util.remitente_coincide('Ventas <ventas@prov.com.py>', ['ventas@prov.com.py'])[0])

    def test_mismo_dominio_de_empresa(self):
        self.assertTrue(util.remitente_coincide('facturas@prov.com.py', ['gerencia@prov.com.py'])[0])

    def test_subdominio(self):
        self.assertTrue(util.remitente_coincide('x@fe.prov.com.py', ['gerencia@prov.com.py'])[0])

    def test_dominio_distinto(self):
        coincide, motivo = util.remitente_coincide('x@otra.com.py', ['gerencia@prov.com.py'])
        self.assertFalse(coincide)
        self.assertIn('no coincide', motivo)

    def test_dominio_publico_exige_direccion_exacta(self):
        self.assertFalse(util.remitente_coincide('otro@gmail.com', ['prov@gmail.com'])[0])
        self.assertTrue(util.remitente_coincide('prov@gmail.com', ['prov@gmail.com'])[0])

    def test_dominio_parecido_no_coincide(self):
        self.assertFalse(util.remitente_coincide('x@malprov.com.py', ['g@prov.com.py'])[0])

    def test_proveedor_sin_correo(self):
        coincide, motivo = util.remitente_coincide('x@prov.com.py', [False, ''])
        self.assertFalse(coincide)
        self.assertIn('ficha', motivo)

    def test_varios_correos_en_la_ficha(self):
        self.assertTrue(util.remitente_coincide('b@z.com.py', ['a@y.com; b@z.com.py'])[0])

    def test_remitente_vacio(self):
        self.assertFalse(util.remitente_coincide('', ['a@b.com'])[0])


class TestTolerancia(unittest.TestCase):
    def test_dentro(self):
        self.assertTrue(util.dentro_de_tolerancia(1, 1))
        self.assertTrue(util.dentro_de_tolerancia(-0.5, 1))

    def test_fuera(self):
        self.assertFalse(util.dentro_de_tolerancia(1.01, 1))

    def test_cero_exige_igualdad(self):
        self.assertTrue(util.dentro_de_tolerancia(0.0, 0))
        self.assertFalse(util.dentro_de_tolerancia(0.01, 0))


if __name__ == '__main__':
    unittest.main()
