# -*- coding: utf-8 -*-
from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.tllr_fc.tests.common import TallerCommon


@tagged('post_install', '-at_install')
class TestCompras(TallerCommon):
    """2026.19.023: puente de Compras."""

    parchear_cierre = False

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        compania = cls.env.company
        cls.proveedor = cls.env['res.partner'].create({'name': 'Proveedor F23'})
        cls.s2.product_tmpl_id.tllr_fc_puede_tercerizarse = True
        cls.diario_venta = cls.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', compania.id)], limit=1)
        compania.tllr_fc_diario_venta_id = cls.diario_venta

    # ---------------- Auxiliares ----------------
    def _asistente(self, ot, usuario=None, **extra):
        modelo = self.env['tllr_fc.wizard.compra_directa']
        if usuario:
            modelo = modelo.with_user(usuario)
        return modelo.with_context(default_ot_id=ot.id).create({'ot_id': ot.id, **extra})

    def _ot_con_repuesto(self, reservada=15):
        ot = self._ot_planificada()
        self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': reservada})
        return ot

    def _compra_directa(self, ot, cantidad=5, precio=11000):
        asistente = self._asistente(
            ot, proveedor_id=self.proveedor.id,
            linea_ids=[Command.create({
                'producto_id': ot.producto_ids.id, 'cantidad': cantidad, 'precio': precio})])
        accion = asistente.action_crear_compra()
        return self.env['purchase.order'].browse(accion['res_id'])

    def _recibir(self, compra):
        compra.button_confirm()
        picking = compra.picking_ids
        for movimiento in picking.move_ids:
            movimiento.quantity = movimiento.product_uom_qty
            movimiento.picked = True
        picking._action_done()
        return picking

    # ---------------- Ajuste ----------------
    def test_ajuste_activo_por_defecto(self):
        self.assertTrue(self.env.company.tllr_fc_usar_compras)
        self.assertTrue(self.env['res.config.settings'].create({}).tllr_fc_usar_compras)

    # ---------------- Compra directa ----------------
    def test_asistente_propone_el_faltante_de_stock(self):
        ot = self._ot_con_repuesto(15)  # hay 10 en stock
        asistente = self._asistente(ot)
        self.assertEqual(len(asistente.linea_ids), 1)
        self.assertAlmostEqual(asistente.linea_ids.cantidad, 5.0)

    def test_compra_directa_vincula_la_ot(self):
        ot = self._ot_con_repuesto()
        compra = self._compra_directa(ot)
        self.assertEqual(compra.tllr_fc_ot_id, ot)
        self.assertEqual(compra.tllr_fc_tipo, 'directa')
        self.assertEqual(compra.state, 'draft')
        self.assertEqual(compra.order_line.price_unit, 11000)
        self.assertEqual(ot.producto_ids.origen_compra_id, compra)
        self.assertEqual(ot.compra_count, 1)
        self.assertTrue(ot.action_ver_compras()['domain'])

    def test_usuario_solicita_y_no_crea_la_compra(self):
        ot = self._ot_con_repuesto()
        asistente = self._asistente(
            ot, usuario=self.usuario_taller,
            linea_ids=[Command.create({
                'producto_id': ot.producto_ids.id, 'cantidad': 5})])
        with self.assertRaises(AccessError):
            asistente.action_crear_compra()
        asistente.action_solicitar()
        actividades = self.env['mail.activity'].search([
            ('res_model', '=', 'tllr_fc.ot'), ('res_id', '=', ot.id)])
        self.assertTrue(actividades)
        self.assertFalse(ot.compra_ids)

    def test_compra_directa_sin_integracion_no_se_crea(self):
        self.env.company.tllr_fc_usar_compras = False
        ot = self._ot_con_repuesto()
        with self.assertRaises(UserError):
            ot.action_compra_directa()

    def test_recibir_la_compra_reserva_a_la_ot(self):
        ot = self._ot_con_repuesto(15)
        compra = self._compra_directa(ot, cantidad=5)
        self._recibir(compra)
        self.assertEqual(compra.picking_ids.state, 'done')
        mensajes = ot.message_ids.filtered(lambda m: 'recibida' in (m.body or ''))
        self.assertTrue(mensajes)
        # Todo lo pedido por la OT queda reservado (10 de stock + 5 recibidos)
        reservado = sum(ot.producto_ids.move_ids.filtered(
            lambda m: m.state in ('assigned', 'partially_available')).mapped('quantity'))
        self.assertAlmostEqual(reservado, 15.0)

    def test_recibir_compra_sobrante_queda_libre(self):
        ot = self._ot_con_repuesto(12)
        compra = self._compra_directa(ot, cantidad=8)  # sobran 6
        antes = self.repuesto.free_qty
        self._recibir(compra)
        self.assertAlmostEqual(self.repuesto.free_qty - antes, 8 - 2)

    # ---------------- Tercerizados ----------------
    def test_tercerizado_exige_ficha_y_proveedor(self):
        ot = self._ot_planificada()
        servicio_propio = ot.servicio_ids.filtered(lambda s: s.product_id == self.s1)
        with self.assertRaises(ValidationError):
            servicio_propio.write({'tercerizado': True, 'proveedor_id': self.proveedor.id})
        servicio = ot.servicio_ids.filtered(lambda s: s.product_id == self.s2)
        with self.assertRaises(ValidationError):
            servicio.write({'tercerizado': True})

    def test_solo_supervisor_terceriza(self):
        ot = self._ot_planificada()
        servicio = ot.servicio_ids.filtered(lambda s: s.product_id == self.s2)
        with self.assertRaises(AccessError):
            servicio.with_user(self.usuario_taller).write({
                'tercerizado': True, 'proveedor_id': self.proveedor.id})

    def _tercerizar(self, ot):
        servicio = ot.servicio_ids.filtered(lambda s: s.product_id == self.s2)
        servicio.write({'tercerizado': True, 'proveedor_id': self.proveedor.id})
        servicio.action_generar_compra()
        return servicio

    def test_tercerizado_genera_compra_y_costo_real(self):
        ot = self._ot_planificada()
        servicio = self._tercerizar(ot)
        compra = servicio.compra_id
        self.assertEqual(compra.tllr_fc_ot_id, ot)
        self.assertEqual(compra.tllr_fc_tipo, 'tercerizado')
        self.assertEqual(compra.order_line.tllr_fc_ot_servicio_id, servicio)
        self.assertEqual(servicio.horas_estandar, 0.0)
        # Sin compra confirmada: costo estándar de la ficha
        self.assertEqual(servicio.costo_efectivo, servicio._tllr_fc_costo_estandar_valor())
        compra.order_line.price_unit = 20000
        compra.button_confirm()
        self.assertEqual(servicio.costo_real, 20000)
        self.assertEqual(servicio.costo_efectivo, 20000)
        self.assertEqual(ot.tercerizados_resumen, self.proveedor.name)
        with self.assertRaises(UserError):
            servicio.action_generar_compra()  # una sola compra por servicio
        with self.assertRaises(UserError):
            servicio.write({'tercerizado': False})

    def test_tercerizado_no_suma_horas(self):
        ot = self._ot_planificada()
        servicio = self._tercerizar(ot)
        ot.action_iniciar()
        with self.assertRaises(ValidationError):
            self.env['tllr_fc.ot.hora'].create({
                'ot_id': ot.id, 'servicio_id': servicio.id,
                'puesto_line_id': servicio.puesto_line_id.id,
                'personal_id': self.personal2.id, 'horas': 1})

    def test_cierre_de_puesto_no_exige_horas_al_tercerizado(self):
        ot = self._ot_planificada()
        servicio = self._tercerizar(ot)
        ot.action_iniciar()
        servicio.with_context(tllr_fc_permitir_write=True).write({'estado': 'terminado'})
        servicio.informe = 'Hecho por el proveedor'
        servicio.puesto_line_id._tllr_fc_validar_cierre()  # no exige horas

    def test_tercerizado_se_factura_con_precio_de_ficha(self):
        ot = self._ot_planificada()
        servicio = self._tercerizar(ot)
        self.assertEqual(servicio.precio_unitario, self.s2.list_price)
        self.assertTrue(servicio.facturable)

    # ---------------- Factura de proveedor tardía ----------------
    def test_factura_tardia_crea_ajuste_de_costo(self):
        ot = self._ot_planificada()
        servicio = self._tercerizar(ot)
        compra = servicio.compra_id
        compra.order_line.price_unit = 20000
        compra.button_confirm()
        # La OT termina antes de que llegue la factura
        ot.write({'state': 'entregado'})
        compra.action_create_invoice()
        factura = compra.invoice_ids
        factura.invoice_date = fields.Date.context_today(factura)
        factura.invoice_line_ids.price_unit = 23000
        factura.action_post()
        ajuste = self.env['tllr_fc.ot.ajuste_costo'].search([('ot_id', '=', ot.id)])
        self.assertEqual(len(ajuste), 1)
        self.assertAlmostEqual(ajuste.monto, 3000)
        self.assertEqual(ajuste.origen_compra_id, compra)
        self.assertFalse(ajuste.asiento_id)

    def test_factura_igual_a_la_compra_no_crea_ajuste(self):
        ot = self._ot_planificada()
        servicio = self._tercerizar(ot)
        compra = servicio.compra_id
        compra.order_line.price_unit = 20000
        compra.button_confirm()
        ot.write({'state': 'entregado'})
        compra.action_create_invoice()
        factura = compra.invoice_ids
        factura.invoice_date = fields.Date.context_today(factura)
        factura.action_post()
        self.assertFalse(self.env['tllr_fc.ot.ajuste_costo'].search([('ot_id', '=', ot.id)]))

    def test_factura_con_ot_en_proceso_no_crea_ajuste(self):
        ot = self._ot_planificada()
        servicio = self._tercerizar(ot)
        compra = servicio.compra_id
        compra.order_line.price_unit = 20000
        compra.button_confirm()
        compra.action_create_invoice()
        factura = compra.invoice_ids
        factura.invoice_date = fields.Date.context_today(factura)
        factura.invoice_line_ids.price_unit = 23000
        factura.action_post()
        self.assertFalse(self.env['tllr_fc.ot.ajuste_costo'].search([('ot_id', '=', ot.id)]))

    def test_sin_integracion_la_factura_tardia_no_ajusta(self):
        ot = self._ot_planificada()
        servicio = self._tercerizar(ot)
        compra = servicio.compra_id
        compra.order_line.price_unit = 20000
        compra.button_confirm()
        ot.write({'state': 'entregado'})
        self.env.company.tllr_fc_usar_compras = False
        compra.action_create_invoice()
        factura = compra.invoice_ids
        factura.invoice_date = fields.Date.context_today(factura)
        factura.invoice_line_ids.price_unit = 23000
        factura.action_post()
        self.assertFalse(self.env['tllr_fc.ot.ajuste_costo'].search([('ot_id', '=', ot.id)]))

    def test_90_ajustes_desmarcar_abre_asistente_de_desinstalacion(self):
        ajustes = self.env['res.config.settings'].create({})
        self.assertTrue(ajustes.module_tllr_fc_purchase)
        ajustes.module_tllr_fc_purchase = False
        accion = ajustes.execute()
        self.assertEqual(accion.get('res_model'), 'base.module.uninstall')

    # ---------------- 2026.19.026: aviso de existencia ----------------
    def test_95_aviso_sin_existencia_propone_compra_directa_y_pendientes(self):
        sin_stock = self.env['product.product'].create({
            'name': 'Sin stock 026 compras', 'type': 'consu', 'is_storable': True,
            'tllr_fc_uso_taller': 'repuesto'})
        ot = self._ot_planificada()
        linea = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': sin_stock.id, 'cantidad_reservada': 2})
        self.assertIn("compra directa", linea._tllr_fc_aviso_existencia())
        proveedor = self.env['res.partner'].create({'name': 'Proveedor 026'})
        compra = self.env['purchase.order'].create({
            'partner_id': proveedor.id,
            'order_line': [Command.create({
                'product_id': sin_stock.id, 'product_qty': 3, 'price_unit': 100})]})
        compra.button_confirm()
        aviso = linea._tllr_fc_aviso_existencia()
        self.assertIn(compra.name, aviso)
        self.assertIn("pendientes", aviso)
