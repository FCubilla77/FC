# -*- coding: utf-8 -*-
"""Campos de Facturación Electrónica sobre modelos que ya existen.

Criterio del proyecto: antes de crear un modelo nuevo, se reutiliza el
que ya existe agregándole los campos que la DNIT exige. Todas las
etiquetas llevan el prefijo "FEPy" para distinguirlas de los campos
nativos de Odoo, de local_py o de l10n_py.
"""

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AccountTax(models.Model):
    """Afectación IVA por impuesto.

    Antes el generador deducía la naturaleza del impuesto mirando su
    porcentaje ("si es 10 entonces es IVA 10%"), lo que fallaría con un
    ISC o una retención del mismo porcentaje. Ahora cada impuesto declara
    explícitamente qué es; el porcentaje se sigue leyendo del propio
    impuesto, que es donde ya estaba bien.
    """
    _inherit = 'account.tax'

    fe_py_afectacion_iva_id = fields.Many2one(
        'fe_py.afectacion_iva', string='FEPy Afectación IVA',
        domain="[('disponible', '=', True)]",
        help='Código que se informa como iAfecIVA en cada línea que use este '
             'impuesto. Sin este dato no se puede generar el XML.',
    )

    @api.constrains('fe_py_afectacion_iva_id')
    def _check_fe_py_afectacion_disponible(self):
        for tax in self:
            afec = tax.fe_py_afectacion_iva_id
            if afec and not afec.disponible:
                raise ValidationError(
                    'El código de Afectación IVA "%s" todavía no está '
                    'disponible: su cálculo (total exonerado, proporción '
                    'gravada y base exenta por línea) no está implementado, '
                    'y usarlo generaría un XML inconsistente.' % afec.name
                )


class ResCurrency(models.Model):
    """Descripción de la moneda para el XML.

    El código ya sirve tal cual: SIFEN usa ISO 4217, el mismo estándar
    que Odoo usa en el nombre de la moneda (PYG, USD, EUR). Solo falta
    la descripción en el formato que espera SIFEN.
    """
    _inherit = 'res.currency'

    fe_py_descripcion = fields.Char(
        string='FEPy Descripción de Moneda',
        help='Texto que se informa como dDesMoneOpe (3 a 20 caracteres). '
             'Ejemplos: "Guarani", "Dolar americano", "Real brasileño". '
             'Sin este dato no se puede facturar en esta moneda.',
    )


class AccountPaymentTerm(models.Model):
    """Condición de la operación y del crédito."""
    _inherit = 'account.payment.term'

    fe_py_condicion_credito = fields.Selection(
        string='FEPy Condición del Crédito',
        selection=[('1', 'Plazo'), ('2', 'Cuota')], default='1',
        help='Se informa como iCondCred en las operaciones a crédito. '
             '"Plazo" informa dPlazoCre; "Cuota" informa el detalle de cada '
             'cuota. Solo aplica si la Condición de local_py es Crédito.',
    )


class ProductTemplate(models.Model):
    """Unidad de medida SIFEN por producto.

    Antes toda línea salía como "Unidad (77)", sin importar si se vendían
    kilos, litros o metros — un dato fiscal incorrecto en cada documento.
    """
    _inherit = 'product.template'

    fe_py_unidad_medida_id = fields.Many2one(
        'fe_py.unidad_medida', string='FEPy Unidad de Medida',
        help='Unidad que se informa como cUniMed en las líneas de este '
             'producto. Obligatoria para poder facturarlo electrónicamente.',
    )


class UomUom(models.Model):
    """Correspondencia entre las unidades de Odoo y las de SIFEN.

    No reemplaza al dato del producto (que es el que manda), pero permite
    proponerlo automáticamente al crear productos nuevos, en vez de
    obligar a elegirlo uno por uno.
    """
    _inherit = 'uom.uom'

    fe_py_unidad_medida_id = fields.Many2one(
        'fe_py.unidad_medida', string='FEPy Unidad de Medida',
        help='Se usa para proponer la unidad SIFEN al crear un producto con '
             'esta unidad de medida.',
    )
