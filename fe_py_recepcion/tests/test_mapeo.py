# -*- coding: utf-8 -*-
"""Pruebas de la lógica pura del mapeo de campos.   python3 tests/test_mapeo.py"""
import importlib.util
import os
import unittest
from datetime import date

AQUI = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    'utilidades', os.path.join(os.path.dirname(AQUI), 'models', 'utilidades.py'))
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)


class TestMapeo(unittest.TestCase):
    def test_compatibilidad(self):
        self.assertTrue(u.tipos_compatibles('char', 'char'))
        self.assertTrue(u.tipos_compatibles('date', 'char'))
        self.assertTrue(u.tipos_compatibles('char', 'integer'))
        self.assertTrue(u.tipos_compatibles('char', 'many2one'))
        self.assertTrue(u.tipos_compatibles('many2one', 'many2one'))
        self.assertFalse(u.tipos_compatibles('boolean', 'integer'))
        self.assertFalse(u.tipos_compatibles('date', 'integer'))
        self.assertFalse(u.tipos_compatibles('char', 'boolean'))
        self.assertFalse(u.tipos_compatibles('char', 'one2many'))

    def test_texto(self):
        self.assertEqual(u.convertir_valor('abc', 'char'), (True, 'abc'))
        self.assertEqual(u.convertir_valor(15, 'char'), (True, '15'))
        self.assertEqual(u.convertir_valor(date(2026, 1, 5), 'char'), (True, '2026-01-05'))

    def test_vacios_no_se_copian(self):
        for vacio in (None, False, ''):
            self.assertEqual(u.convertir_valor(vacio, 'char'), (False, None))
            self.assertEqual(u.convertir_valor(vacio, 'integer'), (False, None))
        self.assertEqual(u.convertir_valor(False, 'boolean'), (True, False))

    def test_numeros(self):
        self.assertEqual(u.convertir_valor('12345678', 'integer'), (True, 12345678))
        self.assertEqual(u.convertir_valor('12,5', 'float'), (True, 12.5))
        self.assertEqual(u.convertir_valor(0, 'integer'), (True, 0))
        self.assertEqual(u.convertir_valor('abc', 'integer'), (False, None))
        self.assertEqual(u.convertir_valor('x1', 'float'), (False, None))

    def test_fechas(self):
        self.assertEqual(u.convertir_valor(date(2026, 3, 4), 'date'), (True, '2026-03-04'))
        self.assertEqual(u.convertir_valor('2026-03-04T10:00:00', 'date'), (True, '2026-03-04'))
        self.assertEqual(u.convertir_valor(date(2026, 3, 4), 'datetime'),
                         (True, '2026-03-04 00:00:00'))

    def test_reservados(self):
        self.assertIn('partner_id', u.CAMPOS_RESERVADOS['account.move'])
        self.assertIn('product_id', u.CAMPOS_RESERVADOS['account.move.line'])
        self.assertNotIn('ref', u.CAMPOS_RESERVADOS['account.move'])


if __name__ == '__main__':
    unittest.main()
