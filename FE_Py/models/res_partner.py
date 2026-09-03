# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Tabla E011 del Manual Técnico — Indicador de presencia de la operación.
INDICADOR_PRESENCIA = [
    ('1', 'Operación presencial'),
    ('2', 'Operación electrónica'),
    ('3', 'Operación telemarketing'),
    ('4', 'Operación de venta a domicilio'),
    ('5', 'Operación bancaria'),
    ('6', 'Operación cíclica'),
    ('9', 'Otro'),
]

# Tabla D013 del Manual Técnico — Tipo de impuesto afectado.
TIPO_IMPUESTO = [
    ('1', 'IVA'),
    ('2', 'ISC'),
    ('3', 'Renta'),
    ('4', 'Ninguno'),
    ('5', 'IVA - Renta'),
]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    fe_py_es_estado = fields.Boolean(
        string='Es Organismo del Estado',
        help='Tildar para Organismos o Entidades del Estado (OEE). SIFEN '
             'valida contra su propia base de datos: si el RUC del receptor '
             'corresponde a un OEE, el Tipo de Operación DEBE ser B2G '
             '(Nota Técnica N° 20).\n\n'
             'Excluyente con "Es Exterior": un OEE tiene RUC paraguayo por '
             'definición, nunca puede ser del exterior.',
    )
    fe_py_tipo_persona = fields.Selection(
        string='Tipo de Persona (FE)',
        selection=[('fisica', 'Persona Física'), ('juridica', 'Persona Jurídica')],
        compute='_compute_fe_py_tipo_persona', store=True, readonly=False,
        help='Se informa como iTiContRec en el XML. Se propone según el tipo '
             'de Contacto (Empresa = Jurídica, Individual = Física), pero '
             'queda editable: puede haber un contribuyente registrado como '
             'Empresa en Odoo que legalmente sea Persona Física.',
    )
    fe_py_identificacion_texto = fields.Char(
        string='Descripción de la Identificación',
        help='Solo aplica cuando el Tipo de Identificación Fiscal es '
             '"Identificacion Tributaria". SIFEN no tiene un código propio '
             'para ese caso, así que se informa como "Otro" (iTipIDRec=9) '
             'más esta descripción libre. Ejemplos: "CUIT", "RFC", "NIT", '
             '"Tax ID".',
    )
    fe_py_itimp = fields.Selection(
        string='Tipo de Impuesto Afectado (FE)',
        selection=TIPO_IMPUESTO, default='1',
        help='Se informa como iTImp en el XML. Valor por defecto para las '
             'facturas de este Cliente — queda editable por operación.',
    )
    fe_py_indicador_presencia = fields.Selection(
        string='Indicador de Presencia (FE)',
        selection=INDICADOR_PRESENCIA, default='1',
        help='Se informa como iIndPres en el XML. Presencial = venta física '
             'en el local; Electrónica = e-commerce o similar; Cíclica = '
             'facturación recurrente de contrato. Valor por defecto para las '
             'facturas de este Cliente — queda editable por operación.',
    )
    fe_py_es_exterior = fields.Boolean(
        string='Es del Exterior (FE)', compute='_compute_fe_py_es_exterior',
        help='Calculado desde la Posición Fiscal marcada como "Es Exterior" '
             'en local_py. local_py ya valida que este dato sea coherente con '
             'el País, el Tipo de Identificación Fiscal y el Incoterm del '
             'Contacto, así que se usa directamente como fuente confiable.',
    )

    @api.depends('is_company')
    def _compute_fe_py_tipo_persona(self):
        for partner in self:
            if not partner.fe_py_tipo_persona:
                partner.fe_py_tipo_persona = 'juridica' if partner.is_company else 'fisica'

    @api.depends('property_account_position_id', 'property_account_position_id.local_py_es_exterior')
    def _compute_fe_py_es_exterior(self):
        for partner in self:
            partner.fe_py_es_exterior = bool(
                partner.property_account_position_id
                and partner.property_account_position_id.local_py_es_exterior
            )

    @api.constrains('fe_py_es_estado', 'property_account_position_id')
    def _check_fe_py_estado_vs_exterior(self):
        for partner in self:
            if partner.fe_py_es_estado and partner.fe_py_es_exterior:
                raise ValidationError(
                    'El Contacto "%s" está marcado como Organismo del Estado y '
                    'a la vez tiene una Posición Fiscal "Es Exterior". Un '
                    'Organismo del Estado paraguayo tiene RUC nacional por '
                    'definición — las dos condiciones son excluyentes.'
                    % (partner.display_name or '')
                )
