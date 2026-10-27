# -*- coding: utf-8 -*-
from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import TallerCommon


@tagged('post_install', '-at_install')
class Test026(TallerCommon):
    """2026.19.026: kilometraje al duplicar, horas automáticas, repuestos por servicio."""

    def _entregar_ot_con_repuestos(self, servicios, lineas):
        """OT entregada con repuestos. lineas: [(producto, cantidad, servicio_producto|None)]."""
        ot = self._ot(servicios=servicios)
        puestos = {self.s1: self.puesto1, self.s2: self.puesto2}
        for i, servicio in enumerate(servicios):
            self.env['tllr_fc.ot.puesto'].create({
                'ot_id': ot.id, 'puesto_id': puestos[servicio].id, 'sequence': 10 * (i + 1),
                'personal_ids': [Command.set((self.personal1 if i == 0 else self.personal2).ids)]})
        ot.responsable_id = self.responsable
        for producto, cantidad, servicio in lineas:
            vinculo = ot.servicio_ids.filtered(lambda s: s.product_id == servicio)
            self.env['tllr_fc.ot.producto'].create({
                'ot_id': ot.id, 'product_id': producto.id, 'cantidad_reservada': cantidad,
                'servicio_id': vinculo.id or False})
        ot.action_iniciar()
        for puesto in ot.puesto_line_ids.sorted('sequence'):
            if puesto.state == 'activo':
                for linea in ot.producto_ids.filtered(lambda p: p.puesto_line_id == puesto):
                    linea.cantidad_utilizada = linea.cantidad_reservada
                puesto.servicio_ids.filtered(lambda s: s.estado == 'pendiente').action_terminar()
                ot.action_terminar_puesto()
        ot.write({'state': 'entregado', 'fecha_entrega': fields.Datetime.now()})
        return ot

    # ---------------- Vehículo ----------------
    def test_01_duplicar_vehiculo_reinicia_kilometraje(self):
        self.assertEqual(self.vehiculo.kilometraje, 1000)
        copia = self.vehiculo.copy()
        self.assertEqual(copia.kilometraje, 0)

    # ---------------- Horas ----------------
    def _default_hora(self, ot):
        return self.env['tllr_fc.ot.hora'].with_context(default_ot_id=ot.id).default_get(
            ['servicio_id', 'puesto_line_id'])

    def test_02_horas_proponen_servicio_y_puesto_unicos(self):
        ot = self._ot(servicios=[self.s1])
        puesto = self.env['tllr_fc.ot.puesto'].create({
            'ot_id': ot.id, 'puesto_id': self.puesto1.id,
            'personal_ids': [Command.set(self.personal1.ids)]})
        valores = self._default_hora(ot)
        self.assertEqual(valores.get('servicio_id'), ot.servicio_ids.id)
        self.assertEqual(valores.get('puesto_line_id'), puesto.id)

    def test_03_horas_con_varios_servicios_y_un_puesto_proponen_solo_el_puesto(self):
        ot = self._ot(servicios=[self.s1, self.s2])
        puesto = self.env['tllr_fc.ot.puesto'].create({
            'ot_id': ot.id, 'puesto_id': self.puesto1.id,
            'personal_ids': [Command.set(self.personal1.ids)]})
        valores = self._default_hora(ot)
        self.assertFalse(valores.get('servicio_id'))
        self.assertEqual(valores.get('puesto_line_id'), puesto.id)

    def test_04_horas_con_varios_servicios_y_puestos_no_proponen(self):
        ot = self._ot_planificada()
        valores = self._default_hora(ot)
        self.assertFalse(valores.get('servicio_id'))
        self.assertFalse(valores.get('puesto_line_id'))

    # ---------------- Repuesto vinculado al servicio ----------------
    def test_05_servicio_vinculado_debe_ser_de_la_ot(self):
        ot = self._ot(servicios=[self.s1])
        ot2 = self._ot(servicios=[self.s2])
        with self.assertRaises(ValidationError):
            self.env['tllr_fc.ot.producto'].create({
                'ot_id': ot.id, 'product_id': self.repuesto.id,
                'servicio_id': ot2.servicio_ids.id})

    def test_06_costo_de_repuestos_por_servicio(self):
        ot = self._entregar_ot_con_repuestos(
            [self.s1], [(self.repuesto, 2, self.s1), (self.insumo, 1, None)])
        servicio = ot.servicio_ids
        self.assertEqual(servicio.producto_ids.product_id, self.repuesto)
        self.assertEqual(servicio.costo_repuestos, 24000)

    # ---------------- Carga desde la OT anterior ----------------
    def test_07_carga_los_repuestos_vinculados_al_servicio(self):
        self._entregar_ot_con_repuestos(
            [self.s1, self.s2],
            [(self.repuesto, 2, self.s1), (self.insumo, 1, self.s2)])
        nueva = self._ot(servicios=[self.s1])
        self.assertEqual(len(nueva.producto_ids), 1)
        linea = nueva.producto_ids
        self.assertEqual(linea.product_id, self.repuesto)
        self.assertEqual(linea.cantidad_reservada, 2)
        self.assertEqual(linea.servicio_id, nueva.servicio_ids)
        self.assertFalse(linea.adicional)

    def test_08_los_genericos_no_se_cargan(self):
        self._entregar_ot_con_repuestos(
            [self.s1], [(self.repuesto, 2, self.s1), (self.insumo, 1, None)])
        nueva = self._ot(servicios=[self.s1])
        self.assertEqual(nueva.producto_ids.product_id, self.repuesto)

    def test_09_ot_anterior_sin_vinculos_carga_todo(self):
        self._entregar_ot_con_repuestos(
            [self.s1], [(self.repuesto, 2, None), (self.insumo, 1, None)])
        nueva = self._ot(servicios=[self.s1])
        self.assertEqual(set(nueva.producto_ids.product_id.ids),
                         {self.repuesto.id, self.insumo.id})
        self.assertFalse(nueva.producto_ids.servicio_id)

    def test_10_servicio_distinto_no_carga(self):
        self._entregar_ot_con_repuestos([self.s1], [(self.repuesto, 2, self.s1)])
        nueva = self._ot(servicios=[self.s2])
        self.assertFalse(nueva.producto_ids)

    def test_11_otro_vehiculo_no_carga(self):
        self._entregar_ot_con_repuestos([self.s1], [(self.repuesto, 2, self.s1)])
        otro = self.vehiculo.copy({'chapa': 'OTRO 026'})
        recepcion = self.env['tllr_fc.recepcion'].create({
            'vehiculo_id': otro.id, 'partner_id': self.cliente.id, 'kilometraje': 10,
            'servicio_ids': [Command.create({'product_id': self.s1.id})]})
        recepcion.action_cargar_items()
        recepcion.item_ids.write({'presente': 'si'})
        recepcion.action_confirmar()
        self.assertFalse(recepcion.ot_id.producto_ids)

    # ---------------- Aviso de existencia ----------------
    def test_12_aviso_sin_existencia(self):
        sin_stock = self.env['product.product'].create({
            'name': 'Sin stock 026', 'type': 'consu', 'is_storable': True,
            'tllr_fc_uso_taller': 'repuesto'})
        ot = self._ot(servicios=[self.s1])
        linea = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': sin_stock.id, 'cantidad_reservada': 1})
        self.assertIn("no tiene existencia", linea._tllr_fc_aviso_existencia())
        self.assertIn("compra", linea._tllr_fc_aviso_existencia())

    def test_13_aviso_no_alcanza(self):
        ot = self._ot(servicios=[self.s1])
        linea = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 50})
        self.assertIn("no alcanza", linea._tllr_fc_aviso_existencia())

    def test_14_sin_aviso_si_hay_stock(self):
        ot = self._ot(servicios=[self.s1])
        linea = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 2})
        self.assertEqual(linea._tllr_fc_aviso_existencia(), "")

    def test_15_onchange_devuelve_advertencia(self):
        ot = self._ot(servicios=[self.s1])
        linea = self.env['tllr_fc.ot.producto'].new({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 99})
        resultado = linea._onchange_aviso_existencia()
        self.assertTrue(resultado and resultado.get('warning'))
