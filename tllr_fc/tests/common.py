# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


class TallerCommon(TransactionCase):
    """Datos y auxiliares compartidos por las pruebas de las fases 3 y 4."""

    # Las pruebas de las fases anteriores no cargan informe, horas ni «No utilizado»:
    # el control de cierre del puesto (2026.19.011) se prueba en test_cierre_puesto.
    parchear_cierre = True

    def _sv(self, ot):
        """Servicio y puesto del primer servicio de la OT (para cargar horas)."""
        servicio = ot.servicio_ids[:1]
        return {'servicio_id': servicio.id, 'puesto_line_id': servicio.puesto_line_id.id}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if cls.parchear_cierre:
            parche = patch.object(
                type(cls.env['tllr_fc.ot.puesto']), '_tllr_fc_validar_cierre',
                lambda self: None)
            parche.start()
            cls.addClassCleanup(parche.stop)
        marca = cls.env['tllr_fc.marca'].create({'name': 'Toyota F3'})
        modelo = cls.env['tllr_fc.modelo'].create({'name': 'Hilux F3', 'marca_id': marca.id})
        tipo = cls.env['tllr_fc.tipo_vehiculo'].create({'name': 'Camioneta F3'})
        cls.cliente = cls.env['res.partner'].create({
            'name': 'Cliente Fase 3', 'tllr_fc_descuento': 10.0})
        cls.vehiculo = cls.env['tllr_fc.vehiculo'].create({
            'name': 'Hilux F3', 'marca_id': marca.id, 'modelo_id': modelo.id,
            'anio': 2021, 'tipo_id': tipo.id, 'partner_id': cls.cliente.id,
            'chapa': 'FAS 003', 'kilometraje': 1000,
        })
        cls.s1 = cls.env['product.product'].create({
            'name': 'Cambio de aceite F3', 'type': 'service', 'list_price': 100000,
            'standard_price': 5000, 'tllr_fc_horas_estandar': 1.0})
        cls.s2 = cls.env['product.product'].create({
            'name': 'Alineación F3', 'type': 'service', 'list_price': 50000,
            'tllr_fc_horas_estandar': 0.5})
        cls.s3 = cls.env['product.product'].create({
            'name': 'Servicio sin puesto F3', 'type': 'service', 'list_price': 10000})
        almacen = cls.env['stock.warehouse'].search([], limit=1)
        cls.almacen = almacen
        cls.puesto1 = cls.env['tllr_fc.puesto'].create({
            'name': 'Puesto 1 F3', 'almacen_id': almacen.id,
            'servicio_ids': [Command.set(cls.s1.product_tmpl_id.ids)]})
        cls.puesto2 = cls.env['tllr_fc.puesto'].create({
            'name': 'Puesto 2 F3', 'almacen_id': almacen.id,
            'servicio_ids': [Command.set(cls.s2.product_tmpl_id.ids)]})
        funcion = cls.env.ref('tllr_fc.funcion_mecanico')
        cls.usuario_taller = cls.env['res.users'].create({
            'name': "Mecánico F3", 'login': "mecanico_f3",
            'group_ids': [Command.link(cls.env.ref('tllr_fc.group_usuario').id)]})
        cls.personal1 = cls.env['tllr_fc.personal'].create({
            'name': 'Mecánico 1 F3', 'funcion_id': funcion.id,
            'user_id': cls.usuario_taller.id})
        cls.personal2 = cls.env['tllr_fc.personal'].create({
            'name': 'Mecánico 2 F3', 'funcion_id': funcion.id})
        cls.responsable = cls.env['tllr_fc.personal'].create({
            'name': 'Jefe F3', 'funcion_id': funcion.id})
        cls.repuesto = cls.env['product.product'].create({
            'name': 'Filtro F3', 'type': 'consu', 'is_storable': True,
            'list_price': 30000, 'standard_price': 12000,
            'tllr_fc_uso_taller': 'repuesto'})
        cls.insumo = cls.env['product.product'].create({
            'name': 'Grasa F3', 'type': 'consu', 'is_storable': True,
            'list_price': 8000, 'standard_price': 3000,
            'tllr_fc_uso_taller': 'insumo'})
        cls.env['stock.quant']._update_available_quantity(
            cls.repuesto, almacen.lot_stock_id, 10)
        cls.env['stock.quant']._update_available_quantity(
            cls.insumo, almacen.lot_stock_id, 5)

    # ---------------- Auxiliares ----------------
    def _ot(self, servicios=None, **extra):
        servicios = servicios or [self.s1, self.s2]
        recepcion = self.env['tllr_fc.recepcion'].create({
            'vehiculo_id': self.vehiculo.id, 'partner_id': self.cliente.id,
            'kilometraje': 2000,
            'servicio_ids': [Command.create({'product_id': s.id}) for s in servicios],
        })
        recepcion.action_cargar_items()
        recepcion.item_ids.write({'presente': 'si'})
        accion = recepcion.action_confirmar()
        if isinstance(accion, dict):  # advertencia por OT abierta del mismo vehículo
            self.env['tllr_fc.wizard.confirmar_advertencia'].create({
                'res_model': 'tllr_fc.recepcion', 'res_id': recepcion.id,
                'accion': 'action_confirmar', 'mensaje': 'x'}).action_continuar()
        ot = recepcion.ot_id
        if extra:
            ot.write(extra)
        return ot

    def _ot_planificada(self):
        """OT con dos puestos (uno por servicio), personal y responsable."""
        ot = self._ot()
        self.env['tllr_fc.ot.puesto'].create([
            {'ot_id': ot.id, 'puesto_id': self.puesto1.id, 'sequence': 10,
             'personal_ids': [Command.set(self.personal1.ids)]},
            {'ot_id': ot.id, 'puesto_id': self.puesto2.id, 'sequence': 20,
             'personal_ids': [Command.set(self.personal2.ids)]},
        ])
        ot.responsable_id = self.responsable
        return ot

    def _terminar_servicios(self, linea):
        linea.servicio_ids.action_terminar()

