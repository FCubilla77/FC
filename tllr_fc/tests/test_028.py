# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import TallerCommon


@tagged('post_install', '-at_install')
class Test028(TallerCommon):
    """2026.19.028: nombre descriptivo de la línea de puesto y puesto del repuesto según su servicio."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.puesto_doble = cls.env['tllr_fc.puesto'].create({
            'name': 'Puesto doble F28', 'almacen_id': cls.almacen.id,
            'servicio_ids': [Command.set((cls.s1 | cls.s2).product_tmpl_id.ids)]})

    def _lineas(self):
        ot = self._ot()
        s2 = ot.servicio_ids.filtered(lambda s: s.product_id == self.s2)
        L = self.env['tllr_fc.ot.puesto']
        l1 = L.create({'ot_id': ot.id, 'puesto_id': self.puesto_doble.id, 'sequence': 10,
                       'personal_ids': [Command.set(self.personal1.ids)]})
        l2 = L.create({'ot_id': ot.id, 'puesto_id': self.puesto_doble.id, 'sequence': 20,
                       'servicio_id': s2.id,
                       'personal_ids': [Command.set(self.personal2.ids)]})
        return ot, l1, l2, s2

    def test_01_nombre_distingue_lineas_del_mismo_puesto(self):
        ot, l1, l2, s2 = self._lineas()
        self.assertNotEqual(l1.display_name, l2.display_name)
        self.assertIn(self.s2.name, l2.display_name)
        self.assertIn(self.s1.name, l1.display_name)
        # El nombre del puesto (mensajes, reportes) no cambia.
        self.assertEqual(l1.name, l2.name)

    def test_02_linea_sin_servicio_muestra_el_personal(self):
        ot = self._ot(servicios=[self.s1])
        linea = self.env['tllr_fc.ot.puesto'].create({
            'ot_id': ot.id, 'puesto_id': self.puesto2.id,
            'personal_ids': [Command.set(self.personal2.ids)]})
        self.assertIn(self.personal2.name, linea.display_name)

    def test_03_elegir_servicio_completa_el_puesto(self):
        ot, l1, l2, s2 = self._lineas()
        repuesto = self.env['tllr_fc.ot.producto'].new({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'servicio_id': s2.id})
        repuesto._onchange_servicio_puesto()
        self.assertEqual(repuesto.puesto_line_id, l2)

    def test_04_repuesto_con_servicio_no_toma_otra_linea(self):
        ot, l1, l2, s2 = self._lineas()
        repuesto = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 1,
            'servicio_id': s2.id})
        self.assertEqual(repuesto.puesto_line_id, l2)
        with self.assertRaisesRegex(UserError, "corresponde al servicio"):
            repuesto.puesto_line_id = l1

    def test_05_repuesto_generico_elige_cualquier_linea(self):
        ot, l1, l2, s2 = self._lineas()
        repuesto = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.insumo.id, 'cantidad_reservada': 1})
        repuesto.puesto_line_id = l2
        self.assertEqual(repuesto.puesto_line_id, l2)
        repuesto.puesto_line_id = l1
        self.assertEqual(repuesto.puesto_line_id, l1)

    def test_06_quitar_servicio_permite_cambiar_de_linea(self):
        ot, l1, l2, s2 = self._lineas()
        repuesto = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 1,
            'servicio_id': s2.id})
        repuesto.write({'servicio_id': False, 'puesto_line_id': l1.id})
        self.assertEqual(repuesto.puesto_line_id, l1)
