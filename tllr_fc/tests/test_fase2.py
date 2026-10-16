# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFase2(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        marca = cls.env['tllr_fc.marca'].create({'name': 'Toyota F2'})
        modelo = cls.env['tllr_fc.modelo'].create({'name': 'Hilux F2', 'marca_id': marca.id})
        tipo = cls.env['tllr_fc.tipo_vehiculo'].create({'name': 'Camioneta F2'})
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente Fase 2', 'email': 'c@example.com'})
        cls.vehiculo = cls.env['tllr_fc.vehiculo'].create({
            'name': 'Hilux F2', 'marca_id': marca.id, 'modelo_id': modelo.id,
            'anio': 2020, 'tipo_id': tipo.id, 'partner_id': cls.cliente.id,
            'chapa': 'FAS 002', 'kilometraje': 50000,
        })
        cls.servicio = cls.env['product.product'].create({
            'name': 'Cambio de aceite F2', 'type': 'service',
            'tllr_fc_horas_estandar': 1.5,
        })
        cls.puesto = cls.env['tllr_fc.puesto'].create({
            'name': 'Puesto F2',
            'servicio_ids': [Command.set(cls.servicio.product_tmpl_id.ids)],
            'almacen_id': cls.env['stock.warehouse'].search([], limit=1).id,
        })

    # ---------------- Auxiliares ----------------
    def _turno(self, **extra):
        vals = {
            'partner_id': self.cliente.id,
            'vehiculo_id': self.vehiculo.id,
            'fecha_hora': fields.Datetime.now() + timedelta(days=1),
            'servicio_ids': [Command.create({'product_id': self.servicio.id})],
        }
        vals.update(extra)
        return self.env['tllr_fc.turno'].create(vals)

    def _recepcion(self, **extra):
        vals = {
            'vehiculo_id': self.vehiculo.id,
            'partner_id': self.cliente.id,
            'kilometraje': 51000,
            'servicio_ids': [Command.create({
                'product_id': self.servicio.id, 'observacion': 'Con filtro'})],
        }
        vals.update(extra)
        recepcion = self.env['tllr_fc.recepcion'].create(vals)
        recepcion.action_cargar_items()
        recepcion.item_ids.write({'presente': 'si'})
        return recepcion

    # ---------------- Turnos ----------------
    def test_turno_secuencia_duracion_y_estado(self):
        turno = self._turno()
        self.assertTrue(turno.name.startswith('TUR/'))
        self.assertEqual(turno.state, 'agendado')
        self.assertAlmostEqual(turno.duracion, 1.5)
        self.assertEqual(turno.fecha_fin, turno.fecha_hora + timedelta(hours=1.5))
        turno.action_confirmar()
        self.assertEqual(turno.state, 'confirmado')
        with self.assertRaises(UserError):
            turno.action_confirmar()

    def test_turno_aviso_superposicion_no_bloquea(self):
        base = fields.Datetime.now() + timedelta(days=2)
        t1 = self._turno(fecha_hora=base, puesto_id=self.puesto.id)
        t2 = self._turno(fecha_hora=base + timedelta(minutes=30), puesto_id=self.puesto.id)
        self.assertIn(t1.name, t2.aviso_superposicion)
        t3 = self._turno(fecha_hora=base + timedelta(hours=5), puesto_id=self.puesto.id)
        self.assertFalse(t3.aviso_superposicion)

    def test_turno_vencido_no_asistio_y_reprogramar(self):
        pasado = fields.Datetime.now() - timedelta(days=1)
        t1 = self._turno(fecha_hora=pasado)
        self.assertTrue(t1.vencido)
        self.assertIn(t1, self.env['tllr_fc.turno'].search([('vencido', '=', True)]))
        self.assertNotIn(t1, self.env['tllr_fc.turno'].search([('vencido', '=', False)]))
        t1.action_no_asistio()
        self.assertEqual(t1.state, 'no_asistio')
        self.assertFalse(t1.vencido)

        t2 = self._turno(fecha_hora=pasado)
        accion = t2.action_reprogramar()
        nuevo = self.env['tllr_fc.turno'].browse(accion['res_id'])
        self.assertEqual(t2.state, 'cancelado')
        self.assertEqual(nuevo.state, 'agendado')
        self.assertEqual(nuevo.vehiculo_id, t2.vehiculo_id)
        self.assertEqual(len(nuevo.servicio_ids), 1)
        self.assertGreater(nuevo.fecha_hora, fields.Datetime.now())

    def test_turno_futuro_no_se_marca_no_asistio(self):
        turno = self._turno()
        with self.assertRaises(UserError):
            turno.action_no_asistio()
        with self.assertRaises(UserError):
            turno.action_reprogramar()

    def test_turno_recordatorio_requiere_correo(self):
        turno = self._turno()
        turno.partner_id.email = False
        with self.assertRaises(UserError):
            turno.action_recordatorio()
        turno.partner_id.email = 'c@example.com'
        turno.action_recordatorio()

    # ---------------- Recepción ----------------
    def test_recibir_turno_precarga_recepcion(self):
        turno = self._turno()
        accion = turno.action_recibir()
        recepcion = self.env['tllr_fc.recepcion'].browse(accion['res_id'])
        self.assertEqual(recepcion.state, 'borrador')
        self.assertEqual(recepcion.turno_id, turno)
        self.assertEqual(recepcion.vehiculo_id, self.vehiculo)
        self.assertEqual(recepcion.servicio_ids.product_id, self.servicio)
        # El turno no cambia de estado hasta confirmar la recepción.
        self.assertEqual(turno.state, 'agendado')
        self.assertEqual(turno.recepcion_id, recepcion)
        with self.assertRaises(UserError):
            turno.action_recibir()

    def test_confirmar_recepcion_genera_ot_en_espera(self):
        turno = self._turno()
        turno.action_confirmar()
        recepcion = self._recepcion(turno_id=turno.id)
        self.assertTrue(recepcion.name.startswith('REC/'))
        recepcion.action_confirmar()
        self.assertEqual(recepcion.state, 'confirmada')
        ot = recepcion.ot_id
        self.assertTrue(ot.name.startswith('OT/'))
        self.assertEqual(ot.state, 'espera')
        self.assertEqual(ot.tipo, 'cliente')
        self.assertEqual(ot.vehiculo_id, self.vehiculo)
        self.assertEqual(ot.kilometraje_ingreso, 51000)
        self.assertEqual(ot.servicio_ids.product_id, self.servicio)
        self.assertEqual(ot.servicio_ids.descripcion, 'Con filtro')
        self.assertEqual(self.vehiculo.kilometraje, 51000)
        self.assertEqual(turno.state, 'recibido')

    def test_confirmar_exige_servicios_e_inventario(self):
        sin_servicios = self._recepcion(servicio_ids=[])
        with self.assertRaises(UserError):
            sin_servicios.action_confirmar()
        sin_confirmar = self._recepcion()
        sin_confirmar.item_ids[:1].write({'presente': False})
        with self.assertRaises(UserError):
            sin_confirmar.action_confirmar()
        vacia = self._recepcion()
        vacia.item_ids.unlink()
        with self.assertRaises(UserError):
            vacia.action_confirmar()

    def test_recepcion_confirmada_no_se_edita(self):
        recepcion = self._recepcion()
        recepcion.action_confirmar()
        with self.assertRaises(UserError):
            recepcion.write({'kilometraje': 52000})
        with self.assertRaises(UserError):
            recepcion.write({'servicio_ids': [Command.clear()]})
        with self.assertRaises(UserError):
            recepcion.item_ids[:1].write({'presente': 'no'})
        with self.assertRaises(UserError):
            recepcion.unlink()
        # La mensajería sigue disponible.
        recepcion.message_post(body="Nota posterior")

    def test_advertencia_por_ot_abierta(self):
        primera = self._recepcion()
        primera.action_confirmar()
        segunda = self._recepcion(kilometraje=51500)
        accion = segunda.action_confirmar()
        self.assertEqual(accion['res_model'], 'tllr_fc.wizard.confirmar_advertencia')
        self.assertEqual(segunda.state, 'borrador')
        asistente = self.env['tllr_fc.wizard.confirmar_advertencia'].create({
            'res_model': 'tllr_fc.recepcion', 'res_id': segunda.id,
            'accion': 'action_confirmar', 'mensaje': 'x'})
        asistente.action_continuar()
        self.assertEqual(segunda.state, 'confirmada')
        self.assertEqual(self.env['tllr_fc.ot'].search_count(
            [('vehiculo_id', '=', self.vehiculo.id), ('state', '=', 'espera')]), 2)

    def test_km_menor_exige_excepcion_al_usuario(self):
        usuario = self.env['res.users'].create({
            'name': "Usuario F2", 'login': "usuario_f2",
            'group_ids': [Command.link(self.env.ref('tllr_fc.group_usuario').id)],
        })
        self.vehiculo.kilometraje = 80000
        recepcion = self._recepcion(kilometraje=70000).with_user(usuario)
        accion = recepcion.action_confirmar()
        self.assertEqual(accion['res_model'], 'tllr_fc.wizard.excepcion')
        self.assertEqual(recepcion.state, 'borrador')
        # El usuario de taller no puede autorizar.
        asistente = self.env['tllr_fc.wizard.excepcion'].with_user(usuario).create({
            'res_model': 'tllr_fc.recepcion', 'res_id': recepcion.id,
            'accion': 'action_confirmar', 'grupo_requerido': 'supervisor',
            'motivo': 'Cambio de tablero'})
        with self.assertRaises(AccessError):
            asistente.action_autorizar()
        # El supervisor (administrador por defecto) sí.
        asistente_admin = self.env['tllr_fc.wizard.excepcion'].create({
            'res_model': 'tllr_fc.recepcion', 'res_id': recepcion.id,
            'accion': 'action_confirmar', 'grupo_requerido': 'supervisor',
            'motivo': 'Cambio de tablero'})
        resultado = asistente_admin.action_autorizar()
        # Con la autorización, la única verificación restante es la de OT abierta.
        if isinstance(resultado, dict):
            self.assertEqual(resultado['res_model'], 'tllr_fc.wizard.confirmar_advertencia')
            self.env['tllr_fc.wizard.confirmar_advertencia'].create({
                'res_model': 'tllr_fc.recepcion', 'res_id': recepcion.id,
                'accion': 'action_confirmar', 'mensaje': 'x'}).action_continuar()
        recepcion.invalidate_recordset()
        self.assertEqual(recepcion.state, 'confirmada')

    def test_km_menor_supervisor_solo_advierte(self):
        self.vehiculo.kilometraje = 90000
        recepcion = self._recepcion(kilometraje=85000)
        accion = recepcion.action_confirmar()
        self.assertEqual(accion['res_model'], 'tllr_fc.wizard.confirmar_advertencia')
        self.assertIn('menor', accion['context']['default_mensaje'])

    def test_anular_recepcion_cancela_ot_en_espera_y_libera_turno(self):
        turno = self._turno()
        recepcion = self._recepcion(turno_id=turno.id)
        recepcion.action_confirmar()
        self.assertEqual(turno.state, 'recibido')
        recepcion.action_cancelar()
        self.assertEqual(recepcion.state, 'cancelada')
        self.assertEqual(recepcion.ot_id.state, 'cancelada')
        self.assertTrue(recepcion.ot_id.motivo_cancelacion_id)
        self.assertEqual(turno.state, 'confirmado')
        self.assertFalse(turno.recepcion_id)
        # El turno puede volver a recibirse.
        turno.action_recibir()

    def test_anular_recepcion_con_ot_en_proceso_no_se_permite(self):
        recepcion = self._recepcion()
        recepcion.action_confirmar()
        recepcion.ot_id.state = 'proceso'
        with self.assertRaises(UserError):
            recepcion.action_cancelar()
        self.assertEqual(recepcion.state, 'confirmada')

    def test_turno_ligado_a_una_sola_recepcion(self):
        turno = self._turno()
        self._recepcion(turno_id=turno.id)
        with self.assertRaises(ValidationError):
            self._recepcion(turno_id=turno.id)

    def test_duplicar_copia_e_inicia_el_resto(self):
        turno = self._turno()
        original = self._recepcion(
            turno_id=turno.id, combustible_nivel='1_2', observaciones='Rayón puerta',
            partner_secundario_id=self.env['res.partner'].create({'name': 'Chofer'}).id)
        original.action_confirmar()
        accion = original.action_duplicar()
        copia = self.env['tllr_fc.recepcion'].browse(accion['res_id'])
        self.assertNotEqual(copia.name, original.name)
        self.assertEqual(copia.state, 'borrador')
        self.assertEqual(copia.vehiculo_id, original.vehiculo_id)
        self.assertEqual(copia.partner_secundario_id, original.partner_secundario_id)
        self.assertEqual(copia.kilometraje, original.kilometraje)
        self.assertEqual(copia.combustible_nivel, '1_2')
        self.assertEqual(len(copia.item_ids), len(original.item_ids))
        # Se reinicia lo demás, incluida la confirmación de cada ítem.
        self.assertFalse(copia.turno_id)
        self.assertFalse(copia.ot_id)
        self.assertFalse(copia.servicio_ids)
        self.assertFalse(copia.observaciones)
        self.assertFalse(copia.item_ids.filtered('presente'))

    def test_ot_tipo_solo_lo_cambia_el_supervisor(self):
        usuario = self.env['res.users'].create({
            'name': "Usuario F2b", 'login': "usuario_f2b",
            'group_ids': [Command.link(self.env.ref('tllr_fc.group_usuario').id)],
        })
        recepcion = self._recepcion(tipo_ot_propuesto='interno')
        recepcion.action_confirmar()
        ot = recepcion.ot_id
        self.assertEqual(ot.tipo, 'interno')
        with self.assertRaises(AccessError):
            ot.with_user(usuario).write({'tipo': 'cliente'})
        ot.write({'tipo': 'cliente'})

    def test_comprobante_de_recepcion(self):
        recepcion = self._recepcion()
        recepcion.action_confirmar()
        html, _tipo = self.env['ir.actions.report']._render_qweb_html(
            'tllr_fc.report_recepcion_document', recepcion.ids)
        self.assertIn(recepcion.name.encode(), html)
        self.assertIn(b'FAS002', html)

    def test_conteos_en_vehiculo(self):
        recepcion = self._recepcion()
        recepcion.action_confirmar()
        self.vehiculo.invalidate_recordset()
        self.assertEqual(self.vehiculo.recepcion_count, 1)
        self.assertEqual(self.vehiculo.ot_count, 1)
