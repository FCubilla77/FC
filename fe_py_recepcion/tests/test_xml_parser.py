# -*- coding: utf-8 -*-
"""Pruebas del parser y de las funciones puras, sin necesidad de Odoo.

Se ejecutan con:   python3 -m unittest tests/test_xml_parser.py   (desde la
carpeta del módulo) o con el test runner de Odoo. Los XML de tests/xml son
ficticios (ver generar_muestras.py).
"""

import importlib.util
import os
import unittest
from datetime import date
from decimal import Decimal as D

AQUI = os.path.dirname(os.path.abspath(__file__))
MODELOS = os.path.join(os.path.dirname(AQUI), 'models')


def _cargar(nombre):
    """Importa un módulo puro por ruta, sin pasar por el paquete de Odoo."""
    spec = importlib.util.spec_from_file_location(nombre, os.path.join(MODELOS, nombre + '.py'))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


xp = _cargar('xml_parser')
util = _cargar('utilidades')


def leer(nombre):
    with open(os.path.join(AQUI, 'xml', nombre), 'rb') as archivo:
        return xp.parsear(archivo.read())


class TestParser(unittest.TestCase):

    def test_factura_suelta_con_descuento(self):
        d = leer('muestra_a_factura_iva5_descuento.xml')
        self.assertEqual(d['itide'], 1)
        self.assertEqual(len(d['cdc']), 44)
        self.assertEqual(d['nro_documento'], '001-002-0007105')
        self.assertEqual(d['timbrado'], '12345001')
        self.assertEqual(d['fecha_emision'], date(2026, 11, 3))
        self.assertEqual(d['moneda'], 'PYG')
        self.assertEqual(d['condicion'], 1)
        self.assertEqual(d['totales']['total_general'], D('21000'))
        self.assertEqual(d['totales']['iva'], D('1000'))
        linea = d['items'][0]
        self.assertEqual(linea['codigo'], '1001')
        self.assertEqual(linea['precio'], D('26250'))
        self.assertEqual(linea['descuento_pct'], D('20'))
        self.assertEqual(linea['total'], D('21000'))
        self.assertEqual(linea['tasa'], 5)
        self.assertEqual(linea['afectacion'], '1')
        self.assertEqual(linea['lote'], '173')

    def test_sobre_soap_nodos_vacios_y_numeros_largos(self):
        d = leer('muestra_b_factura_iva10_soap.xml')
        self.assertEqual(d['nro_documento'], '001-002-0000464')
        self.assertEqual(d['totales']['total_general'], D('550000'))
        self.assertEqual(d['totales']['iva'], D('50000'))
        self.assertEqual(d['items'][0]['tasa'], 10)
        # el RUC trae un cero a la izquierda: se normaliza
        self.assertEqual(d['emisor']['ruc'], '8000030')
        self.assertEqual(d['emisor']['ruc_dv'], '8000030-4')
        # nodo de pago con descripción vacía
        self.assertEqual(d['pagos'][0]['descripcion'], '')

    def test_usd_credito_por_plazo(self):
        d = leer('sintetica_usd_credito_plazo.xml')
        self.assertEqual(d['moneda'], 'USD')
        self.assertEqual(d['tipo_cambio'], D('7300'))
        self.assertEqual(d['condicion'], 2)
        self.assertEqual(d['credito']['tipo'], 1)
        self.assertEqual(util.dias_de_plazo(d['credito']['plazo']), 30)
        self.assertEqual(d['totales']['total_general'], D('250'))
        self.assertEqual(d['totales']['total_gs'], D('1825000'))

    def test_credito_por_cuotas_y_tasas_mixtas(self):
        d = leer('sintetica_credito_cuotas_mixta.xml')
        self.assertEqual([i['tasa'] for i in d['items']], [10, 5, 0])
        self.assertEqual([i['afectacion'] for i in d['items']], ['1', '1', '3'])
        self.assertEqual(d['credito']['tipo'], 2)
        self.assertEqual(len(d['credito']['cuotas']), 3)
        perfil = util.perfil_xml(d['condicion'], d['credito']['plazo'], d['credito']['cuotas'],
                                 d['fecha_emision'])
        self.assertEqual(perfil, [30, 60, 90])

    def test_nota_de_credito_con_asociado_electronico(self):
        d = leer('sintetica_nota_credito.xml')
        self.assertEqual(d['itide'], 5)
        self.assertEqual(d['motivo_codigo'], 2)
        self.assertEqual(len(d['asociados']), 1)
        self.assertEqual(d['asociados'][0]['tipo'], 1)
        asociado = leer('muestra_a_factura_iva5_descuento.xml')
        self.assertEqual(d['asociados'][0]['cdc'], asociado['cdc'])
        partes = xp.componentes_cdc(d['asociados'][0]['cdc'])
        self.assertEqual((partes['establecimiento'], partes['punto'], partes['numero']),
                         ('001', '002', '0007105'))

    def test_nota_de_debito_con_asociado_impreso(self):
        d = leer('sintetica_nota_debito_impresa.xml')
        self.assertEqual(d['itide'], 6)
        asociado = d['asociados'][0]
        self.assertEqual(asociado['tipo'], 2)
        self.assertEqual((asociado['timbrado'], asociado['establecimiento'], asociado['punto'],
                          asociado['numero']), ('11111111', '001', '001', '0000999'))
        self.assertEqual(asociado['fecha'], date(2025, 12, 1))

    def test_rechazos(self):
        for archivo, texto in (('invalida_remision.xml', 'no soportado'),
                               ('invalida_dtd.xml', 'DTD'),
                               ('invalida_no_es_de.xml', 'rDE')):
            with self.assertRaises(xp.XmlRecepcionError) as ctx:
                leer(archivo)
            self.assertIn(texto, str(ctx.exception))
        for malo in (b'', b'   ', b'<a><b></a>', b'no es xml'):
            with self.assertRaises(xp.XmlRecepcionError):
                xp.parsear(malo)

    def test_normalizar_ruc(self):
        self.assertEqual(xp.normalizar_ruc('08000030', '4'), ('8000030', '4'))
        self.assertEqual(xp.normalizar_vat('8000030-4'), ('8000030', '4'))
        self.assertEqual(xp.normalizar_vat('08000030'), ('8000030', ''))
        self.assertEqual(xp.normalizar_vat(''), ('', ''))
        self.assertEqual(xp.formatear_ruc('8000030', '4'), '8000030-4')


