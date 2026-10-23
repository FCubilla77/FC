# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import TallerCommon


@tagged('post_install', '-at_install')
class TestIntegraciones(TallerCommon):
    """2026.19.024: instalación de los puentes desde Ajustes."""

    def _estado(self, nombre):
        modulo = self.env['ir.module.module'].search([('name', '=', nombre)], limit=1)
        return modulo.state == 'installed' if modulo else False

    def test_01_valores_reflejan_estado_del_modulo(self):
        ajustes = self.env['res.config.settings'].create({})
        self.assertEqual(ajustes.module_tllr_fc_sale, self._estado('tllr_fc_sale'))
        self.assertEqual(ajustes.module_tllr_fc_purchase, self._estado('tllr_fc_purchase'))

    def test_02_los_puentes_no_se_instalan_solos(self):
        for nombre in ('tllr_fc_sale', 'tllr_fc_purchase'):
            modulo = self.env['ir.module.module'].search([('name', '=', nombre)], limit=1)
            if modulo:
                self.assertFalse(modulo.auto_install,
                                 "%s no debe instalarse automáticamente" % nombre)

    def test_03_solo_administrador_de_odoo_ejecuta(self):
        usuario = self.env['res.users'].create({
            'name': 'Admin Taller sin Odoo', 'login': 'adm_taller_sin_odoo',
            'group_ids': [(6, 0, [self.env.ref('tllr_fc.group_administrador').id])],
        })
        with self.assertRaises(AccessError):
            self.env['res.config.settings'].with_user(usuario).create({})

    def test_04_ajustes_sin_cambios_no_instala_nada(self):
        antes = (self._estado('tllr_fc_sale'), self._estado('tllr_fc_purchase'))
        ajustes = self.env['res.config.settings'].create({})
        ajustes.execute()
        self.assertEqual(antes, (self._estado('tllr_fc_sale'), self._estado('tllr_fc_purchase')))
