# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import TallerCommon


@tagged('post_install', '-at_install')
class TestTraslados(TallerCommon):
    """2026.19.010: traslados de stock entre el almacén principal y los puestos."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        compania = cls.env.company
        cls.principal = cls.almacen
        compania.tllr_fc_almacen_principal_id = cls.principal
        cls.almacen_a = cls.env['stock.warehouse'].create({'name': 'Puesto A F6', 'code': 'PAF6'})
        cls.almacen_b = cls.env['stock.warehouse'].create({'name': 'Puesto B F6', 'code': 'PBF6'})
        cls.puesto_a = cls.env['tllr_fc.puesto'].create({
            'name': 'Puesto A F6', 'almacen_id': cls.almacen_a.id,
            'servicio_ids': [Command.set(cls.s1.product_tmpl_id.ids)]})
        cls.puesto_b = cls.env['tllr_fc.puesto'].create({
            'name': 'Puesto B F6', 'almacen_id': cls.almacen_b.id,
            'servicio_ids': [Command.set(cls.s2.product_tmpl_id.ids)]})

    def _ot_traslado(self):
        ot = self._ot()
        self.env['tllr_fc.ot.puesto'].create([
            {'ot_id': ot.id, 'puesto_id': self.puesto_a.id, 'sequence': 10,
             'personal_ids': [Command.set(self.personal1.ids)]},
            {'ot_id': ot.id, 'puesto_id': self.puesto_b.id, 'sequence': 20,
             'personal_ids': [Command.set(self.personal2.ids)]},
        ])
        ot.responsable_id = self.responsable
        return ot

    def _linea(self, ot, producto=None, cantidad=3, puesto=None):
        vals = {'ot_id': ot.id, 'product_id': (producto or self.repuesto).id,
                'cantidad_reservada': cantidad}
        if puesto:
            vals['puesto_line_id'] = puesto.id
        return self.env['tllr_fc.ot.producto'].create(vals)

    def _picking(self, ot, sentido, estado='draft'):
        return self.env['stock.picking'].search([
            ('tllr_fc_ot_id', '=', ot.id), ('tllr_fc_sentido', '=', sentido),
            ('state', '=', estado)])

    def _validar(self, picking):
        picking.action_confirm()
        picking.action_assign()
        for movimiento in picking.move_ids:
            movimiento.quantity = movimiento.product_uom_qty
            movimiento.picked = True
        picking.with_context(skip_backorder=True).button_validate()
        self.assertEqual(picking.state, 'done')

    def _stock(self, producto, almacen):
        quants = self.env['stock.quant'].search([
            ('product_id', '=', producto.id), ('location_id', '=', almacen.lot_stock_id.id)])
        return sum(quants.mapped('quantity'))

    def test_borrador_de_traslado_se_actualiza_sin_duplicar(self):
        ot = self._ot_traslado()
        linea = self._linea(ot, cantidad=3)
        self.assertEqual(linea.puesto_line_id.puesto_id, self.puesto_a)
        ida = self._picking(ot, 'ida')
        self.assertEqual(len(ida), 1)
        self.assertEqual(ida.location_id, self.principal.lot_stock_id)
        self.assertEqual(ida.location_dest_id, self.almacen_a.lot_stock_id)
        self.assertEqual(ida.move_ids.product_uom_qty, 3)
        self.assertEqual(linea.reserva_estado, 'traslado')
        linea.cantidad_reservada = 5
        self.assertEqual(self._picking(ot, 'ida'), ida)
        self.assertEqual(ida.move_ids.product_uom_qty, 5)
        linea.cantidad_reservada = 4
        self.assertEqual(ida.move_ids.product_uom_qty, 4)
        # Otro producto del mismo puesto va al mismo borrador.
        self._linea(ot, producto=self.insumo, cantidad=2)
        self.assertEqual(len(self._picking(ot, 'ida')), 1)
        self.assertEqual(len(ida.move_ids), 2)
        # Quitar la línea quita su movimiento del borrador.
        linea.unlink()
        self.assertEqual(len(ida.move_ids), 1)

    def test_traslado_validado_habilita_el_uso_y_la_reserva(self):
        ot = self._ot_traslado()
        linea = self._linea(ot, cantidad=3)
        self._validar(self._picking(ot, 'ida'))
        self.assertEqual(self._stock(self.repuesto, self.almacen_a), 3)
        ot.action_iniciar()
        self.assertEqual(linea.reserva_estado, 'ok')
        self.assertEqual(linea.cantidad_en_puesto, 3)
        linea.cantidad_utilizada = 2
        self.assertEqual(linea.cantidad_consumida, 2)
        self.assertEqual(self._stock(self.repuesto, self.almacen_a), 1)
        self.assertEqual(linea.cantidad_en_puesto, 1)

    def test_uso_sin_traslado_bloqueado_o_autorizado_por_el_supervisor(self):
        ot = self._ot_traslado()
        linea = self._linea(ot, cantidad=3)
        ot.action_iniciar()
        self.assertEqual(linea.reserva_estado, 'traslado')
        with self.assertRaises(UserError):
            linea.cantidad_utilizada = 1
        stock_principal = self._stock(self.repuesto, self.principal)
        self.env['tllr_fc.wizard.excepcion'].create({
            'res_model': linea._name, 'res_id': linea.id,
            'accion': 'action_autorizar_sin_traslado', 'grupo_requerido': 'supervisor',
            'motivo': 'Urgente'}).action_autorizar()
        self.assertTrue(linea.autorizado_sin_traslado)
        # El borrador ya no hace falta.
        self.assertFalse(self._picking(ot, 'ida'))
        linea.cantidad_utilizada = 2
        self.assertEqual(self._stock(self.repuesto, self.principal), stock_principal - 2)

    def test_uso_solo_con_el_puesto_activo(self):
        ot = self._ot_traslado()
        en_b = self._linea(ot, producto=self.insumo, cantidad=1, puesto=ot.puesto_line_ids[1])
        self._validar(self._picking(ot, 'ida'))
        ot.action_iniciar()
        with self.assertRaises(UserError):
            en_b.cantidad_utilizada = 1

    def test_devolucion_al_terminar_el_puesto_y_al_cancelar(self):
        ot = self._ot_traslado()
        linea = self._linea(ot, cantidad=4)
        self._validar(self._picking(ot, 'ida'))
        ot.action_iniciar()
        linea.cantidad_utilizada = 1
        primera = ot.puesto_line_ids.sorted('sequence')[0]
        primera.servicio_ids.filtered(lambda s: s.estado == 'pendiente').action_terminar()
        ot.action_terminar_puesto()
        vuelta = self._picking(ot, 'vuelta')
        self.assertEqual(len(vuelta), 1)
        self.assertEqual(vuelta.location_id, self.almacen_a.lot_stock_id)
        self.assertEqual(vuelta.location_dest_id, self.principal.lot_stock_id)
        self.assertEqual(vuelta.move_ids.product_uom_qty, 3)
        self._validar(vuelta)
        self.assertEqual(self._stock(self.repuesto, self.almacen_a), 0)
        # Cancelar la OT con otro producto en el puesto B: se devuelve lo no usado.
        otra = self._ot_traslado()
        l2 = self._linea(otra, producto=self.insumo, cantidad=2)
        self._validar(self._picking(otra, 'ida'))
        otra.action_iniciar()
        otra._tllr_fc_cancelar(self.env['tllr_fc.motivo'].search(
            [('tipo', '=', 'cancelacion')], limit=1), False)
        vuelta2 = self._picking(otra, 'vuelta')
        self.assertEqual(vuelta2.move_ids.product_uom_qty, 2)
        self.assertEqual(l2.cantidad_en_puesto, 2)

    def test_sin_almacen_principal_no_hay_traslados(self):
        self.env.company.tllr_fc_almacen_principal_id = False
        ot = self._ot_traslado()
        linea = self._linea(ot, cantidad=2)
        self.assertFalse(self.env['stock.picking'].search([('tllr_fc_ot_id', '=', ot.id)]))
        self.assertFalse(linea.traslado_requerido)
