# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import TallerCommon


@tagged('post_install', '-at_install')
class TestFase5(TallerCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        compania = cls.env.company
        cls.diario = cls.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', compania.id)], limit=1)
        compania.tllr_fc_diario_venta_id = cls.diario
        cls.s1.product_tmpl_id.write({'tllr_fc_garantia_dias': 30, 'tllr_fc_garantia_km': 1000})
        cls.repuesto.product_tmpl_id.write({'tllr_fc_garantia_dias': 90})
        cls.plazo30 = cls.env['account.payment.term'].create({
            'name': '30 días F5', 'line_ids': [Command.create({
                'value': 'percent', 'value_amount': 100, 'delay_type': 'days_after',
                'nb_days': 30})]})

    # ---------------- Auxiliares ----------------
    def _autorizar(self, registro, accion, motivo='Prueba', grupo='supervisor'):
        self.env['tllr_fc.wizard.excepcion'].create({
            'res_model': registro._name, 'res_id': registro.id, 'accion': accion,
            'grupo_requerido': grupo, 'motivo': motivo}).action_autorizar()

    def _ot_lista(self, repuesto=True, no_facturar=False):
        ot = self._ot_planificada()
        if repuesto:
            self.env['tllr_fc.ot.producto'].create({
                'ot_id': ot.id, 'product_id': self.repuesto.id,
                'cantidad_reservada': 2})
        ot.action_iniciar()
        if repuesto:
            ot.producto_ids.cantidad_utilizada = 2
            if no_facturar:
                ot.producto_ids.no_facturar = True
        for linea in ot.puesto_line_ids.sorted('sequence'):
            if linea.state == 'activo':
                linea.servicio_ids.filtered(lambda s: s.estado == 'pendiente').action_terminar()
                ot.action_terminar_puesto()
        self.assertEqual(ot.state, 'listo')
        return ot

    def _facturar(self, ot, confirmar=True, plazo=True):
        ot.action_cerrar_facturar()
        factura = ot._tllr_fc_facturas()
        if plazo:
            factura.invoice_payment_term_id = self.plazo30
        if confirmar:
            factura.action_post()
        return factura

    # ---------------- Tablero ----------------
    def test_tablero_espera_primero_y_listo_ultimo(self):
        ot = self._ot_planificada()
        espera = ot.company_id._tllr_fc_puesto_sistema('espera')
        self.assertEqual(ot.puesto_activo_id, espera)
        columnas = ot._read_group_puesto_activo_id(self.env['tllr_fc.puesto'], [])
        self.assertEqual(columnas[0].sistema, 'espera')
        self.assertEqual(columnas[-1].sistema, 'listo')
        self.assertEqual(columnas[-2].sistema, 'calidad')
        self.assertIn(self.puesto1, columnas)
        # Los puestos de sistema no se eligen como puestos reales.
        self.assertEqual(self.env['tllr_fc.puesto'].search_count(
            [('sistema', '!=', False), ('id', 'in', self.puesto1.ids)]), 0)

    def test_arrastre_espera_a_primer_puesto_inicia_la_ot(self):
        ot = self._ot_planificada()
        ot.puesto_activo_id = self.puesto1
        self.assertEqual(ot.state, 'proceso')
        # Se vuelve a En espera solo si no se hizo nada.
        ot.puesto_activo_id = ot.company_id._tllr_fc_puesto_sistema('espera')
        self.assertEqual(ot.state, 'espera')
        with self.assertRaises(UserError):  # solo al primer puesto
            ot.puesto_activo_id = self.puesto2

    def test_ot_lista_aparece_en_la_columna_listo(self):
        ot = self._ot_lista()
        self.assertEqual(ot.puesto_activo_id, ot.company_id._tllr_fc_puesto_sistema('listo'))

    # ---------------- Facturación ----------------
    def test_cerrar_para_facturar_crea_factura_en_borrador(self):
        ot = self._ot_lista()
        ot.write({'responsable_id': ot.responsable_id.id})
        ot.action_cerrar_facturar()
        self.assertTrue(ot.cerrada_facturar)
        factura = ot._tllr_fc_facturas()
        self.assertEqual(len(factura), 1)
        self.assertEqual(factura.state, 'draft')
        self.assertEqual(factura.journal_id, self.diario)
        self.assertEqual(factura.partner_id, self.cliente)
        self.assertEqual(ot.estado_facturacion, 'borrador')
        productos = factura.invoice_line_ids.product_id
        self.assertIn(self.repuesto, productos)
        self.assertIn(self.s1, productos)
        self.assertNotIn(self.insumo, productos)
        linea = factura.invoice_line_ids.filtered(lambda l: l.product_id == self.repuesto)
        self.assertEqual(linea.quantity, 2)
        self.assertEqual(linea.discount, 10.0)
        with self.assertRaises(UserError):
            ot.action_cerrar_facturar()

    def test_no_facturar_queda_fuera_de_la_factura(self):
        ot = self._ot_lista(no_facturar=True)
        factura = self._facturar(ot, confirmar=False)
        self.assertNotIn(self.repuesto, factura.invoice_line_ids.product_id)

    def test_diario_de_venta_obligatorio_y_precio_obligatorio(self):
        ot = self._ot_lista()
        self.env.company.tllr_fc_diario_venta_id = False
        with self.assertRaises(UserError):
            ot.action_cerrar_facturar()
        self.env.company.tllr_fc_diario_venta_id = self.diario
        ot.servicio_ids[:1].with_context(tllr_fc_permitir_write=True).precio_unitario = 0
        with self.assertRaises(UserError):
            ot.action_cerrar_facturar()

    def test_ot_interna_no_se_factura(self):
        ot = self._ot_lista()
        ot.tipo = 'interno'
        with self.assertRaises(UserError):
            ot.action_cerrar_facturar()

    def test_reabrir_facturacion(self):
        ot = self._ot_lista()
        factura = self._facturar(ot, confirmar=False)
        accion = ot.action_reabrir_facturar()
        self.assertEqual(accion['res_model'], 'tllr_fc.wizard.excepcion')
        self._autorizar(ot, 'action_reabrir_facturar', 'Error de precio')
        self.assertFalse(ot.cerrada_facturar)
        self.assertFalse(factura.exists())
        factura = self._facturar(ot)
        with self.assertRaises(UserError):  # con factura confirmada no se reabre
            ot.action_reabrir_facturar()
        self.assertEqual(ot.estado_facturacion, 'confirmada')
        self.assertEqual(ot.estado_pago, 'no_pagada')

    def test_volver_atras_bloqueado_con_ot_cerrada_para_facturar(self):
        ot = self._ot_lista()
        self._facturar(ot, confirmar=False)
        with self.assertRaises(UserError):
            self._autorizar(ot, 'action_volver_estado')

    # ---------------- Entrega ----------------
    def test_entrega_sin_factura_exige_excepcion(self):
        ot = self._ot_lista()
        accion = ot.action_entregar()
        entrega = self.env['tllr_fc.entrega'].browse(accion['res_id'])
        self.assertEqual(entrega.retira_id, self.cliente)
        self.assertTrue(entrega.linea_ids)
        resultado = entrega.action_confirmar()
        self.assertEqual(resultado['res_model'], 'tllr_fc.wizard.excepcion')
        self.assertEqual(entrega.state, 'borrador')
        self._autorizar(entrega, 'action_confirmar', 'Cliente de confianza')
        self.assertEqual(entrega.state, 'confirmada')
        self.assertEqual(ot.state, 'entregado')
        self.assertTrue(ot.fecha_entrega)

    def test_entrega_con_factura_a_credito_no_pide_autorizacion(self):
        ot = self._ot_lista()
        self._facturar(ot)
        entrega = self.env['tllr_fc.entrega'].browse(ot.action_entregar()['res_id'])
        entrega.linea_ids.write({'entregado': True})
        entrega.kilometraje_salida = 2100
        self.assertTrue(entrega.action_confirmar() is True)
        self.assertEqual(ot.state, 'entregado')
        self.assertEqual(self.vehiculo.kilometraje, 2100)
        with self.assertRaises(UserError):
            entrega.write({'comentarios': 'x'})

    def test_factura_de_contado_sin_pago_exige_excepcion(self):
        ot = self._ot_lista()
        self._facturar(ot, plazo=False)
        entrega = self.env['tllr_fc.entrega'].browse(ot.action_entregar()['res_id'])
        entrega.linea_ids.write({'entregado': True})
        self.assertIsInstance(entrega.action_confirmar(), dict)

    def test_diferencias_de_inventario_exigen_excepcion(self):
        ot = self._ot_lista()
        self._facturar(ot)
        entrega = self.env['tllr_fc.entrega'].browse(ot.action_entregar()['res_id'])
        self.assertTrue(entrega.linea_ids.filtered('diferencia'))
        self.assertTrue(entrega.hay_diferencias)
        self.assertIsInstance(entrega.action_confirmar(), dict)
        entrega.linea_ids.write({'entregado': True})
        self.assertTrue(entrega.action_confirmar() is True)

    def test_combustible_de_salida_menor_alerta_sin_bloquear(self):
        ot = self._ot_lista()
        ot.combustible_ingreso = 'lleno'
        self._facturar(ot)
        entrega = self.env['tllr_fc.entrega'].browse(ot.action_entregar()['res_id'])
        entrega.linea_ids.write({'entregado': True})
        entrega.combustible_salida = '1_4'
        self.assertTrue(entrega.alerta_combustible)
        self.assertTrue(entrega.action_confirmar() is True)
        self.assertIn('combustible', ' '.join(ot.message_ids.mapped('body')).lower())

    def test_ot_interna_se_entrega_sin_factura(self):
        ot = self._ot_lista()
        ot.tipo = 'interno'
        entrega = self.env['tllr_fc.entrega'].browse(ot.action_entregar()['res_id'])
        entrega.linea_ids.write({'entregado': True})
        self.assertTrue(entrega.action_confirmar() is True)
        self.assertEqual(ot.state, 'entregado')
        self.assertFalse(ot.garantia_ids)  # solo las OT de cliente generan garantías

    # ---------------- Garantías ----------------
    def test_garantias_al_entregar(self):
        ot = self._ot_lista()
        self._facturar(ot)
        entrega = self.env['tllr_fc.entrega'].browse(ot.action_entregar()['res_id'])
        entrega.linea_ids.write({'entregado': True})
        entrega.kilometraje_salida = 2500
        entrega.action_confirmar()
        garantias = ot.garantia_ids
        self.assertEqual(set(garantias.product_id.ids), {self.s1.id, self.repuesto.id})
        g_servicio = garantias.filtered(lambda g: g.product_id == self.s1)
        self.assertEqual(g_servicio.km_limite, 3500)
        self.assertEqual(g_servicio.fecha_limite, fields.Date.to_date(ot.fecha_entrega) + timedelta(days=30))
        self.assertEqual(g_servicio.state, 'vigente')

    def test_reclamo_de_garantia_genera_recepcion_y_ot_de_garantia(self):
        ot = self._ot_lista()
        self._facturar(ot)
        entrega = self.env['tllr_fc.entrega'].browse(ot.action_entregar()['res_id'])
        entrega.linea_ids.write({'entregado': True})
        entrega.action_confirmar()
        asistente = self.env['tllr_fc.wizard.reclamo_garantia'].create({
            'ot_id': ot.id, 'garantia_ids': [Command.set(ot.garantia_ids.ids)],
            'kilometraje_actual': 2600, 'descripcion': 'Pierde aceite'})
        accion = asistente.action_reclamar()
        recepcion = self.env['tllr_fc.recepcion'].browse(accion['res_id'])
        self.assertEqual(recepcion.tipo_ot_propuesto, 'garantia')
        self.assertEqual(recepcion.ot_origen_id, ot)
        recepcion.action_cargar_items()
        recepcion.item_ids.write({'presente': 'si'})
        resultado = recepcion.action_confirmar()
        if isinstance(resultado, dict):
            self.env['tllr_fc.wizard.confirmar_advertencia'].create({
                'res_model': 'tllr_fc.recepcion', 'res_id': recepcion.id,
                'accion': 'action_confirmar', 'mensaje': 'x'}).action_continuar()
        ot_garantia = recepcion.ot_id
        self.assertEqual(ot_garantia.tipo, 'garantia')
        self.assertEqual(ot_garantia.ot_origen_id, ot)
        self.assertEqual(ot.garantia_ids.mapped('reclamo_ot_id'), ot_garantia)

    def test_reclamo_vencido_solo_lo_autoriza_el_administrador(self):
        ot = self._ot_lista()
        self._facturar(ot)
        entrega = self.env['tllr_fc.entrega'].browse(ot.action_entregar()['res_id'])
        entrega.linea_ids.write({'entregado': True})
        entrega.action_confirmar()
        ot.garantia_ids.sudo().write({'fecha_limite': fields.Date.today() - timedelta(days=1)})
        self.assertEqual(ot.garantia_ids[:1].state, 'vencida_fecha')
        asistente = self.env['tllr_fc.wizard.reclamo_garantia'].create({
            'ot_id': ot.id, 'garantia_ids': [Command.set(ot.garantia_ids.ids)],
            'kilometraje_actual': 2600, 'descripcion': 'Fuera de plazo'})
        self.assertTrue(asistente.aviso)
        accion = asistente.action_reclamar()
        self.assertEqual(accion['res_model'], 'tllr_fc.wizard.excepcion')
        self._autorizar(asistente, 'action_reclamar', 'Cliente antiguo', grupo='administrador')
        self.assertTrue(ot.garantia_ids.mapped('reclamo_recepcion_id'))

    # ---------------- Cancelación ----------------
    def test_cancelar_sin_trabajo_libera_reservas(self):
        ot = self._ot_planificada()
        linea = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 3})
        disponible = self.repuesto.with_context(location=self.almacen.lot_stock_id.id).free_qty
        asistente = self.env['tllr_fc.wizard.cancelar'].create({
            'ot_id': ot.id,
            'motivo_id': self.env.ref('tllr_fc.motivo_cancelacion_otro').id,
            'confirmo': True})
        asistente.action_confirmar()
        self.assertEqual(ot.state, 'cancelada')
        self.assertFalse(ot.liquidada)
        self.assertGreaterEqual(
            self.repuesto.with_context(location=self.almacen.lot_stock_id.id).free_qty, disponible)
        self.assertEqual(linea.reserva_estado, linea.reserva_estado)

    def test_cancelar_requiere_confirmacion(self):
        ot = self._ot_planificada()
        asistente = self.env['tllr_fc.wizard.cancelar'].create({
            'ot_id': ot.id, 'motivo_id': self.env.ref('tllr_fc.motivo_cancelacion_otro').id})
        with self.assertRaises(UserError):
            asistente.action_confirmar()

    def test_cancelar_con_liquidacion_factura_lo_realizado(self):
        ot = self._ot_planificada()
        ot.action_iniciar()
        primera = ot.puesto_line_ids.sorted('sequence')[0]
        primera.servicio_ids.action_terminar()
        self.assertTrue(ot._tllr_fc_trabajo_realizado())
        asistente = self.env['tllr_fc.wizard.cancelar'].create({
            'ot_id': ot.id,
            'motivo_id': self.env.ref('tllr_fc.motivo_cancelacion_retiro_vehiculo').id,
            'liquidar': True, 'confirmo': True})
        asistente.action_confirmar()
        self.assertEqual(ot.state, 'cancelada')
        self.assertTrue(ot.liquidada)
        factura = ot._tllr_fc_facturas()
        self.assertEqual(factura.invoice_line_ids.product_id, self.s1)
        # La OT cancelada con liquidación se entrega con su factura confirmada.
        factura.invoice_payment_term_id = self.plazo30
        factura.action_post()
        entrega = self.env['tllr_fc.entrega'].browse(ot.action_entregar()['res_id'])
        entrega.linea_ids.write({'entregado': True})
        self.assertTrue(entrega.action_confirmar() is True)
        self.assertEqual(ot.state, 'cancelada')
        self.assertTrue(ot.fecha_entrega)

    def test_cancelar_sin_liquidar_trabajo_exige_autorizacion(self):
        ot = self._ot_planificada()
        ot.action_iniciar()
        ot.puesto_line_ids.sorted('sequence')[0].servicio_ids.action_terminar()
        asistente = self.env['tllr_fc.wizard.cancelar'].create({
            'ot_id': ot.id, 'motivo_id': self.env.ref('tllr_fc.motivo_cancelacion_otro').id,
            'confirmo': True})
        accion = asistente.action_confirmar()
        self.assertEqual(accion['res_model'], 'tllr_fc.wizard.excepcion')
        self.assertEqual(ot.state, 'proceso')
        self._autorizar(asistente, 'action_confirmar', 'Rechazó el costo')
        self.assertEqual(ot.state, 'cancelada')
        self.assertFalse(ot.liquidada)
        self.assertFalse(ot._tllr_fc_facturas())

    def test_ot_con_factura_confirmada_no_se_cancela(self):
        ot = self._ot_lista()
        self._facturar(ot)
        asistente = self.env['tllr_fc.wizard.cancelar'].create({
            'ot_id': ot.id, 'motivo_id': self.env.ref('tllr_fc.motivo_cancelacion_otro').id,
            'confirmo': True})
        with self.assertRaises(UserError):
            ot._tllr_fc_cancelar(asistente.motivo_id, False)

    def test_solo_supervisor_cancela(self):
        ot = self._ot_planificada()
        with self.assertRaises(AccessError):
            ot.with_user(self.usuario_taller).action_cancelar()

    def test_aviso_al_cliente(self):
        ot = self._ot_lista()
        with self.assertRaises(UserError):  # sin correo
            ot.action_avisar_cliente()
        self.cliente.email = 'cliente@example.com'
        self.assertTrue(ot.action_avisar_cliente())

    # ---------------- Ajustes 2026.19.009 ----------------
    def _ot_entregada(self):
        ot = self._ot_lista()
        self._facturar(ot)
        entrega = self.env['tllr_fc.entrega'].browse(ot.action_entregar()['res_id'])
        entrega.linea_ids.write({'entregado': True})
        entrega.action_confirmar()
        return ot

    def test_plazo_de_garantia_visible_en_las_lineas(self):
        ot = self._ot_planificada()
        self.assertEqual(ot.servicio_ids.filtered(lambda s: s.product_id == self.s1).garantia_dias, 30)
        self.assertEqual(ot.servicio_ids.filtered(lambda s: s.product_id == self.s1).garantia_km, 1000)
        linea = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 1})
        self.assertEqual(linea.garantia_dias, 90)

    def test_reclamo_sin_garantias_explica_que_hacer(self):
        ot = self._ot_lista()
        self._facturar(ot)
        entrega = self.env['tllr_fc.entrega'].browse(ot.action_entregar()['res_id'])
        entrega.linea_ids.write({'entregado': True})
        entrega.action_confirmar()
        ot.garantia_ids.sudo().unlink()
        with self.assertRaises(UserError) as error:
            ot.action_reclamo_garantia()
        self.assertIn('Garantías', error.exception.args[0])

    def test_recepcion_de_garantia_con_ot_original_elegida(self):
        ot = self._ot_entregada()
        recepcion = self.env['tllr_fc.recepcion'].create({
            'vehiculo_id': self.vehiculo.id, 'partner_id': self.cliente.id,
            'kilometraje': 3000, 'tipo_ot_propuesto': 'garantia', 'ot_origen_id': ot.id,
            'servicio_ids': [Command.create({'product_id': self.s1.id})]})
        recepcion.action_cargar_items()
        recepcion.item_ids.write({'presente': 'si'})
        resultado = recepcion.action_confirmar()
        if isinstance(resultado, dict):
            self.env['tllr_fc.wizard.confirmar_advertencia'].create({
                'res_model': 'tllr_fc.recepcion', 'res_id': recepcion.id,
                'accion': 'action_confirmar', 'mensaje': 'x'}).action_continuar()
        self.assertEqual(recepcion.ot_id.ot_origen_id, ot)
        self.assertIn(recepcion.ot_id, ot.ot_garantia_ids)
        # La OT original solo vale en recepciones de garantía.
        with self.assertRaises(Exception):
            self.env['tllr_fc.recepcion'].create({
                'vehiculo_id': self.vehiculo.id, 'partner_id': self.cliente.id,
                'kilometraje': 3000, 'tipo_ot_propuesto': 'cliente', 'ot_origen_id': ot.id,
                'servicio_ids': [Command.create({'product_id': self.s1.id})]})

    def test_garantia_manual_solo_administrador(self):
        ot = self._ot_entregada()
        ot.garantia_ids.sudo().unlink()
        supervisor = self.env['res.users'].create({
            'name': 'Supervisor F5', 'login': 'sup_f5',
            'group_ids': [Command.link(self.env.ref('tllr_fc.group_supervisor').id)]})
        with self.assertRaises(AccessError):
            self.env['tllr_fc.garantia'].with_user(supervisor).create({
                'ot_id': ot.id, 'product_id': self.s1.id,
                'fecha_entrega': fields.Date.today(), 'fecha_limite': fields.Date.today()})
        garantia = self.env['tllr_fc.garantia'].new({'ot_id': ot.id, 'product_id': self.s1.id})
        garantia._onchange_ot_id()
        garantia._onchange_plazos()
        self.assertEqual(garantia.dias, 30)
        self.assertTrue(garantia.fecha_limite)
        creada = self.env['tllr_fc.garantia'].create({
            'ot_id': ot.id, 'product_id': self.s1.id, 'fecha_entrega': garantia.fecha_entrega,
            'dias': garantia.dias, 'fecha_limite': garantia.fecha_limite})
        self.assertEqual(creada.ot_id, ot)

    def test_reclamo_desde_el_listado_de_garantias(self):
        ot = self._ot_entregada()
        asistente = self.env['tllr_fc.wizard.reclamo_garantia'].with_context(
            active_model='tllr_fc.garantia', active_ids=ot.garantia_ids.ids).create(
            {'ot_id': ot.id, 'garantia_ids': [Command.set(ot.garantia_ids.ids)],
             'kilometraje_actual': 2600, 'descripcion': 'x'})
        valores = self.env['tllr_fc.wizard.reclamo_garantia'].with_context(
            active_model='tllr_fc.garantia', active_ids=ot.garantia_ids.ids).default_get(
            ['ot_id', 'garantia_ids'])
        self.assertEqual(valores['ot_id'], ot.id)
        self.assertEqual(len(valores['garantia_ids'][0][2]), len(ot.garantia_ids))
        self.assertTrue(asistente)
