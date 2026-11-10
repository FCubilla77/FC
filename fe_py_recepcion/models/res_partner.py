# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    fe_py_recepcion_confirmar_auto = fields.Boolean(
        string='Confirmar Facturas Electrónicas Recibidas - Automáticamente',
        groups='account.group_account_manager', copy=False,
        help='Al leer el XML de este proveedor (de un correo o cargado a mano), la factura, nota '
             'de crédito o nota de débito se publica sola si la compañía tiene el estado de las '
             'facturas leídas en «Confirmado» y se cumplen los criterios de publicación. Si no '
             'está marcado, o si algún criterio falla, queda en borrador con el motivo.')

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        # Un proveedor creado desde una factura electrónica recibida nace con la confirmación
        # automática marcada si la compañía deja las facturas leídas en «Confirmado».
        if self.env.context.get('fe_py_recepcion_proveedor_nuevo') and \
                self.env.company.fe_py_recepcion_estado_facturas == 'confirmado':
            for partner, vals in zip(partners, vals_list):
                if not partner.parent_id and 'fe_py_recepcion_confirmar_auto' not in vals:
                    partner.sudo().fe_py_recepcion_confirmar_auto = True
        return partners
