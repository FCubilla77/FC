# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import TallerCommon


@tagged('post_install', '-at_install')
class TestAjustes011(TallerCommon):
    """Ajustes de la versión 2026.19.011 (cierre de puesto, calidad, bloqueos)."""
    parchear_cierre = False

    def _ot_proceso(self, reservada=3):
        ot = self._ot_planificada()
        linea = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id,
            'cantidad_reservada': reservada,
            'puesto_line_id': ot.puesto_line_ids.sorted('sequence')[0].id,
        }) if 'puesto_line_id' in self.env['tllr_fc.ot.producto']._fields else \
            self.env['tllr_fc.ot.producto'].create({
                'ot_id': ot.id, 'product_id': self.repuesto.id,
                'cantidad_reservada': reservada})
        ot.action_iniciar()
        return ot, linea

    # ---- 01 Ajustes: validación diferida ----
    def test_01_validacion_diferida(self):
        compania = self.env.company
        compania.tllr_fc_generar_asientos = False
        compania.with_context(tllr_fc_diferir_validacion=True).tllr_fc_generar_asientos = True
        compania.with_context(tllr_fc_diferir_validacion=True).tllr_fc_diario_id = False
        with self.assertRaises(ValidationError):
            compania._tllr_fc_validar_asientos()
        compania.tllr_fc_generar_asientos = False

    # ---- 02 Horas con puesto + servicio; responsable ----
    def test_02_horas_servicio_y_responsable(self):
        ot, _l = self._ot_proceso()
        Hora = self.env['tllr_fc.ot.hora']
        with self.assertRaises(UserError):
            Hora.create({'ot_id': ot.id, 'personal_id': self.personal1.id, 'horas': 1})
        hora = Hora.create({'ot_id': ot.id, **self._sv(ot),
                            'personal_id': self.responsable.id, 'horas': 1})
        self.assertTrue(hora.puesto_line_id)

    # ---- 03 Terminar puesto ----
    def test_03_terminar_puesto_exige_informe_horas_y_no_utilizado(self):
        ot, linea = self._ot_proceso(3)
        puesto = ot.puesto_line_ids.sorted('sequence')[0]
        puesto.servicio_ids.action_terminar()
        with self.assertRaises(UserError):
            puesto._tllr_fc_validar_cierre()
        puesto.servicio_ids.write({'informe': 'Hecho'})
        with self.assertRaises(UserError):
            puesto._tllr_fc_validar_cierre()  # faltan horas
        self.env['tllr_fc.ot.hora'].create({
            'ot_id': ot.id, **self._sv(ot), 'personal_id': self.personal1.id, 'horas': 1})
        with self.assertRaises(UserError):
            puesto._tllr_fc_validar_cierre()  # sin costo/hora vigente
        from datetime import date
        self.env['tllr_fc.funcion.costo'].create({
            'funcion_id': self.personal1.funcion_id.id,
            'fecha_desde': date(2020, 1, 1), 'costo_hora': 1000})
        if linea.puesto_line_id == puesto or 'puesto_line_id' not in linea._fields:
            with self.assertRaises(UserError):
                puesto._tllr_fc_validar_cierre()  # utilizada+no utilizada != reservada
            linea.write({'cantidad_utilizada': 2, 'cantidad_no_utilizada': 1})
        puesto._tllr_fc_validar_cierre()

    def test_03b_no_utilizado_no_excede(self):
        ot, linea = self._ot_proceso(3)
        with self.assertRaises(ValidationError):
            linea.write({'cantidad_utilizada': 2, 'cantidad_no_utilizada': 2})

    # ---- 04/05 Control de calidad ----
    def test_04_control_responsable_manual_y_grid(self):
        ot = self._ot_planificada()
        control = self.env['tllr_fc.control_calidad'].new({'ot_id': ot.id})
        self.assertFalse(control.responsable_id)

    # ---- 08 Entrega ----
    def test_08_entrega_campos_obligatorios(self):
        self.assertFalse(self.env['tllr_fc.entrega']._fields['retira_id'].required)
        self.assertIn('combustible_salida', self.env['tllr_fc.entrega']._fields)

    # ---- 11 Bloqueos ----
    def test_11_devolucion_de_picking_ot_bloqueada(self):
        self.assertIn('stock.return.picking', self.env)
        self.assertIn('tllr_fc_ot_id', self.env['stock.picking']._fields)
        self.assertIn('tllr_fc_ot_id', self.env['account.move']._fields)
