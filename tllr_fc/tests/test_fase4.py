# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import TallerCommon


@tagged('post_install', '-at_install')
class TestFase4(TallerCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.herramienta = cls.env['product.product'].create({
            'name': 'Llave F4', 'type': 'consu', 'is_storable': True,
            'tllr_fc_uso_taller': 'herramienta'})

    # ---------------- Auxiliares ----------------
    def _ot_en_proceso(self):
        ot = self._ot_planificada()
        ot.action_iniciar()
        return ot

    def _llegar_a_calidad(self, ot=None):
        ot = ot or self._ot_planificada()
        ot.requiere_qc = True
        if ot.state == 'espera':
            ot.action_iniciar()
        for linea in ot.puesto_line_ids.sorted('sequence'):
            if linea.state == 'activo':
                linea.servicio_ids.filtered(lambda s: s.estado == 'pendiente').action_terminar()
                ot.action_terminar_puesto()
        return ot

    def _autorizar(self, registro, accion, motivo='Prueba'):
        self.env['tllr_fc.wizard.excepcion'].create({
            'res_model': registro._name, 'res_id': registro.id, 'accion': accion,
            'grupo_requerido': 'supervisor', 'motivo': motivo}).action_autorizar()

    # ---------------- Horas ----------------
    def test_horas_copian_funcion_y_costo(self):
        funcion = self.env['tllr_fc.funcion'].create({'name': 'Especialista F4'})
        self.env['tllr_fc.funcion.costo'].create({
            'funcion_id': funcion.id, 'fecha_desde': date(2020, 1, 1), 'costo_hora': 20000})
        self.personal1.funcion_id = funcion
        ot = self._ot_en_proceso()
        hora = self.env['tllr_fc.ot.hora'].create({
            'ot_id': ot.id, **self._sv(ot), 'personal_id': self.personal1.id, 'horas': 2.5})
        self.assertEqual(hora.funcion_id, funcion)
        self.assertAlmostEqual(hora.costo, 50000)
        self.assertAlmostEqual(ot.horas_reales, 2.5)
        self.assertAlmostEqual(ot.costo_horas, 50000)
        # Un cambio posterior de función no altera la línea ya cargada.
        otra = self.env['tllr_fc.funcion'].create({'name': 'Otra F4'})
        self.personal1.funcion_id = otra
        self.assertEqual(hora.funcion_id, funcion)
        with self.assertRaises(UserError):
            hora.funcion_id = otra

    def test_horas_solo_personal_asignado(self):
        ot = self._ot_en_proceso()
        ajeno = self.env['tllr_fc.personal'].create({
            'name': 'Ajeno F4', 'funcion_id': self.personal1.funcion_id.id})
        with self.assertRaises(ValidationError):
            self.env['tllr_fc.ot.hora'].with_user(self.usuario_taller).create({
                'ot_id': ot.id, **self._sv(ot), 'personal_id': ajeno.id, 'horas': 1})
        propia = self.env['tllr_fc.ot.hora'].with_user(self.usuario_taller).create({
            'ot_id': ot.id, **self._sv(ot), 'personal_id': self.personal1.id, 'horas': 1})
        self.assertTrue(propia)
        # 2026.19.027: tampoco el supervisor carga horas de quien no está en la línea.
        with self.assertRaises(ValidationError):
            self.env['tllr_fc.ot.hora'].create({
                'ot_id': ot.id, **self._sv(ot), 'personal_id': ajeno.id, 'horas': 1})

    def test_horas_mas_de_12_en_el_dia_avisa_sin_bloquear(self):
        ot = self._ot_en_proceso()
        hora = self.env['tllr_fc.ot.hora'].create({
            'ot_id': ot.id, **self._sv(ot), 'personal_id': self.personal1.id, 'horas': 8})
        self.assertFalse(hora.aviso)
        segunda = self.env['tllr_fc.ot.hora'].create({
            'ot_id': ot.id, **self._sv(ot), 'personal_id': self.personal1.id, 'horas': 6})
        self.assertAlmostEqual(segunda.horas_dia_persona, 14)
        self.assertIn('14.00', segunda.aviso)
        self.assertTrue(ot.aviso_horas)
        with self.assertRaises(ValidationError):
            self.env['tllr_fc.ot.hora'].create({
                'ot_id': ot.id, **self._sv(ot), 'personal_id': self.personal1.id, 'horas': 0})

    def test_horas_bloqueadas_en_calidad_y_con_ot_detenida(self):
        ot = self._ot_en_proceso()
        motivo = self.env.ref('tllr_fc.motivo_detencion_repuesto')
        ot._tllr_fc_detener(motivo, False)
        with self.assertRaises(UserError):
            self.env['tllr_fc.ot.hora'].create({
                'ot_id': ot.id, **self._sv(ot), 'personal_id': self.personal1.id, 'horas': 1})
        ot.action_reanudar()
        hora = self.env['tllr_fc.ot.hora'].create({
            'ot_id': ot.id, **self._sv(ot), 'personal_id': self.personal1.id, 'horas': 1})
        self._llegar_a_calidad(ot)
        self.assertEqual(ot.state, 'calidad')
        # En calidad solo carga horas el responsable del control (o el supervisor).
        with self.assertRaises(ValidationError):
            self.env['tllr_fc.ot.hora'].with_user(self.usuario_taller).create({
                'ot_id': ot.id, **self._sv(ot), 'personal_id': self.personal1.id, 'horas': 1})
        propia = self.env['tllr_fc.ot.hora'].create({
            'ot_id': ot.id, **self._sv(ot), 'personal_id': ot.control_ids.responsable_id.id, 'horas': 1})
        self.assertTrue(propia)
        ot.control_ids.action_aprobar_todas()
        ot.control_ids.action_confirmar()
        self.assertEqual(ot.state, 'listo')
        with self.assertRaises(UserError):
            hora.horas = 2
        with self.assertRaises(UserError):
            hora.unlink()

    # ---------------- Herramientas dañadas ----------------
    def test_herramienta_danada_no_mueve_stock(self):
        ot = self._ot_en_proceso()
        movimientos = self.env['stock.move'].search_count([('tllr_fc_ot_id', '=', ot.id)])
        linea = self.env['tllr_fc.ot.herramienta_danada'].create({
            'ot_id': ot.id, 'product_id': self.herramienta.id, 'cantidad': 1,
            'motivo': 'Se rompió el dado', 'personal_id': self.personal1.id})
        self.assertEqual(self.env['stock.move'].search_count(
            [('tllr_fc_ot_id', '=', ot.id)]), movimientos)
        self.assertTrue(linea)
        with self.assertRaises(ValidationError):
            self.env['tllr_fc.ot.herramienta_danada'].create({
                'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad': 1, 'motivo': 'x'})

    # ---------------- OT detenida ----------------
    def test_detenida_bloquea_servicios_y_puestos(self):
        ot = self._ot_en_proceso()
        motivo = self.env.ref('tllr_fc.motivo_detencion_repuesto')
        with self.assertRaises(AccessError):
            ot.with_user(self.usuario_taller).action_detener()
        accion = ot.action_detener()
        self.assertEqual(accion['res_model'], 'tllr_fc.wizard.detener')
        self.env['tllr_fc.wizard.detener'].create({
            'ot_id': ot.id, 'motivo_id': motivo.id,
            'fecha_estimada': fields.Date.today() + timedelta(days=2)}).action_detener()
        self.assertTrue(ot.detenida)
        s1 = ot.servicio_ids.filtered(lambda s: s.product_id == self.s1)
        with self.assertRaises(UserError):
            s1.action_terminar()
        with self.assertRaises(UserError):
            ot.action_terminar_puesto()
        with self.assertRaises(UserError):
            ot.action_detener()
        ot.detenida_desde = fields.Datetime.now() - timedelta(days=3)
        self.assertGreaterEqual(ot.dias_detenida_total, 2.9)
        ot.action_reanudar()
        self.assertFalse(ot.detenida)
        self.assertGreaterEqual(ot.dias_detenida, 2.9)
        s1.action_terminar()
        self.assertEqual(s1.estado, 'terminado')

    def test_detenida_se_cierra_al_cancelar(self):
        ot = self._ot()
        ot._tllr_fc_detener(self.env.ref('tllr_fc.motivo_detencion_otro'), False)
        ot.recepcion_id.action_cancelar()
        self.assertEqual(ot.state, 'cancelada')
        self.assertFalse(ot.detenida)

    # ---------------- Control de calidad ----------------
    def test_control_se_crea_al_llegar_a_calidad(self):
        self.s1.product_tmpl_id.tllr_fc_checklist_ids = [
            Command.create({'name': 'Sin fugas'}), Command.create({'name': 'Nivel correcto'})]
        ot = self._llegar_a_calidad()
        self.assertEqual(ot.state, 'calidad')
        control = ot.control_ids
        self.assertEqual(len(control), 1)
        self.assertEqual(control.state, 'borrador')
        self.assertEqual(control.responsable_id, self.responsable)
        self.assertEqual(len(control.linea_ids), 2)
        linea1 = control.linea_ids.filtered(lambda l: l.ot_servicio_id.product_id == self.s1)
        self.assertEqual(linea1.check_ids.mapped('name'), ['Sin fugas', 'Nivel correcto'])
        self.assertTrue(control.name.startswith('QC/'))

    def test_control_aprobado_deja_la_ot_lista(self):
        ot = self._llegar_a_calidad()
        control = ot.control_ids
        with self.assertRaises(UserError):  # sin resultados
            control.action_confirmar()
        control.action_aprobar_todas()
        control.action_confirmar()
        self.assertEqual(control.state, 'aprobado')
        self.assertEqual(ot.state, 'listo')
        with self.assertRaises(UserError):  # el control confirmado no se modifica
            control.comentarios = 'x'
        with self.assertRaises(UserError):
            control.linea_ids[:1].resultado = 'rechazado'

    def test_control_solo_supervisor_confirma(self):
        ot = self._llegar_a_calidad()
        control = ot.control_ids
        control.action_aprobar_todas()
        with self.assertRaises(AccessError):
            control.with_user(self.usuario_taller).action_confirmar()

    def test_responsable_del_control_entre_el_personal_exige_excepcion(self):
        ot = self._planificada_con_responsable_en_puesto()
        control = ot.control_ids
        control.action_aprobar_todas()
        accion = control.action_confirmar()
        self.assertEqual(accion['res_model'], 'tllr_fc.wizard.excepcion')
        self.assertEqual(control.state, 'borrador')
        self._autorizar(control, 'action_confirmar', 'No hay otra persona')
        self.assertEqual(control.state, 'aprobado')
        self.assertEqual(ot.state, 'listo')

    def _planificada_con_responsable_en_puesto(self):
        ot = self._ot_planificada()
        ot.requiere_qc = True
        ot.responsable_id = self.personal1
        self._autorizar(ot, 'action_iniciar')
        for linea in ot.puesto_line_ids.sorted('sequence'):
            linea.servicio_ids.action_terminar()
            ot.action_terminar_puesto()
        return ot

    def test_control_rechazado_devuelve_a_proceso_y_se_reenvia(self):
        ot = self._llegar_a_calidad()
        control = ot.control_ids
        l1 = control.linea_ids.filtered(lambda l: l.ot_servicio_id.product_id == self.s1)
        l2 = control.linea_ids - l1
        l1.resultado = 'rechazado'
        l2.resultado = 'aprobado'
        control.action_confirmar()
        self.assertEqual(control.state, 'rechazado')
        self.assertEqual(ot.state, 'proceso')
        s1 = ot.servicio_ids.filtered(lambda s: s.product_id == self.s1)
        self.assertEqual(s1.estado, 'pendiente')
        lineas = ot.puesto_line_ids.sorted('sequence')
        # Se reactiva el primer puesto con rechazo; el siguiente repite el recorrido.
        self.assertEqual([l.state for l in lineas], ['activo', 'pendiente'])
        # Se corrige y se reenvía: nuevo control, el historial se conserva.
        s1.action_terminar()
        ot.action_terminar_puesto()
        ot.action_terminar_puesto()
        self.assertEqual(ot.state, 'calidad')
        self.assertEqual(len(ot.control_ids), 2)
        nuevo = ot.control_ids.filtered(lambda c: c.state == 'borrador')
        self.assertEqual(len(nuevo), 1)
        nuevo.action_aprobar_todas()
        nuevo.action_confirmar()
        self.assertEqual(ot.state, 'listo')
        self.assertEqual(ot.control_count, 2)

    def test_servicio_no_realizado_no_entra_al_control(self):
        ot = self._ot_planificada()
        ot.requiere_qc = True
        ot.action_iniciar()
        s1 = ot.servicio_ids.filtered(lambda s: s.product_id == self.s1)
        s1.action_no_realizado()
        self._autorizar(s1, 'action_no_realizado', 'No aplica')
        ot.action_terminar_puesto()
        ot.servicio_ids.filtered(lambda s: s.estado == 'pendiente').action_terminar()
        ot.action_terminar_puesto()
        control = ot.control_ids
        self.assertEqual(control.linea_ids.ot_servicio_id.product_id, self.s2)

    def test_sin_control_requerido_pasa_directo_a_listo(self):
        ot = self._ot_planificada()
        ot.action_iniciar()
        for linea in ot.puesto_line_ids.sorted('sequence'):
            linea.servicio_ids.action_terminar()
            ot.action_terminar_puesto()
        self.assertEqual(ot.state, 'listo')
        self.assertFalse(ot.control_ids)

    def test_ot_en_calidad_no_admite_cambios(self):
        ot = self._llegar_a_calidad()
        with self.assertRaises(UserError):
            self.env['tllr_fc.ot.servicio'].create({'ot_id': ot.id, 'product_id': self.s3.id})
        with self.assertRaises(UserError):
            self.env['tllr_fc.ot.producto'].create({
                'ot_id': ot.id, 'product_id': self.repuesto.id})

    # ---------------- Adicionales y aprobación ----------------
    def _adicional(self, ot, usuario=None):
        modelo = self.env['tllr_fc.ot.servicio']
        if usuario:
            modelo = modelo.with_user(usuario)
        return modelo.create({'ot_id': ot.id, 'product_id': self.s3.id})

    def test_adicional_queda_pendiente_solo_en_ot_de_cliente(self):
        ot = self._ot_en_proceso()
        adicional = self._adicional(ot, self.usuario_taller)
        self.assertTrue(adicional.adicional)
        self.assertEqual(adicional.state_aprobacion, 'pendiente')
        self.assertEqual(ot.adicionales_pendientes, 1)
        interna = self._ot_planificada()
        interna.tipo = 'interno'
        interna.action_iniciar()
        self.assertEqual(self._adicional(interna).state_aprobacion, 'no_requiere')
        # Los servicios de la recepción no son adicionales.
        self.assertFalse(ot.servicio_ids.filtered(lambda s: s.product_id == self.s1).adicional)

    def test_adicional_pendiente_bloquea_ejecucion_si_es_obligatoria(self):
        ot = self._ot_en_proceso()
        ot.company_id.tllr_fc_aprobacion_adicional = 'obligatoria'
        adicional = self._adicional(ot)
        linea = ot.puesto_line_ids.sorted('sequence')[0]
        adicional.puesto_line_id = linea  # supervisor: aunque el puesto no lo realice
        with self.assertRaises(UserError):
            adicional.action_terminar()
        rep = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 2})
        self.assertEqual(rep.state_aprobacion, 'pendiente')
        with self.assertRaises(UserError):
            rep.cantidad_utilizada = 1
        # Autorización del supervisor sin aprobación del cliente.
        adicional.action_autorizar_sin_aprobacion()
        self._autorizar(adicional, 'action_autorizar_sin_aprobacion', 'Urgente')
        self.assertEqual(adicional.state_aprobacion, 'autorizado')
        adicional.action_terminar()
        self.assertEqual(adicional.estado, 'terminado')

    def test_adicional_recomendada_no_bloquea(self):
        ot = self._ot_en_proceso()
        ot.company_id.tllr_fc_aprobacion_adicional = 'recomendada'
        adicional = self._adicional(ot)
        adicional.puesto_line_id = ot.puesto_line_ids.sorted('sequence')[0]
        adicional.action_terminar()
        self.assertEqual(adicional.estado, 'terminado')
        ot.company_id.tllr_fc_aprobacion_adicional = 'obligatoria'

    def test_registrar_aprobacion_aprobada(self):
        ot = self._ot_en_proceso()
        adicional = self._adicional(ot)
        rep = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 1})
        accion = ot.action_registrar_aprobacion()
        self.assertEqual(accion['res_model'], 'tllr_fc.wizard.aprobacion')
        asistente = self.env['tllr_fc.wizard.aprobacion'].with_context(
            default_ot_id=ot.id).create({
                'ot_id': ot.id, 'persona': 'María (esposa)', 'medio': 'telefono'})
        self.assertEqual(asistente.servicio_ids, adicional)
        self.assertEqual(asistente.producto_ids, rep)
        with self.assertRaises(AccessError):
            asistente.with_user(self.usuario_taller).action_registrar()
        asistente.action_registrar()
        self.assertEqual(adicional.state_aprobacion, 'aprobado')
        self.assertEqual(rep.state_aprobacion, 'aprobado')
        self.assertEqual(ot.adicionales_pendientes, 0)
        self.assertEqual(ot.aprobacion_ids.persona, 'María (esposa)')
        adicional.puesto_line_id = ot.puesto_line_ids.sorted('sequence')[0]
        adicional.action_terminar()
        rep.cantidad_utilizada = 1
        self.assertEqual(rep.cantidad_consumida, 1)

    def test_registrar_aprobacion_rechazada_quita_las_lineas(self):
        ot = self._ot_en_proceso()
        adicional = self._adicional(ot)
        asistente = self.env['tllr_fc.wizard.aprobacion'].with_context(
            default_ot_id=ot.id).create({
                'ot_id': ot.id, 'persona': 'Cliente', 'estado': 'rechazado'})
        asistente.action_registrar()
        self.assertFalse(adicional.exists())
        self.assertEqual(ot.aprobacion_ids.estado, 'rechazado')
        self.assertIn('RECHAZADOS', ot.message_ids[0].body)

    def test_estado_de_aprobacion_no_se_escribe_directo(self):
        ot = self._ot_en_proceso()
        adicional = self._adicional(ot)
        with self.assertRaises(UserError):
            adicional.state_aprobacion = 'aprobado'

    # ---------------- Menú Maestros ----------------
    def test_menu_maestros_agrupado(self):
        def padre(xml_id):
            return self.env.ref('tllr_fc.' + xml_id).parent_id
        veh = self.env.ref('tllr_fc.menu_tllr_fc_maestros_vehiculos')
        rrhh = self.env.ref('tllr_fc.menu_tllr_fc_maestros_rrhh')
        prod = self.env.ref('tllr_fc.menu_tllr_fc_maestros_productos')
        for contenedor in (veh, rrhh, prod):
            self.assertEqual(contenedor.parent_id, self.env.ref('tllr_fc.menu_tllr_fc_maestros'))
        self.assertEqual([veh.name, rrhh.name, prod.name], ["Vehículos", "RRHH", "Productos"])
        esperado = {
            veh: ['menu_tllr_fc_vehiculos', 'menu_tllr_fc_marcas', 'menu_tllr_fc_modelos',
                  'menu_tllr_fc_tipos_vehiculo'],
            rrhh: ['menu_tllr_fc_personal', 'menu_tllr_fc_funciones', 'menu_tllr_fc_puestos'],
            prod: ['menu_tllr_fc_items_inventario', 'menu_tllr_fc_servicios',
                   'menu_tllr_fc_repuestos', 'menu_tllr_fc_herramientas'],
        }
        for contenedor, hijos in esperado.items():
            ordenados = contenedor.child_id.sorted('sequence')
            self.assertEqual(
                ordenados.ids, [self.env.ref('tllr_fc.' + h).id for h in hijos], contenedor.name)
