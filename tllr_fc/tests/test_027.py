# -*- coding: utf-8 -*-
from datetime import date

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import TallerCommon


@tagged('post_install', '-at_install')
class Test027(TallerCommon):
    """2026.19.027: servicio en la línea de puesto, duplicados, repuestos y horas por línea."""

    parchear_cierre = False

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Un puesto que realiza los dos servicios (el caso de dos servicios en el mismo puesto).
        cls.puesto_doble = cls.env['tllr_fc.puesto'].create({
            'name': 'Puesto doble F27', 'almacen_id': cls.almacen.id,
            'servicio_ids': [Command.set((cls.s1 | cls.s2).product_tmpl_id.ids)]})
        cls.env['tllr_fc.funcion.costo'].create({
            'funcion_id': cls.personal1.funcion_id.id, 'fecha_desde': date(2020, 1, 1),
            'costo_hora': 1000})

    def _lineas_doble(self, ot=None):
        """Dos líneas del mismo puesto, una por servicio, con personal distinto."""
        ot = ot or self._ot()
        s1 = ot.servicio_ids.filtered(lambda s: s.product_id == self.s1)
        s2 = ot.servicio_ids.filtered(lambda s: s.product_id == self.s2)
        L = self.env['tllr_fc.ot.puesto']
        l1 = L.create({'ot_id': ot.id, 'puesto_id': self.puesto_doble.id, 'sequence': 10,
                       'personal_ids': [Command.set(self.personal1.ids)]})
        l2 = L.create({'ot_id': ot.id, 'puesto_id': self.puesto_doble.id, 'sequence': 20,
                       'servicio_id': s2.id,
                       'personal_ids': [Command.set(self.personal2.ids)]})
        ot.responsable_id = self.responsable
        return ot, l1, l2, s1, s2

    def _hora(self, ot, personal, servicio=None, linea=None, horas=1.0):
        return self.env['tllr_fc.ot.hora'].create({
            'ot_id': ot.id, 'personal_id': personal.id, 'horas': horas,
            'servicio_id': servicio.id if servicio else False,
            'puesto_line_id': (linea or servicio.puesto_line_id).id})

    # ---------------- Línea con servicio ----------------
    def test_01_servicio_se_mueve_a_la_segunda_linea(self):
        ot, l1, l2, s1, s2 = self._lineas_doble()
        self.assertEqual(s1.puesto_line_id, l1)
        self.assertEqual(s2.puesto_line_id, l2)
        self.assertEqual(l1.servicio_id, s1)
        self.assertEqual(l2.servicio_id, s2)

    def test_02_dos_servicios_mismo_puesto_avanzan_en_orden(self):
        ot, l1, l2, s1, s2 = self._lineas_doble()
        ot.action_iniciar()
        self.assertEqual((l1.state, l2.state), ('activo', 'pendiente'))
        s1.informe = "ok"
        s1.action_terminar()
        self._hora(ot, self.personal1, s1)
        ot.action_terminar_puesto()
        self.assertEqual((l1.state, l2.state), ('terminado', 'activo'))
        s2.informe = "ok"
        s2.action_terminar()
        self._hora(ot, self.personal2, s2)
        ot.action_terminar_puesto()
        self.assertEqual(l2.state, 'terminado')

    def test_03_servicio_duplicado_en_otra_linea_se_bloquea(self):
        ot, l1, l2, s1, s2 = self._lineas_doble()
        otra = self.env['tllr_fc.ot.puesto'].create({
            'ot_id': ot.id, 'puesto_id': self.puesto_doble.id, 'sequence': 30,
            'personal_ids': [Command.set(self.personal1.ids)]})
        with self.assertRaisesRegex(UserError, "duplicando"):
            otra.servicio_id = s2

    def test_04_linea_sin_servicio_con_mismo_personal_es_duplicado(self):
        ot = self._ot(servicios=[self.s1])
        L = self.env['tllr_fc.ot.puesto']
        L.create({'ot_id': ot.id, 'puesto_id': self.puesto2.id,
                  'personal_ids': [Command.set(self.personal1.ids)]})
        with self.assertRaisesRegex(ValidationError, "duplicando"):
            L.create({'ot_id': ot.id, 'puesto_id': self.puesto2.id,
                      'personal_ids': [Command.set(self.personal1.ids)]})

    def test_05_linea_sin_servicio_con_otro_personal_se_permite(self):
        ot = self._ot(servicios=[self.s1])
        L = self.env['tllr_fc.ot.puesto']
        L.create({'ot_id': ot.id, 'puesto_id': self.puesto2.id,
                  'personal_ids': [Command.set(self.personal1.ids)]})
        L.create({'ot_id': ot.id, 'puesto_id': self.puesto2.id,
                  'personal_ids': [Command.set(self.personal2.ids)]})
        self.assertEqual(len(ot.puesto_line_ids), 2)

    def test_06_servicio_de_linea_en_curso_no_se_cambia(self):
        ot, l1, l2, s1, s2 = self._lineas_doble()
        ot.action_iniciar()
        with self.assertRaises(UserError):
            l1.servicio_id = s2

    # ---------------- Repuestos ----------------
    def test_07_repuesto_sigue_al_puesto_de_su_servicio(self):
        ot, l1, l2, s1, s2 = self._lineas_doble()
        repuesto = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 1,
            'servicio_id': s2.id})
        self.assertEqual(repuesto.puesto_line_id, l2)
        ot.action_iniciar()
        with self.assertRaisesRegex(UserError, "no está activo"):
            repuesto.cantidad_utilizada = 1

    def test_08_repuesto_pasa_al_puesto_al_mover_el_servicio(self):
        ot = self._ot()
        s2 = ot.servicio_ids.filtered(lambda s: s.product_id == self.s2)
        L = self.env['tllr_fc.ot.puesto']
        l1 = L.create({'ot_id': ot.id, 'puesto_id': self.puesto_doble.id, 'sequence': 10,
                       'personal_ids': [Command.set(self.personal1.ids)]})
        repuesto = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 1,
            'servicio_id': s2.id})
        self.assertEqual(repuesto.puesto_line_id, l1)
        l2 = L.create({'ot_id': ot.id, 'puesto_id': self.puesto_doble.id, 'sequence': 20,
                       'servicio_id': s2.id,
                       'personal_ids': [Command.set(self.personal2.ids)]})
        self.assertEqual(repuesto.puesto_line_id, l2)

    def test_09_repuesto_de_servicio_2_se_usa_al_activarse_su_puesto(self):
        ot, l1, l2, s1, s2 = self._lineas_doble()
        repuesto = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 1,
            'servicio_id': s2.id})
        ot.action_iniciar()
        s1.informe = "ok"
        s1.action_terminar()
        self._hora(ot, self.personal1, s1)
        ot.action_terminar_puesto()
        repuesto.cantidad_utilizada = 1
        self.assertEqual(repuesto.cantidad_utilizada, 1)

    # ---------------- Horas ----------------
    def test_10_horas_solo_del_personal_de_la_linea(self):
        ot, l1, l2, s1, s2 = self._lineas_doble()
        ot.action_iniciar()
        with self.assertRaisesRegex(ValidationError, "no está asignado"):
            self._hora(ot, self.personal2, s1)  # personal2 es de la línea 2
        self._hora(ot, self.personal1, s1)

    def test_11_el_responsable_tampoco_carga_horas_si_no_esta_en_la_linea(self):
        ot, l1, l2, s1, s2 = self._lineas_doble()
        ot.action_iniciar()
        with self.assertRaisesRegex(ValidationError, "no está asignado"):
            self._hora(ot, self.responsable, s1)

    def test_12_no_se_cargan_horas_en_linea_pendiente(self):
        ot, l1, l2, s1, s2 = self._lineas_doble()
        ot.action_iniciar()
        with self.assertRaisesRegex(UserError, "todavía no está activo"):
            self._hora(ot, self.personal2, s2)

    def test_13_linea_sin_personal_no_admite_horas(self):
        ot = self._ot(servicios=[self.s1])
        linea = self.env['tllr_fc.ot.puesto'].create({
            'ot_id': ot.id, 'puesto_id': self.puesto1.id})
        servicio = ot.servicio_ids
        ot.write({'responsable_id': self.responsable.id})
        linea.write({'personal_ids': [Command.set(self.personal1.ids)]})
        ot.action_iniciar()
        linea.write({'personal_ids': [Command.clear()]})
        with self.assertRaisesRegex(ValidationError, "no tiene personal"):
            self._hora(ot, self.personal1, servicio)

    def test_14_no_se_quita_personal_con_horas(self):
        ot, l1, l2, s1, s2 = self._lineas_doble()
        ot.action_iniciar()
        self._hora(ot, self.personal1, s1)
        with self.assertRaisesRegex(UserError, "tiene horas cargadas"):
            l1.write({'personal_ids': [Command.clear()]})

    def test_15_linea_sin_servicio_admite_horas_sin_servicio(self):
        ot = self._ot(servicios=[self.s1])
        L = self.env['tllr_fc.ot.puesto']
        L.create({'ot_id': ot.id, 'puesto_id': self.puesto1.id, 'sequence': 10,
                  'personal_ids': [Command.set(self.personal1.ids)]})
        control = L.create({'ot_id': ot.id, 'puesto_id': self.puesto2.id, 'sequence': 20,
                            'personal_ids': [Command.set(self.personal2.ids)]})
        ot.responsable_id = self.responsable
        ot.action_iniciar()
        ot.servicio_ids.informe = "ok"
        ot.servicio_ids.action_terminar()
        self._hora(ot, self.personal1, ot.servicio_ids)
        ot.action_terminar_puesto()
        hora = self._hora(ot, self.personal2, linea=control)
        self.assertFalse(hora.servicio_id)

    def test_16_servicio_con_horas_no_cambia_de_puesto(self):
        ot, l1, l2, s1, s2 = self._lineas_doble()
        ot.action_iniciar()
        self._hora(ot, self.personal1, s1)
        with self.assertRaises(UserError):
            s1.puesto_line_id = l2

    def test_17_no_se_borra_linea_con_horas(self):
        ot, l1, l2, s1, s2 = self._lineas_doble()
        ot.action_iniciar()
        self._hora(ot, self.personal1, s1)
        s1.informe = "ok"
        s1.action_terminar()
        ot.action_terminar_puesto()
        with self.assertRaises(UserError):
            l1.unlink()

    # ---------------- Cierre ----------------
    def test_18_cierre_indica_horas_y_aprobacion_pendientes(self):
        ot, l1, l2, s1, s2 = self._lineas_doble()
        ot.action_iniciar()
        s1.informe = "ok"
        s1.action_terminar()
        with self.assertRaisesRegex(UserError, "Faltan las horas trabajadas de"):
            ot.action_terminar_puesto()

    def test_19_iniciar_asigna_servicios_a_la_linea_unica(self):
        ot = self._ot()
        self.env['tllr_fc.ot.puesto'].create({
            'ot_id': ot.id, 'puesto_id': self.puesto_doble.id,
            'personal_ids': [Command.set(self.personal1.ids)]})
        ot.responsable_id = self.responsable
        ot.action_iniciar()
        self.assertEqual(set(ot.servicio_ids.mapped('estado')), {'pendiente'})
        self.assertTrue(all(ot.servicio_ids.mapped('puesto_line_id')))
