# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, tagged

from odoo.addons.tllr_fc.tests.common import TallerCommon


@tagged('post_install', '-at_install')
class TestVentas(TallerCommon):
    """2026.19.022: puente de Ventas."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        compania = cls.env.company
        cls.diario_venta = cls.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', compania.id)], limit=1)
        compania.write({'tllr_fc_diario_venta_id': cls.diario_venta.id})
        cls.plazo = cls.env['account.payment.term'].create({
            'name': '30 días Ventas', 'line_ids': [Command.create({
                'value': 'percent', 'value_amount': 100, 'delay_type': 'days_after',
                'nb_days': 30})]})

    # ---------------- Auxiliares ----------------
    def _ot_lista(self, repuesto=True):
        ot = self._ot_planificada()
        if repuesto:
            self.env['tllr_fc.ot.producto'].create({
                'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 2})
        ot.action_iniciar()
        if repuesto:
            ot.producto_ids.cantidad_utilizada = 2
        for linea in ot.puesto_line_ids.sorted('sequence'):
            if linea.state == 'activo':
                linea.servicio_ids.filtered(lambda s: s.estado == 'pendiente').action_terminar()
                ot.action_terminar_puesto()
        self.assertEqual(ot.state, 'listo')
        return ot

    def _presupuesto(self, productos=None, **extra):
        productos = productos or [self.s1, self.s2]
        valores = {
            'partner_id': self.cliente.id,
            'order_line': [Command.create({
                'product_id': p.id, 'product_uom_qty': 1}) for p in productos],
        }
        valores.update(extra)
        return self.env['sale.order'].create(valores)

    def _recepcion(self, pedido=None, **extra):
        valores = {
            'vehiculo_id': self.vehiculo.id, 'partner_id': self.cliente.id,
            'kilometraje': 2000,
            'servicio_ids': [Command.create({'product_id': self.s1.id}),
                             Command.create({'product_id': self.s2.id})],
        }
        if pedido:
            valores['sale_order_id'] = pedido.id
        valores.update(extra)
        recepcion = self.env['tllr_fc.recepcion'].create(valores)
        recepcion.action_cargar_items()
        recepcion.item_ids.write({'presente': 'si'})
        return recepcion

    def _confirmar_recepcion(self, recepcion):
        accion = recepcion.action_confirmar()
        if isinstance(accion, dict):
            self.env['tllr_fc.wizard.confirmar_advertencia'].create({
                'res_model': 'tllr_fc.recepcion', 'res_id': recepcion.id,
                'accion': 'action_confirmar', 'mensaje': 'x'}).action_continuar()
        return recepcion.ot_id

    def _planificar(self, ot):
        self.env['tllr_fc.ot.puesto'].create([
            {'ot_id': ot.id, 'puesto_id': self.puesto1.id, 'sequence': 10,
             'personal_ids': [Command.set(self.personal1.ids)]},
            {'ot_id': ot.id, 'puesto_id': self.puesto2.id, 'sequence': 20,
             'personal_ids': [Command.set(self.personal2.ids)]},
        ])
        ot.responsable_id = self.responsable

    def _autorizar(self, registro, accion, motivo='Prueba'):
        self.env['tllr_fc.wizard.excepcion'].create({
            'res_model': registro._name, 'res_id': registro.id, 'accion': accion,
            'grupo_requerido': 'supervisor', 'motivo': motivo}).action_autorizar()

    # ---------------- Ajuste ----------------
    def test_ajuste_activo_por_defecto(self):
        self.assertTrue(self.env.company.tllr_fc_usar_ventas)
        ajustes = self.env['res.config.settings'].create({})
        self.assertTrue(ajustes.tllr_fc_usar_ventas)

    # ---------------- Cerrar para facturar ----------------
    def test_cerrar_facturar_crea_pedido_y_factura_desde_el_pedido(self):
        ot = self._ot_lista()
        self.assertFalse(ot.sale_order_id)
        ot.action_cerrar_facturar()
        pedido = ot.sale_order_id
        self.assertTrue(pedido)
        self.assertEqual(pedido.state, 'sale')
        self.assertEqual(pedido.tllr_fc_ot_id, ot)
        self.assertEqual(pedido.tllr_fc_vehiculo_id, ot.vehiculo_id)
        self.assertEqual(len(pedido.order_line), 3)  # 2 servicios + repuesto
        factura = ot._tllr_fc_facturas()
        self.assertEqual(len(factura), 1)
        self.assertEqual(factura.state, 'draft')
        self.assertEqual(factura.tllr_fc_ot_id, ot)
        self.assertEqual(factura.invoice_line_ids.sale_line_ids, pedido.order_line)
        self.assertAlmostEqual(factura.amount_total, pedido.amount_total)
        # El stock lo mueve la OT: el pedido no genera entregas propias.
        self.assertFalse(pedido.picking_ids)
        # Precios de la ficha con el descuento del cliente (10 %)
        servicio = pedido.order_line.filtered(lambda l: l.product_id == self.s1)
        self.assertEqual(servicio.price_unit, 100000)
        self.assertEqual(servicio.discount, 10.0)

    def test_factura_confirmada_desde_pedido(self):
        ot = self._ot_lista()
        ot.action_cerrar_facturar()
        factura = ot._tllr_fc_facturas()
        factura.invoice_payment_term_id = self.plazo
        factura.action_post()
        self.assertEqual(ot.sale_order_id.invoice_status, 'invoiced')
        self.assertGreater(ot.ingreso, 0)
        self.assertEqual(ot.estado_facturacion, 'confirmada')

    def test_sin_integracion_factura_directa(self):
        self.env.company.tllr_fc_usar_ventas = False
        ot = self._ot_lista()
        ot.action_cerrar_facturar()
        self.assertFalse(ot.sale_order_id)
        factura = ot._tllr_fc_facturas()
        self.assertEqual(len(factura), 1)
        self.assertFalse(factura.invoice_line_ids.sale_line_ids)

    def test_ot_con_pedido_sigue_facturando_desde_el_pedido(self):
        ot = self._ot_lista()
        ot.action_actualizar_presupuesto()
        pedido = ot.sale_order_id
        self.assertTrue(pedido)
        self.env.company.tllr_fc_usar_ventas = False
        ot.action_cerrar_facturar()
        self.assertEqual(ot.sale_order_id, pedido)
        self.assertEqual(pedido.state, 'sale')
        self.assertEqual(ot._tllr_fc_facturas().invoice_line_ids.sale_line_ids, pedido.order_line)

    def test_reabrir_y_cerrar_de_nuevo_mantiene_un_solo_pedido(self):
        ot = self._ot_lista()
        ot.action_cerrar_facturar()
        pedido = ot.sale_order_id
        self.assertIsInstance(ot.action_reabrir_facturar(), dict)
        self._autorizar(ot, 'action_reabrir_facturar', 'Error de precio')
        self.assertFalse(ot.cerrada_facturar)
        ot.action_cerrar_facturar()
        self.assertEqual(ot.sale_order_id, pedido)
        self.assertEqual(self.env['sale.order'].search_count(
            [('tllr_fc_ot_id', '=', ot.id)]), 1)
        self.assertEqual(len(ot._tllr_fc_facturas()), 1)

    def test_nota_de_credito_total_y_refacturar(self):
        ot = self._ot_lista()
        ot.action_cerrar_facturar()
        factura = ot._tllr_fc_facturas()
        factura.invoice_payment_term_id = self.plazo
        factura.action_post()
        reversa = self.env['account.move.reversal'].with_context(
            active_model='account.move', active_ids=factura.ids).create({
                'journal_id': factura.journal_id.id, 'reason': 'Error'})
        nota = self.env['account.move'].browse(reversa.refund_moves()['res_id'])
        nota.action_post()
        self.assertTrue(ot.puede_refacturar)
        ot.with_context(tllr_fc_refacturando=True).action_cerrar_facturar()
        self.assertEqual(len(ot._tllr_fc_facturas().filtered(lambda m: m.state == 'draft')), 1)

    # ---------------- Actualizar presupuesto ----------------
    def test_actualizar_presupuesto_deja_historial(self):
        ot = self._ot_planificada()
        self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 1})
        ot.action_actualizar_presupuesto()
        pedido = ot.sale_order_id
        self.assertEqual(pedido.state, 'draft')
        self.assertEqual(len(pedido.order_line), 3)
        ot.action_iniciar()
        # Con un presupuesto existente hay que habilitar la actualización
        with self.assertRaises(UserError):
            ot.action_actualizar_presupuesto()
        ot.actualizar_presupuesto = True
        ot.producto_ids.descuento = 5
        ot.action_actualizar_presupuesto()
        self.assertEqual(pedido, ot.sale_order_id)
        self.assertEqual(len(pedido.order_line), 3)
        mensajes = pedido.message_ids.filtered(lambda m: 'Líneas anteriores' in (m.body or ''))
        self.assertTrue(mensajes)
        self.assertIn(self.env.user.name, mensajes[0].body)

    def test_solo_supervisor_habilita_actualizacion(self):
        ot = self._ot_planificada()
        with self.assertRaises(AccessError):
            ot.with_user(self.usuario_taller).write({'actualizar_presupuesto': True})

    def test_actualizar_pedido_confirmado_no_genera_entregas(self):
        ot = self._ot_planificada()
        self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 2})
        ot.action_actualizar_presupuesto()
        pedido = ot.sale_order_id
        pedido.with_context(skip_procurement=True).action_confirm()
        ot.action_iniciar()
        ot.actualizar_presupuesto = True
        ot.producto_ids.cantidad_reservada = 3
        ot.producto_ids.with_context(
            tllr_fc_excepcion=True, tllr_fc_motivo="prueba").action_autorizar_sin_aprobacion()
        ot.producto_ids.cantidad_utilizada = 3
        ot.action_actualizar_presupuesto()
        linea = pedido.order_line.filtered(lambda l: l.product_id == self.repuesto)
        self.assertEqual(linea.product_uom_qty, 3)
        self.assertEqual(linea.price_unit, 30000)
        self.assertFalse(pedido.picking_ids)

    # ---------------- Presupuesto previo en la recepción ----------------
    def test_recepcion_con_presupuesto_marca_check_y_copia_servicios(self):
        pedido = self._presupuesto([self.s1, self.repuesto])
        with Form(self.env['tllr_fc.recepcion']) as formulario:
            formulario.vehiculo_id = self.vehiculo
            formulario.partner_id = self.cliente
            formulario.kilometraje = 2000
            formulario.sale_order_id = pedido
            self.assertTrue(formulario.cliente_pidio_presupuesto)
            self.assertEqual(len(formulario.servicio_ids), 1)  # solo el servicio, no el repuesto
        recepcion = formulario.record
        self.assertEqual(recepcion.servicio_ids.product_id, self.s1)

    def test_ot_hereda_presupuesto_y_no_inicia_sin_confirmar(self):
        pedido = self._presupuesto()
        recepcion = self._recepcion(pedido, cliente_pidio_presupuesto=True)
        ot = self._confirmar_recepcion(recepcion)
        self.assertEqual(ot.sale_order_id, pedido)
        self.assertEqual(pedido.tllr_fc_ot_id, ot)
        self.assertEqual(pedido.tllr_fc_vehiculo_id, self.vehiculo)
        self.assertEqual(pedido.tllr_fc_kilometraje, 2000)
        self.assertEqual(ot.presupuesto_estado, 'borrador')
        self.assertTrue(ot._tllr_fc_requiere_presupuesto())
        self._planificar(ot)
        accion = ot.action_iniciar()
        self.assertIsInstance(accion, dict)  # pide la excepción del supervisor
        self.assertEqual(ot.state, 'espera')
        pedido.action_confirm()
        self.assertEqual(ot.presupuesto_estado, 'confirmado')
        ot.action_iniciar()
        self.assertEqual(ot.state, 'proceso')

    def test_supervisor_inicia_sin_presupuesto_confirmado_con_motivo(self):
        pedido = self._presupuesto()
        ot = self._confirmar_recepcion(self._recepcion(pedido, cliente_pidio_presupuesto=True))
        self._planificar(ot)
        self._autorizar(ot, 'action_iniciar', 'El cliente confirma por teléfono')
        self.assertEqual(ot.state, 'proceso')

    def test_sin_check_de_presupuesto_no_frena_el_inicio(self):
        ot = self._ot_planificada()
        self.assertFalse(ot._tllr_fc_requiere_presupuesto())
        ot.action_iniciar()
        self.assertEqual(ot.state, 'proceso')

    def test_presupuesto_con_otro_cliente_o_vehiculo_no_se_acepta(self):
        otro = self.env['res.partner'].create({'name': 'Otro cliente'})
        ajeno = self._presupuesto(partner_id=otro.id)
        with self.assertRaises(ValidationError):
            self._recepcion(ajeno)
        marca = self.vehiculo.marca_id
        otro_vehiculo = self.env['tllr_fc.vehiculo'].create({
            'name': 'Otro', 'marca_id': marca.id, 'modelo_id': self.vehiculo.modelo_id.id,
            'anio': 2020, 'tipo_id': self.vehiculo.tipo_id.id, 'partner_id': self.cliente.id,
            'chapa': 'OTR 001', 'kilometraje': 10})
        con_vehiculo = self._presupuesto(tllr_fc_vehiculo_id=otro_vehiculo.id)
        with self.assertRaises(ValidationError):
            self._recepcion(con_vehiculo)

    def test_presupuesto_en_una_sola_recepcion(self):
        pedido = self._presupuesto()
        self._recepcion(pedido)
        with self.assertRaises(ValidationError):
            self._recepcion(pedido)

    def test_anular_recepcion_libera_el_presupuesto(self):
        pedido = self._presupuesto()
        recepcion = self._recepcion(pedido)
        recepcion.action_cancelar()
        self.assertFalse(recepcion.sale_order_id)
        self._recepcion(pedido)  # ya se puede usar en otra recepción

    def test_una_ot_un_solo_presupuesto_vigente(self):
        ot = self._ot_planificada()
        ot.action_actualizar_presupuesto()
        with self.assertRaises(ValidationError):
            self._presupuesto(tllr_fc_ot_id=ot.id)

    # ---------------- Cancelación con liquidación ----------------
    def test_cancelar_liquidando_actualiza_el_pedido_a_lo_realizado(self):
        ot = self._ot_planificada()
        ot.action_actualizar_presupuesto()
        pedido = ot.sale_order_id
        self.assertEqual(len(pedido.order_line), 2)
        ot.action_iniciar()
        ot.puesto_line_ids.sorted('sequence')[0].servicio_ids.action_terminar()
        motivo = self.env['tllr_fc.motivo'].search([('tipo', '=', 'cancelacion')], limit=1)
        ot._tllr_fc_cancelar(motivo, True)
        self.assertEqual(ot.sale_order_id, pedido)
        self.assertEqual(pedido.state, 'sale')
        self.assertEqual(pedido.order_line.mapped('product_id'), self.s1)
        factura = ot._tllr_fc_facturas()
        self.assertEqual(factura.invoice_line_ids.product_id, self.s1)

    # ---------------- Vigencia e impresión ----------------
    def test_confirmar_presupuesto_vencido_avisa(self):
        ayer = fields.Date.context_today(self.env['sale.order']) - timedelta(days=1)
        pedido = self._presupuesto(
            tllr_fc_vehiculo_id=self.vehiculo.id, validity_date=ayer)
        accion = pedido.action_confirm()
        self.assertIsInstance(accion, dict)
        self.assertEqual(accion['res_model'], 'tllr_fc_sale.wizard.vencido')
        self.assertEqual(pedido.state, 'draft')
        self.env['tllr_fc_sale.wizard.vencido'].create({'order_id': pedido.id}).action_continuar()
        self.assertEqual(pedido.state, 'sale')

    def test_presupuesto_comun_vencido_no_avisa(self):
        ayer = fields.Date.context_today(self.env['sale.order']) - timedelta(days=1)
        pedido = self._presupuesto(validity_date=ayer)
        pedido.action_confirm()
        self.assertEqual(pedido.state, 'sale')

    def test_impresion_incluye_datos_del_vehiculo(self):
        pedido = self._presupuesto(
            tllr_fc_vehiculo_id=self.vehiculo.id, tllr_fc_kilometraje=2500)
        html, _ = self.env['ir.actions.report']._render_qweb_html(
            'sale.action_report_saleorder', pedido.ids)
        texto = html.decode()
        self.assertIn(self.vehiculo.chapa, texto)
        self.assertIn('Toyota F3', texto)
        informe = self.env.ref('sale.action_report_saleorder')
        self.assertEqual(informe.paperformat_id, self.env.ref('tllr_fc.paperformat_a4'))

    def test_usuario_de_taller_ve_presupuestos_de_solo_lectura(self):
        pedido = self._presupuesto()
        pedido.with_user(self.usuario_taller).read(['name'])
        with self.assertRaises(AccessError):
            pedido.with_user(self.usuario_taller).write({'note': 'x'})

    # ---------------- 2026.19.024: Ajustes ----------------
    def test_90_ajustes_desmarcar_abre_asistente_de_desinstalacion(self):
        ajustes = self.env['res.config.settings'].create({})
        self.assertTrue(ajustes.module_tllr_fc_sale)
        ajustes.module_tllr_fc_sale = False
        accion = ajustes.execute()
        self.assertEqual(accion.get('res_model'), 'base.module.uninstall')

    # ---------------- 2026.19.025: sin entregas de Ventas ----------------
    def test_91_presupuesto_del_taller_no_genera_entrega(self):
        pedido = self._presupuesto(
            productos=[self.s1, self.repuesto], tllr_fc_vehiculo_id=self.vehiculo.id)
        recepcion = self._recepcion(pedido)
        self.assertTrue(recepcion)
        pedido.action_confirm()
        self.assertEqual(pedido.state, 'sale')
        self.assertFalse(pedido.picking_ids)
        # Aumentar la cantidad tampoco genera entrega
        linea = pedido.order_line.filtered(lambda l: l.product_id == self.repuesto)
        linea.product_uom_qty = 4
        self.assertFalse(pedido.picking_ids)

    def test_92_presupuesto_comun_sigue_generando_entrega(self):
        pedido = self._presupuesto(productos=[self.repuesto])
        pedido.action_confirm()
        self.assertTrue(pedido.picking_ids)


@tagged('post_install', '-at_install')
class TestVentas029(TallerCommon):
    """2026.19.029: líneas «Desde la OT» y reapertura del presupuesto."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref('tllr_fc.group_supervisor')

    def _ot_con_presupuesto(self):
        ot = self._ot_planificada()
        self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 2})
        ot.actualizar_presupuesto = True
        ot.action_actualizar_presupuesto()
        return ot, ot.sale_order_id

    def test_29_01_lineas_del_presupuesto_quedan_marcadas(self):
        ot, pedido = self._ot_con_presupuesto()
        self.assertTrue(pedido.order_line)
        self.assertEqual(set(pedido.order_line.mapped('tllr_fc_origen')), {'ot'})

    def test_29_02_linea_manual_se_conserva_al_actualizar(self):
        ot, pedido = self._ot_con_presupuesto()
        pedido.write({'order_line': [Command.create({
            'product_id': self.s3.id, 'product_uom_qty': 1})]})
        manual = pedido.order_line.filtered(lambda l: l.product_id == self.s3)
        self.assertEqual(manual.tllr_fc_origen, 'manual')
        ot.producto_ids.cantidad_reservada = 3
        ot.action_actualizar_presupuesto()
        self.assertTrue(manual.exists())
        self.assertEqual(manual.product_uom_qty, 1)

    def test_29_03_producto_almacenable_manual_se_bloquea(self):
        ot, pedido = self._ot_con_presupuesto()
        with self.assertRaisesRegex(UserError, "orden de trabajo"):
            pedido.write({'order_line': [Command.create({
                'product_id': self.insumo.id, 'product_uom_qty': 1})]})

    def test_29_04_presupuesto_confirmado_vuelve_a_borrador(self):
        ot, pedido = self._ot_con_presupuesto()
        pedido.with_context(tllr_fc_vencido_ok=True, skip_procurement=True).action_confirm()
        self.assertEqual(pedido.state, 'sale')
        ot.producto_ids.cantidad_reservada = 3
        ot.action_actualizar_presupuesto()
        self.assertEqual(pedido.state, 'draft')
        linea = pedido.order_line.filtered(lambda l: l.product_id == self.repuesto)
        self.assertEqual(linea.product_uom_qty, 3)

    def test_29_05_sin_diferencias_sigue_confirmado(self):
        ot, pedido = self._ot_con_presupuesto()
        pedido.with_context(tllr_fc_vencido_ok=True, skip_procurement=True).action_confirm()
        ot.action_actualizar_presupuesto()
        self.assertEqual(pedido.state, 'sale')
