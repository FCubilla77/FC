# -*- coding: utf-8 -*-
from datetime import date

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import TallerCommon


@tagged('post_install', '-at_install')
class Test030(TallerCommon):
    """2026.19.030: informe obligatorio al liquidar y entregar, informes impresos."""

    parchear_cierre = False

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref('tllr_fc.group_supervisor')

    def test_01_mensaje_de_utilizado_orienta_las_dos_salidas(self):
        ot = self._ot_planificada()
        linea = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 1})
        ot.action_iniciar()
        with self.assertRaisesRegex(ValidationError, "línea adicional"):
            linea.cantidad_utilizada = 2

    def test_02_servicio_terminado_sin_informe_se_detecta(self):
        ot = self._ot_planificada()
        servicio = ot.servicio_ids[:1]
        servicio.with_context(tllr_fc_permitir_write=True).write(
            {'estado': 'terminado', 'informe': False})
        with self.assertRaisesRegex(UserError, "Falta el informe"):
            ot._tllr_fc_verificar_informes()
        servicio.informe = "Hecho"
        ot._tllr_fc_verificar_informes()

    def test_03_informes_en_los_reportes(self):
        ot = self._ot_planificada()
        ot.servicio_ids.with_context(tllr_fc_permitir_write=True).write(
            {'estado': 'terminado', 'informe': 'Informe de prueba 030'})
        html, _ = self.env['ir.actions.report']._render_qweb_html(
            'tllr_fc.report_ot_cliente_document', ot.ids)
        self.assertIn(b'Informe de prueba 030', html)
        self.assertIn(b'Informe de los servicios', html)
