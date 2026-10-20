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