class TestPrecioDescuento(unittest.TestCase):

    def test_sin_descuento(self):
        self.assertEqual(util.calcular_precio_descuento(D('550000'), D(1), D('550000')),
                         (D('550000'), D(0)))

    def test_descuento_exacto_del_xml(self):
        precio, pct = util.calcular_precio_descuento(D('26250'), D(1), D('21000'), D('20'))
        self.assertEqual((precio, pct), (D('26250'), D('20.00')))

    def test_descuento_derivado_si_el_xml_no_trae_porcentaje(self):
        precio, pct = util.calcular_precio_descuento(D('26250'), D(1), D('21000'), None)
        self.assertEqual((precio, pct), (D('26250'), D('20.00')))

    def test_descuento_que_odoo_no_puede_reproducir_usa_precio_neto(self):
        precio, pct = util.calcular_precio_descuento(D('99999'), D(1), D('91234'), D('8.77'))
        self.assertEqual(pct, D(0))
        self.assertEqual(precio, D('91234'))

    def test_el_total_resultante_coincide_con_el_xml(self):
        casos = [(D('26250'), D(1), D('21000')), (D('3333'), D(3), D('9222')),
                 (D('99999'), D(1), D('91234')), (D('1000'), D(7), D('6001'))]
        for precio, cantidad, total in casos:
            p, pct = util.calcular_precio_descuento(precio, cantidad, total, None)
            self.assertLessEqual(abs(p * cantidad * (1 - pct / 100) - total), D('0.5'))

    def test_cantidad_o_precio_cero(self):
        self.assertEqual(util.calcular_precio_descuento(D(0), D(1), D(0)), (D(0), D(0)))
        self.assertEqual(util.calcular_precio_descuento(D(10), D(0), D(0)), (D(10), D(0)))


