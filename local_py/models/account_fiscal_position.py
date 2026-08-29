# -*- coding: utf-8 -*-

from odoo import fields, models


class AccountFiscalPosition(models.Model):
    _inherit = 'account.fiscal.position'

    local_py_es_exterior = fields.Boolean(
        string='Es Exterior',
        help='Tildar en la Posición Fiscal que aplica a Clientes y Proveedores del '
             'exterior (la que reemplaza IVA por Exento, vía Mapeo de Impuestos en '
             'cada Impuesto — ver "Reemplaza"). Se usa junto con el País y el Tipo de '
             'Identificación Fiscal del Contacto para exigir una configuración '
             'consistente: si alguno de esos datos indica "exterior", los demás '
             'tienen que coincidir también.',
    )
