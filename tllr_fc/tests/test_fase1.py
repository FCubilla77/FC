# -*- coding: utf-8 -*-
from datetime import date

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFase1(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.marca = cls.env['tllr_fc.marca'].create({'name': 'Toyota'})
        cls.modelo = cls.env['tllr_fc.modelo'].create(
            {'name': 'Hilux', 'marca_id': cls.marca.id})
        cls.tipo = cls.env['tllr_fc.tipo_vehiculo'].create({'name': 'Camioneta'})
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente Taller'})

    def _vehiculo(self, **extra):
        vals = {
            'name': "Hilux blanca",
            'marca_id': self.marca.id,
            'modelo_id': self.modelo.id,
            'anio': 2020,
            'tipo_id': self.tipo.id,
            'partner_id': self.cliente.id,
            'chapa': "abc 123",
        }
        vals.update(extra)
        return self.env['tllr_fc.vehiculo'].create(vals)

    # ---------------- Vehículo ----------------
    def test_vehiculo_normaliza_chapa_y_asigna_codigo(self):
        vehiculo = self._vehiculo()
        self.assertEqual(vehiculo.chapa, "ABC123")
        self.assertTrue(vehiculo.codigo.startswith("VEH/"))
        self.assertEqual(vehiculo.display_name, "[ABC123] Hilux blanca")

    def test_chapa_unica_por_compania(self):
        self._vehiculo()
        with self.assertRaises(ValidationError):
            self._vehiculo(chapa="ABC 123")

    def test_chapa_repetida_en_otra_compania(self):
        self._vehiculo()
        otra = self.env['res.company'].create({'name': "Otra compañía Taller"})
        marca = self.env['tllr_fc.marca'].create({'name': 'Toyota', 'company_id': otra.id})
        modelo = self.env['tllr_fc.modelo'].create(
            {'name': 'Hilux', 'marca_id': marca.id, 'company_id': otra.id})
        tipo = self.env['tllr_fc.tipo_vehiculo'].create(
            {'name': 'Camioneta', 'company_id': otra.id})
        vehiculo = self._vehiculo(
            company_id=otra.id, marca_id=marca.id, modelo_id=modelo.id, tipo_id=tipo.id)
        self.assertEqual(vehiculo.chapa, "ABC123")

    def test_chasis_opcional_y_unico(self):
        self._vehiculo(chapa="AAA111")
        self._vehiculo(chapa="AAA112")  # sin chasis: permitido repetir el vacío
        self._vehiculo(chapa="AAA113", chasis="vin001")
        with self.assertRaises(ValidationError):
            self._vehiculo(chapa="AAA114", chasis="VIN001")

    def test_rango_del_anio(self):
        with self.assertRaises(ValidationError):
            self._vehiculo(anio=1900)
        with self.assertRaises(ValidationError):
            self._vehiculo(anio=date.today().year + 5)

    def test_modelo_debe_ser_de_la_marca(self):
        otra_marca = self.env['tllr_fc.marca'].create({'name': 'Ford'})
        with self.assertRaises(ValidationError):
            self._vehiculo(marca_id=otra_marca.id)

    def test_cambio_de_propietario_queda_en_el_chatter(self):
        vehiculo = self._vehiculo()
        nuevo = self.env['res.partner'].create({'name': 'Nuevo propietario'})
        vehiculo.write({'partner_id': nuevo.id})
        seguimiento = vehiculo.message_ids.tracking_value_ids.filtered(
            lambda t: t.field_id.name == 'partner_id')
        self.assertTrue(seguimiento)

    def test_contacto_cuenta_vehiculos(self):
        self._vehiculo()
        self.cliente.invalidate_recordset()
        self.assertEqual(self.cliente.tllr_fc_vehiculo_count, 1)

    # ---------------- Catálogos ----------------
    def test_marca_unica_por_compania(self):
        with self.assertRaises(ValidationError):
            self.env['tllr_fc.marca'].create({'name': 'toyota'})

    def test_modelo_unico_por_marca(self):
        with self.assertRaises(ValidationError):
            self.env['tllr_fc.modelo'].create({'name': 'HILUX', 'marca_id': self.marca.id})

    def test_datos_iniciales(self):
        self.assertTrue(self.env.ref('tllr_fc.motivo_detencion_aprobacion_cliente'))
        items = self.env['tllr_fc.item_inventario'].search([('company_id', '=', False)])
        self.assertGreaterEqual(len(items), 6)
        funciones = self.env['tllr_fc.funcion'].search([('company_id', '=', False)])
        self.assertGreaterEqual(len(funciones), 3)

    # ---------------- Función y costo ----------------
    def test_costo_por_hora_con_vigencia(self):
        funcion = self.env['tllr_fc.funcion'].create({'name': 'Electricista'})
        self.env['tllr_fc.funcion.costo'].create({
            'funcion_id': funcion.id, 'fecha_desde': date(2026, 1, 1), 'costo_hora': 10000})
        self.env['tllr_fc.funcion.costo'].create({
            'funcion_id': funcion.id, 'fecha_desde': date(2026, 6, 1), 'costo_hora': 12000})
        self.assertEqual(funcion._costo_a_fecha(date(2025, 12, 31)), 0.0)
        self.assertEqual(funcion._costo_a_fecha(date(2026, 3, 1)), 10000)
        self.assertEqual(funcion._costo_a_fecha(date(2026, 6, 1)), 12000)
        self.assertEqual(funcion._costo_a_fecha(date(2026, 12, 1)), 12000)

    def test_vigencia_no_se_edita_ni_se_borra(self):
        funcion = self.env['tllr_fc.funcion'].create({'name': 'Chapista'})
        linea = self.env['tllr_fc.funcion.costo'].create({
            'funcion_id': funcion.id, 'fecha_desde': date(2026, 1, 1), 'costo_hora': 9000})
        with self.assertRaises(UserError):
            linea.write({'costo_hora': 1})
        with self.assertRaises(UserError):
            linea.unlink()

    def test_vigencia_fecha_unica(self):
        funcion = self.env['tllr_fc.funcion'].create({'name': 'Pintor'})
        self.env['tllr_fc.funcion.costo'].create({
            'funcion_id': funcion.id, 'fecha_desde': date(2026, 1, 1), 'costo_hora': 9000})
        with self.assertRaises(ValidationError):
            self.env['tllr_fc.funcion.costo'].create({
                'funcion_id': funcion.id, 'fecha_desde': date(2026, 1, 1), 'costo_hora': 9500})

    # ---------------- Personal y puesto ----------------
    def test_personal_asigna_codigo(self):
        persona = self.env['tllr_fc.personal'].create({
            'name': "Juan Pérez", 'funcion_id': self.env.ref('tllr_fc.funcion_mecanico').id})
        self.assertTrue(persona.codigo.startswith("PER/"))

    def test_puesto_requiere_servicios(self):
        almacen = self.env['stock.warehouse'].search([], limit=1)
        with self.assertRaises(ValidationError):
            self.env['tllr_fc.puesto'].create({'name': "Bahía 1", 'almacen_id': almacen.id})
        servicio = self.env['product.template'].create({'name': "Cambio de aceite", 'type': 'service'})
        puesto = self.env['tllr_fc.puesto'].create({
            'name': "Bahía 1", 'almacen_id': almacen.id,
            'servicio_ids': [Command.set(servicio.ids)]})
        self.assertTrue(puesto.codigo.startswith("PUE/"))
        servicio.invalidate_recordset()
        self.assertEqual(servicio.tllr_fc_puesto_ids, puesto)

    def test_puesto_rechaza_productos_que_no_son_servicio(self):
        almacen = self.env['stock.warehouse'].search([], limit=1)
        bien = self.env['product.template'].create({'name': "Filtro", 'type': 'consu'})
        with self.assertRaises(ValidationError):
            self.env['tllr_fc.puesto'].create({
                'name': "Bahía 2", 'almacen_id': almacen.id,
                'servicio_ids': [Command.set(bien.ids)]})

    # ---------------- Producto y contacto ----------------
    def test_producto_uso_por_defecto_y_garantia(self):
        producto = self.env['product.template'].create({'name': "Aceite", 'type': 'consu'})
        self.assertEqual(producto.tllr_fc_uso_taller, 'ninguno')
        with self.assertRaises(ValidationError):
            producto.tllr_fc_garantia_dias = -1

    def test_descuento_del_contacto(self):
        with self.assertRaises(ValidationError):
            self.cliente.tllr_fc_descuento = 150
        self.cliente.tllr_fc_descuento = 10
        self.assertEqual(self.cliente.tllr_fc_descuento, 10)

    # ---------------- Seguridad ----------------
    def test_usuario_de_taller_no_ve_costos_ni_edita_funciones(self):
        usuario = self.env['res.users'].create({
            'name': "Usuario Taller Prueba",
            'login': "usuario_taller_prueba",
            'group_ids': [Command.link(self.env.ref('tllr_fc.group_usuario').id)],
        })
        funcion = self.env.ref('tllr_fc.funcion_mecanico')
        # Puede leer la función pero no el costo.
        funcion.with_user(usuario).read(['name'])
        with self.assertRaises(AccessError):
            funcion.with_user(usuario).read(['costo_actual'])
        # No puede modificar maestros de administración.
        with self.assertRaises(AccessError):
            self.env['tllr_fc.funcion'].with_user(usuario).create({'name': "No permitida"})
        # Sí puede crear marcas y vehículos.
        self.env['tllr_fc.marca'].with_user(usuario).create({'name': "Marca del usuario"})
