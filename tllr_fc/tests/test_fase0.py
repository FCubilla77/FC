# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFase0(TransactionCase):

    def test_grupos_acumulativos(self):
        usuario = self.env.ref('tllr_fc.group_usuario')
        supervisor = self.env.ref('tllr_fc.group_supervisor')
        admin = self.env.ref('tllr_fc.group_administrador')
        self.assertIn(usuario, supervisor.all_implied_ids)
        self.assertIn(supervisor, admin.all_implied_ids)
        self.assertIn(usuario, admin.all_implied_ids)

    def test_secuencias_por_compania(self):
        for codigo in ('tllr_fc.vehiculo', 'tllr_fc.ot', 'tllr_fc.entrega'):
            self.assertTrue(self.env['ir.sequence'].search_count([
                ('code', '=', codigo),
                ('company_id', '=', self.env.company.id),
            ]), codigo)

    def test_secuencias_compania_nueva(self):
        compania = self.env['res.company'].create({'name': 'Compañía de prueba Taller'})
        self.assertEqual(
            self.env['ir.sequence'].search_count([
                ('code', 'like', 'tllr_fc.%'),
                ('company_id', '=', compania.id),
            ]), 8)

    def test_formato_papel(self):
        papel = self.env.ref('tllr_fc.paperformat_a4')
        self.assertEqual(papel.format, 'A4')
        self.assertEqual((papel.margin_top, papel.margin_bottom,
                          papel.margin_right, papel.margin_left), (15, 15, 15, 20))

    def test_ajustes_por_defecto(self):
        compania = self.env.company
        self.assertFalse(compania.tllr_fc_generar_asientos)
        self.assertFalse(compania.tllr_fc_qc_cliente)
        self.assertEqual(compania.tllr_fc_aprobacion_adicional, 'obligatoria')

    def test_asientos_requieren_cuentas(self):
        with self.assertRaises(ValidationError):
            self.env.company.tllr_fc_generar_asientos = True