class TestTerminoPago(unittest.TestCase):
    TERMINOS = [
        (1, [0]),            # pago inmediato
        (2, [15]),
        (3, [30]),
        (4, [45]),
        (5, [30, 60]),
        (6, [30, 60, 90]),
        (7, [30, 60, 90, 120]),
    ]

    def test_contado(self):
        self.assertEqual(util.elegir_termino([0], self.TERMINOS), 1)

    def test_contado_sin_termino_inmediato(self):
        self.assertIsNone(util.elegir_termino([0], [(2, [15]), (3, [30])]))

    def test_plazo_exacto_y_aproximado(self):
        self.assertEqual(util.elegir_termino([30], self.TERMINOS), 3)
        self.assertEqual(util.elegir_termino([28], self.TERMINOS), 3)
        self.assertEqual(util.elegir_termino([40], self.TERMINOS), 4)
        self.assertEqual(util.elegir_termino([200], self.TERMINOS), 4)

    def test_plazo_nunca_elige_el_inmediato(self):
        self.assertEqual(util.elegir_termino([5], self.TERMINOS), 2)
        self.assertIsNone(util.elegir_termino([5], [(1, [0])]))

    def test_cuotas_misma_cantidad(self):
        self.assertEqual(util.elegir_termino([30, 60, 90], self.TERMINOS), 6)
        self.assertEqual(util.elegir_termino([30, 60], self.TERMINOS), 5)

    def test_cuotas_sin_misma_cantidad_elige_la_menor_mayor(self):
        self.assertEqual(util.elegir_termino([30, 60, 90, 120, 150],
                                             self.TERMINOS + [(8, [30, 60, 90, 120, 150, 180])]), 8)
        self.assertIsNone(util.elegir_termino([1, 2, 3, 4, 5, 6, 7, 8], self.TERMINOS))

    def test_cuotas_sin_fechas_toma_la_primera_de_la_cantidad(self):
        self.assertEqual(util.elegir_termino([None, None, None], self.TERMINOS), 6)

    def test_credito_sin_datos(self):
        self.assertIsNone(util.elegir_termino([], self.TERMINOS))

    def test_dias_de_plazo(self):
        self.assertEqual(util.dias_de_plazo('30 días'), 30)
        self.assertEqual(util.dias_de_plazo('28'), 28)
        self.assertEqual(util.dias_de_plazo('12 meses'), 360)
        self.assertIsNone(util.dias_de_plazo(''))
        self.assertIsNone(util.dias_de_plazo('contado'))

    def test_descripcion(self):
        self.assertEqual(util.describir_perfil([0]), 'contado')
        self.assertEqual(util.describir_perfil([30]), 'a 30 días')
        self.assertEqual(util.describir_perfil([30, 60, 90]), '3 cuotas (30/60/90 días)')


class TestUnidades(unittest.TestCase):

    def test_misma_familia_no_avisa(self):
        self.assertFalse(util.unidades_distintas('UNI', 'Units'))
        self.assertFalse(util.unidades_distintas('LT', 'L'))
        self.assertFalse(util.unidades_distintas('kg', 'kg'))

    def test_familias_distintas_avisan(self):
        self.assertTrue(util.unidades_distintas('UNI', 'kg'))
        self.assertTrue(util.unidades_distintas('LT', 'Units'))

    def test_si_no_se_conoce_no_avisa(self):
        self.assertFalse(util.unidades_distintas('ración', 'Units'))
        self.assertFalse(util.unidades_distintas('UNI', 'Caja x12'))
        self.assertFalse(util.unidades_distintas('', 'Units'))


class TestEquivalencias(unittest.TestCase):
    def test_normalizar_clave(self):
        self.assertEqual(util.normalizar_clave('  Cable   UTP  Cat6 '), 'cable utp cat6')
        self.assertEqual(util.normalizar_clave('ABC-01'), util.normalizar_clave(' abc-01'))
        self.assertEqual(util.normalizar_clave(None), '')
        self.assertEqual(util.normalizar_clave('   '), '')

    def test_mas_reciente_gana(self):
        filas = [(10, date(2026, 1, 5), 1), (20, date(2026, 3, 1), 2), (30, date(2026, 2, 1), 3)]
        self.assertEqual(util.elegir_mas_reciente(filas), 20)

    def test_sin_fecha_pierde_y_empate_gana_el_id_mayor(self):
        self.assertEqual(util.elegir_mas_reciente([(10, None, 5), (20, date(2026, 1, 1), 1)]), 20)
        self.assertEqual(util.elegir_mas_reciente([(10, date(2026, 1, 1), 1), (20, date(2026, 1, 1), 2)]), 20)
        self.assertEqual(util.elegir_mas_reciente([(10, None, 1), (20, None, 2)]), 20)

    def test_sin_filas(self):
        self.assertIsNone(util.elegir_mas_reciente([]))

    def test_candidato_unico(self):
        self.assertEqual(util.elegir_unico(['a']), 'a')
        self.assertIsNone(util.elegir_unico([]))
        self.assertIsNone(util.elegir_unico(['a', 'b']))


if __name__ == '__main__':
    unittest.main()
