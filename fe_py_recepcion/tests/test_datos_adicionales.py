# -*- coding: utf-8 -*-
"""Pruebas de los datos adicionales que lee el parser (GTIN, lote, serie, tipo de contribuyente,
totales informados). Sin Odoo:   python3 tests/test_datos_adicionales.py"""

import importlib.util
import os
import re
import unittest
from datetime import date
from decimal import Decimal as D

AQUI = os.path.dirname(os.path.abspath(__file__))
MODELOS = os.path.join(os.path.dirname(AQUI), 'models')


def _cargar(nombre):
    spec = importlib.util.spec_from_file_location(nombre, os.path.join(MODELOS, nombre + '.py'))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


xp = _cargar('xml_parser')


def base():
    with open(os.path.join(AQUI, 'xml', 'muestra_a_factura_iva5_descuento.xml'), 'rb') as f:
        xml = f.read().decode('utf-8')
    # la muestra trae un lote; se quita para probar cada caso por separado
    return re.sub(r'<gRasMerc>.*?</gRasMerc>', '', xml)


def con_item(extra_item):
    """Inserta nodos al final del primer ítem."""
    return re.sub(r'(</gCamItem>)', extra_item + r'\1', base(), count=1).encode('utf-8')


class TestDatosAdicionales(unittest.TestCase):

    def test_item_sin_datos_extra(self):
        item = xp.parsear(base().encode('utf-8'))['items'][0]
        for clave in ('gtin', 'gtin_paquete', 'info_item', 'lote', 'serie'):
            self.assertEqual(item[clave], '')
        self.assertIsNone(item['vencimiento'])

    def test_gtin_info_y_rastro_en_el_item(self):
        xml = con_item('<dGtin>7891234567895</dGtin><dGtinPq>17891234567892</dGtinPq>'
                       '<dInfItem>serie ABC123</dInfItem>'
                       '<gRasMerc><dNumLote>L-77</dNumLote><dVencMerc>2027-03-31</dVencMerc>'
                       '<dNSerie>S-1</dNSerie></gRasMerc>')
        item = xp.parsear(xml)['items'][0]
        self.assertEqual(item['gtin'], '7891234567895')
        self.assertEqual(item['gtin_paquete'], '17891234567892')
        self.assertEqual(item['info_item'], 'serie ABC123')
        self.assertEqual(item['lote'], 'L-77')
        self.assertEqual(item['vencimiento'], date(2027, 3, 31))
        self.assertEqual(item['serie'], 'S-1')

    def test_rastro_dentro_de_grupo_especial(self):
        xml = con_item('<gCamEsp><gCamComEsp><gRasMerc><dNumLote>L-9</dNumLote>'
                       '</gRasMerc></gCamComEsp></gCamEsp>')
        self.assertEqual(xp.parsear(xml)['items'][0]['lote'], 'L-9')

    def test_lote_de_la_muestra_real(self):
        with open(os.path.join(AQUI, 'xml', 'muestra_a_factura_iva5_descuento.xml'), 'rb') as f:
            self.assertEqual(xp.parsear(f.read())['items'][0]['lote'], '173')

    def test_tipo_de_contribuyente(self):
        datos = xp.parsear(base().encode('utf-8'))
        self.assertEqual(datos['emisor']['tipo_contribuyente'], 1)
        xml = base().replace('<iTipCont>1</iTipCont>', '<iTipCont>2</iTipCont>')
        self.assertEqual(xp.parsear(xml.encode('utf-8'))['emisor']['tipo_contribuyente'], 2)

    def test_totales_informados(self):
        xml = base().replace('<dTotDesc>', '<dTotDescGlotem>12.5</dTotDescGlotem>'
                             '<dAnticipo>100</dAnticipo><dRedon>3</dRedon><dTotDesc>', 1)
        tot = xp.parsear(xml.encode('utf-8'))['totales']
        self.assertEqual(tot['descuento_global'], D('12.5'))
        self.assertEqual(tot['anticipo'], D(100))
        self.assertEqual(tot['redondeo'], D(3))

    def test_totales_sin_esos_nodos_quedan_en_cero(self):
        tot = xp.parsear(base().encode('utf-8'))['totales']
        self.assertEqual((tot['descuento_global'], tot['anticipo'], tot['redondeo']),
                         (D(0), D(0), D(0)))


if __name__ == '__main__':
    unittest.main()
