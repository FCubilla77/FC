# -*- coding: utf-8 -*-
"""Pruebas de la cotización del XML.   python3 tests/test_cotizacion.py"""
import importlib.util
import os
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    'utilidades', os.path.join(os.path.dirname(AQUI), 'models', 'utilidades.py'))
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)


class TestCotizacion(unittest.TestCase):
    def test_tasa_desde_xml(self):
        self.assertAlmostEqual(u.tasa_odoo_desde_xml(7446.55), 1 / 7446.55)
        self.assertAlmostEqual(u.tasa_odoo_desde_xml('7300.0000'), 1 / 7300)

    def test_sin_tipo_de_cambio(self):
        for vacio in (None, 0, 0.0, '', '0', -5, 'abc'):
            self.assertIsNone(u.tasa_odoo_desde_xml(vacio))

    def test_ida_y_vuelta_del_ejemplo(self):
        # 122,30 USD a 7446,55: 910713,065 Gs; el redondeo del sistema decide el ±1
        tasa = u.tasa_odoo_desde_xml(7446.55)
        self.assertAlmostEqual(122.30 / tasa, 910713.065, places=3)

    def test_difieren(self):
        self.assertFalse(u.cotizaciones_difieren(1 / 7300, 1 / 7300))
        self.assertFalse(u.cotizaciones_difieren(1 / 7300, 1 / 7300.0001))
        self.assertTrue(u.cotizaciones_difieren(1 / 7300, 1 / 7450))
        self.assertFalse(u.cotizaciones_difieren(None, 1 / 7450))


if __name__ == '__main__':
    unittest.main()
