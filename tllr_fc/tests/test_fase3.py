# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import TallerCommon


@tagged('post_install', '-at_install')
class TestFase3(TallerCommon):

    # ---------------- Precios y descuentos ----------------
    def test_servicios_nacen_con_precio_de_ficha_y_descuento_del_contacto(self):
        ot = self._ot()
        serv = ot.servicio_ids.filtered(lambda s: s.product_id == self.s1)
        self.assertEqual(serv.precio_unitario, 100000)
        self.assertEqual(serv.descuento, 10.0)
        self.assertAlmostEqual(serv.subtotal, 90000)
        self.assertEqual(serv.estado, 'pendiente')
        self.assertAlmostEqual(ot.total_servicios, 90000 + 45000)
        self.assertAlmostEqual(ot.horas_estandar, 1.5)

    def test_precio_y_descuento_solo_supervisor(self):
        ot = self._ot()
        serv = ot.servicio_ids[:1]
        with self.assertRaises(AccessError):
            serv.with_user(self.usuario_taller).write({'precio_unitario': 1})
        with self.assertRaises(AccessError):
            serv.with_user(self.usuario_taller).write({'descuento': 50})
        # En la creación, los valores del usuario se ignoran.
        nuevo = self.env['tllr_fc.ot.servicio'].with_user(self.usuario_taller).create({
            'ot_id': ot.id, 'product_id': self.s3.id, 'precio_unitario': 1, 'descuento': 90})
        self.assertEqual(nuevo.precio_unitario, 10000)
        self.assertEqual(nuevo.descuento, 10.0)
        serv.write({'precio_unitario': 120000})
        self.assertEqual(serv.precio_unitario, 120000)

    def test_estado_del_servicio_no_se_escribe_directo(self):
        ot = self._ot()
        with self.assertRaises(UserError):
            ot.servicio_ids[:1].write({'estado': 'terminado'})

    # ---------------- Inicio de la OT ----------------
    def test_iniciar_exige_responsable_puestos_y_personal(self):
        ot = self._ot()
        with self.assertRaises(UserError):  # sin responsable
            ot.action_iniciar()
        ot.responsable_id = self.responsable
        with self.assertRaises(UserError):  # sin puestos
            ot.action_iniciar()
        linea = self.env['tllr_fc.ot.puesto'].create({
            'ot_id': ot.id, 'puesto_id': self.puesto1.id})
        with self.assertRaises(UserError):  # puesto sin personal
            ot.action_iniciar()
        linea.personal_ids = self.personal1
        with self.assertRaises(UserError):  # el servicio 2 no tiene puesto
            ot.action_iniciar()
        self.env['tllr_fc.ot.puesto'].create({
            'ot_id': ot.id, 'puesto_id': self.puesto2.id,
            'personal_ids': [Command.set(self.personal2.ids)]})
        ot.action_iniciar()
        self.assertEqual(ot.state, 'proceso')

    def test_servicios_se_asocian_al_puesto_que_los_realiza(self):
        ot = self._ot_planificada()
        s1 = ot.servicio_ids.filtered(lambda s: s.product_id == self.s1)
        s2 = ot.servicio_ids.filtered(lambda s: s.product_id == self.s2)
        self.assertEqual(s1.puesto_line_id.puesto_id, self.puesto1)
        self.assertEqual(s2.puesto_line_id.puesto_id, self.puesto2)

    def test_responsable_no_puede_ser_personal_sin_excepcion(self):
        ot = self._ot_planificada()
        ot.responsable_id = self.personal1
        accion = ot.action_iniciar()
        self.assertEqual(accion['res_model'], 'tllr_fc.wizard.excepcion')
        self.assertEqual(ot.state, 'espera')
        self.env['tllr_fc.wizard.excepcion'].create({
            'res_model': 'tllr_fc.ot', 'res_id': ot.id, 'accion': 'action_iniciar',
            'grupo_requerido': 'supervisor', 'motivo': 'Es el único mecánico'}).action_autorizar()
        self.assertEqual(ot.state, 'proceso')

    def test_responsable_y_tipo_solo_supervisor(self):
        ot = self._ot()
        with self.assertRaises(AccessError):
            ot.with_user(self.usuario_taller).write({'responsable_id': self.responsable.id})
        with self.assertRaises(AccessError):
            ot.with_user(self.usuario_taller).write({'requiere_qc': True})

    # ---------------- Recorrido por los puestos ----------------
    def test_un_solo_puesto_activo_y_recorrido(self):
        ot = self._ot_planificada()
        ot.action_iniciar()
        l1, l2 = ot.puesto_line_ids.sorted('sequence')
        self.assertEqual((l1.state, l2.state), ('activo', 'pendiente'))
        self.assertEqual(ot.puesto_activo_id, self.puesto1)
        with self.assertRaises(ValidationError):
            l2.with_context(tllr_fc_permitir_write=True).state = 'activo'
        with self.assertRaises(UserError):  # servicios pendientes
            ot.action_terminar_puesto()
        self._terminar_servicios(l1)
        ot.action_terminar_puesto()
        self.assertEqual((l1.state, l2.state), ('terminado', 'activo'))
        self.assertEqual(ot.puesto_activo_id, self.puesto2)
        self.assertEqual(ot.state, 'proceso')
        self._terminar_servicios(l2)
        ot.action_terminar_puesto()
        self.assertEqual(ot.state, 'listo')
        self.assertFalse(ot.puesto_activo_id)

    def test_control_de_calidad_segun_ajuste_o_marca(self):
        ot = self._ot_planificada()
        ot.requiere_qc = True
        ot.action_iniciar()
        for linea in ot.puesto_line_ids.sorted('sequence'):
            self._terminar_servicios(linea)
            ot.action_terminar_puesto()
        self.assertEqual(ot.state, 'calidad')
        # Ajuste de la compañía por tipo
        ot2 = self._ot_planificada()
        ot2.company_id.tllr_fc_qc_cliente = True
        with self.assertRaises(UserError):
            ot2.requiere_qc = False
        ot2.action_iniciar()
        for linea in ot2.puesto_line_ids.sorted('sequence'):
            self._terminar_servicios(linea)
            ot2.action_terminar_puesto()
        self.assertEqual(ot2.state, 'calidad')
        ot2.company_id.tllr_fc_qc_cliente = False

    def test_terminar_servicio_solo_personal_del_puesto_activo(self):
        ot = self._ot_planificada()
        ot.action_iniciar()
        s1 = ot.servicio_ids.filtered(lambda s: s.product_id == self.s1)
        s2 = ot.servicio_ids.filtered(lambda s: s.product_id == self.s2)
        with self.assertRaises(UserError):  # puesto 2 todavía no está activo
            s2.action_terminar()
        s1.with_user(self.usuario_taller).action_terminar()
        self.assertEqual(s1.estado, 'terminado')
        self.assertEqual(s1.terminado_por_id, self.usuario_taller)
        self.assertTrue(s1.fecha_terminado)

    def test_personal_ajeno_no_termina_servicios(self):
        ot = self._ot_planificada()
        ot.action_iniciar()
        ajeno = self.env['res.users'].create({
            'name': "Ajeno F3", 'login': "ajeno_f3",
            'group_ids': [Command.link(self.env.ref('tllr_fc.group_usuario').id)]})
        s1 = ot.servicio_ids.filtered(lambda s: s.product_id == self.s1)
        with self.assertRaises(AccessError):
            s1.with_user(ajeno).action_terminar()

    def test_servicio_no_realizado_con_motivo_y_sin_factura(self):
        ot = self._ot_planificada()
        ot.action_iniciar()
        s1 = ot.servicio_ids.filtered(lambda s: s.product_id == self.s1)
        accion = s1.action_no_realizado()
        self.assertEqual(accion['res_model'], 'tllr_fc.wizard.excepcion')
        self.env['tllr_fc.wizard.excepcion'].create({
            'res_model': 'tllr_fc.ot.servicio', 'res_id': s1.id,
            'accion': 'action_no_realizado', 'grupo_requerido': 'supervisor',
            'motivo': 'El cliente lo rechazó'}).action_autorizar()
        self.assertEqual(s1.estado, 'no_realizado')
        self.assertEqual(s1.motivo_no_realizado, 'El cliente lo rechazó')
        self.assertEqual(s1.subtotal, 0)
        self.assertEqual(s1.horas_estandar, 0)
        # No bloquea terminar el puesto.
        ot.action_terminar_puesto()
        self.assertEqual(ot.puesto_activo_id, self.puesto2)
        with self.assertRaises(AccessError):
            s1.with_user(self.usuario_taller).action_no_realizado()

    def test_retroceder_puesto_exige_supervisor_y_motivo(self):
        ot = self._ot_planificada()
        ot.action_iniciar()
        with self.assertRaises(UserError):  # no hay puesto anterior
            ot.action_retroceder_puesto()
        l1, l2 = ot.puesto_line_ids.sorted('sequence')
        self._terminar_servicios(l1)
        ot.action_terminar_puesto()
        with self.assertRaises(AccessError):
            ot.with_user(self.usuario_taller).action_retroceder_puesto()
        accion = ot.action_retroceder_puesto()
        self.assertEqual(accion['res_model'], 'tllr_fc.wizard.excepcion')
        self.env['tllr_fc.wizard.excepcion'].create({
            'res_model': 'tllr_fc.ot', 'res_id': ot.id,
            'accion': 'action_retroceder_puesto', 'grupo_requerido': 'supervisor',
            'motivo': 'Fuga de aceite'}).action_autorizar()
        self.assertEqual((l1.state, l2.state), ('activo', 'pendiente'))
        self.assertEqual(l1.servicio_ids.estado, 'pendiente')
        self.assertEqual(ot.state, 'proceso')

    # ---------------- Tablero ----------------
    def test_arrastre_hacia_el_siguiente_puesto(self):
        ot = self._ot_planificada()
        ot.action_iniciar()
        l1, l2 = ot.puesto_line_ids.sorted('sequence')
        with self.assertRaises(UserError):  # servicios del puesto actual pendientes
            ot.write({'puesto_activo_id': self.puesto2.id})
        self._terminar_servicios(l1)
        ot.write({'puesto_activo_id': self.puesto2.id})
        self.assertEqual((l1.state, l2.state), ('terminado', 'activo'))
        self.assertEqual(ot.puesto_activo_id, self.puesto2)
        self.assertEqual(ot.state, 'proceso')

    def test_arrastre_invalido(self):
        ot = self._ot_planificada()
        ot.action_iniciar()
        l1, l2 = ot.puesto_line_ids.sorted('sequence')
        self._terminar_servicios(l1)
        ot.action_terminar_puesto()
        with self.assertRaises(UserError):  # hacia atrás
            ot.write({'puesto_activo_id': self.puesto1.id})
        with self.assertRaises(UserError):  # «Sin puesto»
            ot.write({'puesto_activo_id': False})
        otro = self.env['tllr_fc.puesto'].create({
            'name': 'Otro F3', 'almacen_id': self.almacen.id,
            'servicio_ids': [Command.set(self.s3.product_tmpl_id.ids)]})
        with self.assertRaises(UserError):  # puesto que no es el siguiente
            ot.write({'puesto_activo_id': otro.id})
        with self.assertRaises(AccessError):
            ot.with_user(self.usuario_taller).write({'puesto_activo_id': self.puesto1.id})
        self.assertEqual(ot.puesto_activo_id, self.puesto2)
        self.assertEqual(ot.state, 'proceso')

    def test_arrastre_solo_con_ot_en_proceso(self):
        ot = self._ot_planificada()
        with self.assertRaises(UserError):
            ot.write({'puesto_activo_id': self.puesto2.id})

    def test_tablero_muestra_todos_los_puestos(self):
        puestos = self.env['tllr_fc.ot']._read_group_puesto_activo_id(
            self.env['tllr_fc.puesto'], [])
        self.assertIn(self.puesto1, puestos)
        self.assertIn(self.puesto2, puestos)

    # ---------------- Pertenencia de servicios ----------------
    def test_puesto_que_no_realiza_el_servicio(self):
        ot = self._ot_planificada()
        s1 = ot.servicio_ids.filtered(lambda s: s.product_id == self.s1)
        l2 = ot.puesto_line_ids.filtered(lambda l: l.puesto_id == self.puesto2)
        with self.assertRaises(ValidationError):
            s1.with_user(self.usuario_taller).write({'puesto_line_id': l2.id})
        # El supervisor puede, y queda registrado.
        s1.write({'puesto_line_id': l2.id})
        self.assertEqual(s1.puesto_line_id, l2)

    # ---------------- Bloqueos de edición ----------------
    def test_ot_terminada_no_admite_cambios(self):
        ot = self._ot_planificada()
        ot.action_iniciar()
        for linea in ot.puesto_line_ids.sorted('sequence'):
            self._terminar_servicios(linea)
            ot.action_terminar_puesto()
        self.assertEqual(ot.state, 'listo')
        with self.assertRaises(UserError):
            self.env['tllr_fc.ot.servicio'].create({'ot_id': ot.id, 'product_id': self.s3.id})
        with self.assertRaises(UserError):
            self.env['tllr_fc.ot.producto'].create({
                'ot_id': ot.id, 'product_id': self.repuesto.id})

    def test_puesto_no_pendiente_no_se_elimina(self):
        ot = self._ot_planificada()
        ot.action_iniciar()
        activo = ot.puesto_line_ids.filtered(lambda l: l.state == 'activo')
        with self.assertRaises(UserError):
            activo.unlink()
        pendiente = ot.puesto_line_ids.filtered(lambda l: l.state == 'pendiente')
        pendiente.unlink()
        self.assertEqual(len(ot.puesto_line_ids), 1)

    # ---------------- Repuestos, insumos y accesorios ----------------
    def _linea_producto(self, ot, producto=None, **extra):
        vals = {'ot_id': ot.id, 'product_id': (producto or self.repuesto).id,
                'cantidad_reservada': 3}
        vals.update(extra)
        return self.env['tllr_fc.ot.producto'].create(vals)

    def _quant_libre(self, producto):
        quants = self.env['stock.quant'].search([
            ('product_id', '=', producto.id),
            ('location_id', '=', self.almacen.lot_stock_id.id)])
        return sum(quants.mapped('quantity')), sum(quants.mapped('reserved_quantity'))

    def test_producto_precio_descuento_y_facturacion(self):
        ot = self._ot()
        rep = self._linea_producto(ot)
        ins = self._linea_producto(ot, self.insumo, cantidad_reservada=1)
        self.assertEqual(rep.precio_unitario, 30000)
        self.assertEqual(rep.descuento, 10.0)
        self.assertTrue(rep.facturable)
        self.assertEqual(rep.uso, 'repuesto')
        self.assertFalse(ins.facturable)
        self.assertEqual(ins.subtotal, 0)
        self.assertEqual(ins.precio_unitario, 0)
        with self.assertRaises(ValidationError):  # «No facturar» no aplica al insumo
            ins.no_facturar = True
        rep.no_facturar = True
        self.assertFalse(rep.facturable)
        self.assertEqual(rep.subtotal, 0)
        with self.assertRaises(AccessError):
            rep.with_user(self.usuario_taller).write({'precio_unitario': 1})

    def test_producto_no_repuesto_no_se_acepta(self):
        ot = self._ot()
        herramienta = self.env['product.product'].create({
            'name': 'Llave F3', 'type': 'consu', 'is_storable': True,
            'tllr_fc_uso_taller': 'herramienta'})
        with self.assertRaises(ValidationError):
            self._linea_producto(ot, herramienta)

    def test_reserva_de_stock_real(self):
        ot = self._ot()
        total, reservado = self._quant_libre(self.repuesto)
        self.assertEqual((total, reservado), (10, 0))
        linea = self._linea_producto(ot)
        self.assertEqual(self._quant_libre(self.repuesto), (10, 3))
        self.assertEqual(linea.reserva_estado, 'ok')
        linea.cantidad_reservada = 5
        self.assertEqual(self._quant_libre(self.repuesto), (10, 5))
        linea.unlink()
        self.assertEqual(self._quant_libre(self.repuesto), (10, 0))

    def test_reserva_parcial_sin_stock(self):
        ot = self._ot()
        linea = self._linea_producto(ot, cantidad_reservada=15)
        self.assertEqual(linea.reserva_estado, 'parcial')
        linea.unlink()

    def test_consumo_de_stock_y_costo(self):
        ot = self._ot_planificada()
        linea = self._linea_producto(ot, cantidad_reservada=4)
        with self.assertRaises(UserError):  # solo con la OT en proceso
            linea.cantidad_utilizada = 1
        ot.action_iniciar()
        linea.cantidad_utilizada = 3
        self.assertEqual(linea.cantidad_consumida, 3)
        total, reservado = self._quant_libre(self.repuesto)
        self.assertEqual((total, reservado), (7, 1))  # 3 consumidos, 1 reservado
        self.assertAlmostEqual(linea.costo, 3 * 12000)
        self.assertAlmostEqual(linea.subtotal, 3 * 30000 * 0.9)
        with self.assertRaises(UserError):  # no se reduce lo ya descontado
            linea.cantidad_utilizada = 2
        with self.assertRaises(UserError):  # no se elimina lo ya consumido
            linea.unlink()
        with self.assertRaises(ValidationError):  # no más de lo reservado
            linea.cantidad_utilizada = 5
        # Al terminar la OT, lo no usado vuelve a quedar libre.
        for puesto in ot.puesto_line_ids.sorted('sequence'):
            self._terminar_servicios(puesto)
            ot.action_terminar_puesto()
        self.assertEqual(ot.state, 'listo')
        self.assertEqual(self._quant_libre(self.repuesto), (7, 0))

    def test_consumo_sin_stock_suficiente(self):
        ot = self._ot_planificada()
        linea = self._linea_producto(ot, cantidad_reservada=12)
        ot.action_iniciar()
        with self.assertRaises(UserError):
            linea.cantidad_utilizada = 12
        self.assertEqual(linea.cantidad_consumida, 0)

    def test_provisto_por_el_cliente_no_mueve_stock(self):
        ot = self._ot()
        linea = self._linea_producto(ot, provisto_cliente=True)
        self.assertEqual(self._quant_libre(self.repuesto), (10, 0))
        self.assertFalse(linea.facturable)

    def test_consumo_con_lote(self):
        lote_producto = self.env['product.product'].create({
            'name': 'Aceite con lote F3', 'type': 'consu', 'is_storable': True,
            'tracking': 'lot', 'list_price': 20000, 'tllr_fc_uso_taller': 'insumo_facturable'})
        lote = self.env['stock.lot'].create({
            'name': 'LOTE-F3', 'product_id': lote_producto.id,
            'company_id': self.env.company.id})
        self.env['stock.quant']._update_available_quantity(
            lote_producto, self.almacen.lot_stock_id, 6, lot_id=lote)
        ot = self._ot_planificada()
        linea = self._linea_producto(ot, lote_producto, cantidad_reservada=4, lote_id=lote.id)
        ot.action_iniciar()
        linea.cantidad_utilizada = 2
        quant = self.env['stock.quant'].search([
            ('product_id', '=', lote_producto.id), ('lot_id', '=', lote.id),
            ('location_id', '=', self.almacen.lot_stock_id.id)])
        self.assertEqual(sum(quant.mapped('quantity')), 4)

    def test_cancelar_por_recepcion_libera_reservas(self):
        ot = self._ot()
        self._linea_producto(ot)
        self.assertEqual(self._quant_libre(self.repuesto), (10, 3))
        ot.recepcion_id.action_cancelar()
        self.assertEqual(ot.state, 'cancelada')
        self.assertEqual(self._quant_libre(self.repuesto), (10, 0))

    # ---------------- Turnos: botones del calendario ----------------
    def test_calendario_de_turnos_usa_la_vista_personalizada(self):
        vista = self.env.ref('tllr_fc.view_tllr_fc_turno_calendar')
        self.assertIn('js_class="tllr_fc_turno_calendar"', vista.arch_db)
        self.assertIn('name="vencido"', vista.arch_db)
