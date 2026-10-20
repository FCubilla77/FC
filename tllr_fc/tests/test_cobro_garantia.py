# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import TallerCommon


@tagged('post_install', '-at_install')
class TestCobroGarantia(TallerCommon):
    """2026.19.010: «Cobrar al cliente» en las OT de garantía."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        compania = cls.env.company
        cls.diario = cls.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', compania.id)], limit=1)
        compania.tllr_fc_diario_venta_id = cls.diario

    def _ot_garantia(self, cobrar_repuesto=True, cobrar_servicio=False):
        ot = self._ot_planificada()
        ot.write({'tipo': 'garantia'})
        self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 2,
            'cobrar_cliente': cobrar_repuesto})
        if cobrar_servicio:
            ot.servicio_ids.filtered(lambda s: s.product_id == self.s2).cobrar_cliente = True
        return ot

    def _aprobar(self, ot):
        wiz = self.env['tllr_fc.wizard.aprobacion'].with_context(default_ot_id=ot.id).create({
            'ot_id': ot.id, 'persona': 'El cliente', 'estado': 'aprobado'})
        wiz.action_registrar()

    def _terminar(self, ot):
        for linea in ot.puesto_line_ids.sorted('sequence'):
            if linea.state == 'activo':
                linea.servicio_ids.filtered(lambda s: s.estado == 'pendiente').action_terminar()
                ot.action_terminar_puesto()

    def test_marcar_cobro_exige_aprobacion_y_solo_factura_lo_marcado(self):
        ot = self._ot_garantia()
        repuesto = ot.producto_ids
        self.assertTrue(repuesto.facturable)
        self.assertEqual(repuesto.state_aprobacion, 'pendiente')
        self.assertEqual(repuesto.descuento, 10.0)
        self.assertEqual(repuesto.precio_unitario, 30000)
        self.assertFalse(any(ot.servicio_ids.mapped('facturable')))
        self.assertEqual(ot.lineas_cobrar, 1)
        self.assertTrue(ot.requiere_factura)
        self.assertAlmostEqual(ot.total, 2 * 30000 * 0.9)
        # Sin aprobación del cliente no se consume.
        ot.action_iniciar()
        with self.assertRaises(UserError):
            repuesto.cantidad_utilizada = 2
        self._aprobar(ot)
        self.assertEqual(repuesto.state_aprobacion, 'aprobado')
        repuesto.cantidad_utilizada = 2
        self._terminar(ot)
        self.assertEqual(ot.state, 'listo')
        ot.action_cerrar_facturar()
        factura = ot._tllr_fc_facturas()
        self.assertEqual(len(factura.invoice_line_ids), 1)
        self.assertEqual(factura.invoice_line_ids.product_id, self.repuesto)
        # La entrega exige la factura confirmada.
        entrega = self.env['tllr_fc.entrega'].create({'ot_id': ot.id})
        entrega.linea_ids.write({'entregado': True})
        self.assertTrue(any('factura confirmada' in p for p in entrega._tllr_fc_problemas()))
        factura.invoice_payment_term_id = self.env['account.payment.term'].create({
            'name': '30 días cobro', 'line_ids': [Command.create({
                'value': 'percent', 'value_amount': 100, 'delay_type': 'days_after',
                'nb_days': 30})]})
        factura.action_post()
        entrega.kilometraje_salida = 2500
        self.assertFalse(entrega._tllr_fc_problemas())

    def test_garantia_sin_lineas_a_cobrar_no_se_factura_ni_exige_factura(self):
        ot = self._ot_garantia(cobrar_repuesto=False)
        self.assertEqual(ot.lineas_cobrar, 0)
        self.assertFalse(ot.requiere_factura)
        self.assertEqual(ot.total, 0.0)
        ot.action_iniciar()
        ot.producto_ids.cantidad_utilizada = 2
        self._terminar(ot)
        with self.assertRaises(UserError):
            ot.action_cerrar_facturar()
        entrega = self.env['tllr_fc.entrega'].create({'ot_id': ot.id})
        entrega.linea_ids.write({'entregado': True})
        entrega.kilometraje_salida = 2500
        self.assertFalse(entrega._tllr_fc_problemas())

    def test_desmarcar_cobro_quita_la_aprobacion_pendiente(self):
        ot = self._ot_garantia()
        ot.producto_ids.cobrar_cliente = False
        self.assertEqual(ot.producto_ids.state_aprobacion, 'no_requiere')
        self.assertFalse(ot.producto_ids.facturable)

    def test_cobrar_servicio_y_rechazo_del_cliente(self):
        ot = self._ot_garantia(cobrar_servicio=True)
        servicio = ot.servicio_ids.filtered(lambda s: s.product_id == self.s2)
        self.assertEqual(servicio.state_aprobacion, 'pendiente')
        self.assertEqual(ot.lineas_cobrar, 2)
        wiz = self.env['tllr_fc.wizard.aprobacion'].with_context(default_ot_id=ot.id).create({
            'ot_id': ot.id, 'persona': 'El cliente', 'estado': 'rechazado'})
        wiz.action_registrar()
        # Rechazar el cobro no quita la línea: queda cubierta por la garantía.
        self.assertTrue(servicio.exists())
        self.assertFalse(servicio.cobrar_cliente)
        self.assertTrue(ot.producto_ids.exists())
        self.assertEqual(ot.lineas_cobrar, 0)

    def test_solo_el_supervisor_marca_y_solo_en_garantia(self):
        ot = self._ot_garantia(cobrar_repuesto=False)
        with self.assertRaises(AccessError):
            ot.producto_ids.with_user(self.usuario_taller).cobrar_cliente = True
        cliente = self._ot_planificada()
        servicio = cliente.servicio_ids[:1]
        with self.assertRaises(ValidationError):
            servicio.cobrar_cliente = True

    def test_rentabilidad_garantia_suma_el_costo_no_cobrado_a_la_ot_original(self):
        original = self._ot_planificada()
        original.write({'tipo': 'cliente'})
        garantia = self._ot_garantia(cobrar_repuesto=True)
        garantia.ot_origen_id = original
        garantia.action_iniciar()
        self._aprobar(garantia)
        garantia.producto_ids.cantidad_utilizada = 2
        insumo = self.env['tllr_fc.ot.producto'].create({
            'ot_id': garantia.id, 'product_id': self.insumo.id, 'cantidad_reservada': 1})
        insumo.cantidad_utilizada = 1
        self.assertAlmostEqual(garantia.ingreso, 2 * 30000 * 0.9)
        self.assertAlmostEqual(garantia.costo_propio, 2 * 12000)
        self.assertAlmostEqual(garantia.costo_garantia_absorbido, 8000)
        self.assertAlmostEqual(garantia.margen, 2 * 30000 * 0.9 - 2 * 12000)
        self.assertAlmostEqual(original.costo_garantias_origen, 8000)
