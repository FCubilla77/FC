# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .test_fase4 import TestFase4 as _Base


@tagged('post_install', '-at_install')
class TestAjustes(_Base):
    """Ajustes 2026.19.006 (se reutilizan los auxiliares de la fase 4)."""

    def test_informe_por_servicio(self):
        ot = self._ot_en_proceso()
        servicio = ot.servicio_ids[:1]
        servicio.informe = 'Se cambió el aceite y el filtro'
        self.assertEqual(servicio.informe, 'Se cambió el aceite y el filtro')
        ot.action_detener  # sigue accesible
        otra = self._llegar_a_calidad()
        otra.servicio_ids[:1].informe = 'Informe en calidad'
        self.assertEqual(otra.servicio_ids[:1].informe, 'Informe en calidad')
        with self.assertRaises(UserError):
            otra.servicio_ids[:1].estado = 'no_realizado'

    def test_control_manual_tras_descartar_el_borrador(self):
        ot = self._llegar_a_calidad()
        with self.assertRaises(UserError):  # ya hay uno en borrador
            self.env['tllr_fc.control_calidad'].create({'ot_id': ot.id})
        ot.control_ids.unlink()
        control = self.env['tllr_fc.control_calidad'].create({'ot_id': ot.id})
        self.assertEqual(control.state, 'borrador')

    def test_volver_de_calidad_a_proceso(self):
        ot = self._llegar_a_calidad()
        accion = ot.action_volver_estado()
        self.assertEqual(accion['res_model'], 'tllr_fc.wizard.excepcion')
        self.assertEqual(ot.state, 'calidad')
        self._autorizar(ot, 'action_volver_estado', 'Falta un ajuste')
        self.assertEqual(ot.state, 'proceso')
        self.assertFalse(ot.control_ids.filtered(lambda c: c.state == 'borrador'))
        self.assertEqual(len(ot.puesto_line_ids.filtered(lambda l: l.state == 'activo')), 1)

    def test_volver_de_listo_a_calidad(self):
        ot = self._llegar_a_calidad()
        ot.control_ids.action_aprobar_todas()
        ot.control_ids.action_confirmar()
        self.assertEqual(ot.state, 'listo')
        self._autorizar(ot, 'action_volver_estado', 'Revisar')
        self.assertEqual(ot.state, 'calidad')
        self.assertTrue(ot.control_ids.filtered(lambda c: c.state == 'borrador'))

    def test_volver_a_espera_solo_sin_actividad(self):
        ot = self._ot_en_proceso()
        self._autorizar(ot, 'action_volver_estado', 'Inicio por error')
        self.assertEqual(ot.state, 'espera')
        ot.action_iniciar()
        ot.servicio_ids[:1].action_terminar()
        with self.assertRaises(UserError):
            ot.action_volver_estado()

    def test_volver_estado_solo_supervisor(self):
        ot = self._llegar_a_calidad()
        with self.assertRaises(AccessError):
            ot.with_user(self.usuario_taller).action_volver_estado()

    def test_calidad_es_una_columna_del_tablero(self):
        ot = self._llegar_a_calidad()
        calidad = ot.company_id._tllr_fc_puesto_calidad()
        self.assertTrue(calidad.es_calidad)
        self.assertEqual(ot.puesto_activo_id, calidad)
        columnas = ot._read_group_puesto_activo_id(self.env['tllr_fc.puesto'], [])
        self.assertEqual(columnas[-1], calidad)
        self.assertEqual(ot.servicio_ids[:1].display_name,
                         ot.servicio_ids[:1].product_id.display_name)

    def test_arrastre_a_y_desde_calidad(self):
        ot = self._ot_planificada()
        ot.requiere_qc = True
        ot.action_iniciar()
        calidad = ot.company_id._tllr_fc_puesto_calidad()
        # Con puestos pendientes no se puede saltar a calidad.
        if len(ot.puesto_line_ids) > 1:
            with self.assertRaises(UserError):
                ot.puesto_activo_id = calidad
        for linea in ot.puesto_line_ids.sorted('sequence'):
            if linea.state == 'activo':
                linea.servicio_ids.filtered(lambda s: s.estado == 'pendiente').action_terminar()
                if linea != ot.puesto_line_ids.sorted('sequence')[-1]:
                    ot.action_terminar_puesto()
        ot.puesto_activo_id = calidad
        self.assertEqual(ot.state, 'calidad')
        self.assertEqual(len(ot.control_ids), 1)
        ultimo = ot.puesto_line_ids.sorted('sequence')[-1].puesto_id
        ot.puesto_activo_id = ultimo
        self.assertEqual(ot.state, 'proceso')

    def test_horas_en_calidad_solo_responsable(self):
        ot = self._llegar_a_calidad()
        responsable = ot.control_ids.responsable_id
        self.assertEqual(ot.personal_horas_ids, responsable)
        hora = self.env['tllr_fc.ot.hora'].create({
            'ot_id': ot.id, 'personal_id': responsable.id, 'horas': 1.5})
        self.assertEqual(hora.horas, 1.5)
