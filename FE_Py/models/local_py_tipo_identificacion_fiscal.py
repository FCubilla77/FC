# -*- coding: utf-8 -*-

from odoo import fields, models

# Tabla D208 del Manual Técnico — Tipo de documento de identidad del receptor.
# El código 4 (Carnet de residencia) existe en SIFEN pero no tiene equivalente
# en el catálogo de local_py, por eso no se ofrece acá.
ITIPIDREC = [
    ('1', 'Cédula paraguaya'),
    ('2', 'Pasaporte'),
    ('3', 'Cédula extranjera'),
    ('4', 'Carnet de residencia'),
    ('5', 'Innominado'),
    ('6', 'Tarjeta Diplomática de exoneración fiscal'),
    ('9', 'Otro'),
]

# Descripción exacta que exige SIFEN (dDTipIDRec, D209) para cada código.
DESCRIPCION_ITIPIDREC = dict(ITIPIDREC)


class LocalPyTipoIdentificacionFiscal(models.Model):
    _inherit = 'local_py.tipo_identificacion_fiscal'

    fe_py_itipidrec = fields.Selection(
        string='Tipo de Documento SIFEN (iTipIDRec)',
        selection=ITIPIDREC,
        help='Código equivalente en la tabla de SIFEN, usado al generar el '
             'XML para un receptor sin RUC.\n\n'
             'El catálogo de local_py sigue la Tabla 3 de Marangatu, que no '
             'coincide fila por fila con la tabla de SIFEN — por eso hace '
             'falta este mapeo explícito. "RUC" no lleva código: un receptor '
             'con RUC se informa por dRucRec/dDVRec, no por esta tabla.',
    )
