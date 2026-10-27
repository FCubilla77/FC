# -*- coding: utf-8 -*-
from datetime import date

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import TallerCommon


@tagged('post_install', '-at_install')
class Test029(TallerCommon):
    """2026.19.029: adicionales por cantidad (excedente), aprobación y facturación."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.tllr_fc_aprobacion_adicional = 'obligatoria'
        cls.env['tllr_fc.funcion.costo'].create({
            'funcion_id': cls.personal1.funcion_id.id, 'fecha_desde': date(2020, 1, 1),
            'costo_hora': 1000})
        cls.env.user.group_ids |= cls.env.ref('tllr_fc.group_supervisor')

    def _ot_proceso(self, cantidad=2):
        ot = self._ot_planificada()
        linea = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': cantidad})
        ot.action_iniciar()
        return ot, linea

    def test_01_en_espera_la_cubierta_sigue_la_cantidad(self):
        ot = self._ot_planificada()
        linea = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 2})
        self.assertEqual(linea.cantidad_cubierta, 2)
        linea.cantidad_reservada = 5
        self.assertEqual(linea.cantidad_cubierta, 5)
        self.assertEqual(linea.cantidad_excedente, 0)
        self.assertFalse(linea.pendiente_aprobacion)

    def test_02_subir_cantidad_en_proceso_genera_excedente(self):
        ot, linea = self._ot_proceso()
        linea.cantidad_reservada = 3
        self.assertEqual(linea.cantidad_cubierta, 2)
        self.assertEqual(linea.cantidad_excedente, 1)
        self.assertTrue(linea.pendiente_aprobacion)
        self.assertTrue(ot.adicionales_pendientes)

    def test_03_no_se_usa_mas_que_lo_cubierto(self):
        ot, linea = self._ot_proceso()
        linea.cantidad_reservada = 3
        with self.assertRaisesRegex(UserError, "excedente"):
            linea.cantidad_utilizada = 3
        linea.cantidad_utilizada = 2

    def test_04_linea_nueva_nace_pendiente_con_cubierta_cero(self):
        ot, linea = self._ot_proceso()
        nueva = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.insumo.id, 'cantidad_reservada': 1})
        self.assertEqual(nueva.state_aprobacion, 'pendiente')
        self.assertEqual(nueva.cantidad_cubierta, 0)
        self.assertTrue(nueva.pendiente_aprobacion)

    def test_05_la_facturacion_excluye_lo_pendiente(self):
        ot, linea = self._ot_proceso()
        linea.cantidad_reservada = 3
        linea.cantidad_utilizada = 2
        nueva = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.insumo.id, 'cantidad_reservada': 1,
            'precio_unitario': 100})
        comandos = ot._tllr_fc_lineas_factura()
        productos = {c[2]['product_id']: c[2]['quantity'] for c in comandos
                     if c[2]['product_id'] in (self.repuesto.id, self.insumo.id)}
        self.assertEqual(productos.get(self.repuesto.id), 2)
        self.assertNotIn(nueva.product_id.id, productos)

    def test_06_aprobacion_del_cliente_cubre_el_excedente(self):
        ot, linea = self._ot_proceso()
        linea.cantidad_reservada = 3
        self.env['tllr_fc.wizard.aprobacion'].create({
            'ot_id': ot.id, 'persona': 'Cliente', 'estado': 'aprobado',
            'producto_ids': [Command.set(linea.ids)]}).action_registrar()
        self.assertEqual(linea.cantidad_cubierta, 3)
        self.assertFalse(linea.pendiente_aprobacion)
        linea.cantidad_utilizada = 3

    def test_07_rechazo_devuelve_la_cantidad_a_lo_cubierto(self):
        ot, linea = self._ot_proceso()
        linea.cantidad_reservada = 3
        self.env['tllr_fc.wizard.aprobacion'].create({
            'ot_id': ot.id, 'persona': 'Cliente', 'estado': 'rechazado',
            'producto_ids': [Command.set(linea.ids)]}).action_registrar()
        self.assertEqual(linea.cantidad_reservada, 2)
        self.assertFalse(linea.pendiente_aprobacion)

    def test_08_rechazo_de_linea_nueva_la_quita(self):
        ot, linea = self._ot_proceso()
        nueva = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.insumo.id, 'cantidad_reservada': 1})
        self.env['tllr_fc.wizard.aprobacion'].create({
            'ot_id': ot.id, 'persona': 'Cliente', 'estado': 'rechazado',
            'producto_ids': [Command.set(nueva.ids)]}).action_registrar()
        self.assertFalse(nueva.exists())

    def test_09_autorizacion_del_supervisor_deja_registro(self):
        ot, linea = self._ot_proceso()
        linea.cantidad_reservada = 3
        antes = len(ot.aprobacion_ids)
        linea.with_context(tllr_fc_excepcion=True, tllr_fc_motivo="prueba"
                           ).action_autorizar_sin_aprobacion()
        self.assertEqual(len(ot.aprobacion_ids), antes + 1)
        self.assertEqual(ot.aprobacion_ids[-1].medio, 'supervisor')
        self.assertEqual(linea.cantidad_cubierta, 3)
        self.assertFalse(linea.pendiente_aprobacion)

    def test_10_servicio_con_cantidad_mayor_tambien_es_excedente(self):
        ot, linea = self._ot_proceso()
        servicio = ot.servicio_ids[:1]
        servicio.cantidad = 2
        self.assertEqual(servicio.cantidad_excedente, 1)
        self.assertTrue(servicio.pendiente_aprobacion)
        comandos = ot._tllr_fc_lineas_factura()
        cant = [c[2]['quantity'] for c in comandos if c[2]['product_id'] == servicio.product_id.id]
        self.assertEqual(cant, [1])

    def test_11_garantia_sin_cobro_no_controla_excedentes(self):
        ot = self._ot_planificada()
        ot.tipo = 'garantia'
        linea = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 1})
        ot.action_iniciar()
        linea.cantidad_reservada = 4
        self.assertEqual(linea.cantidad_excedente, 0)
