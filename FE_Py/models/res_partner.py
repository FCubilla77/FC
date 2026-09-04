# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    fe_py_es_estado = fields.Boolean(
        string='FEPy Es Organismo del Estado',
        help='Tildar para Organismos o Entidades del Estado (OEE). SIFEN '
             'valida contra su propia base: si el RUC del receptor '
             'corresponde a un OEE, el Tipo de Operación DEBE ser B2G '
             '(Nota Técnica N° 20).\n\n'
             'Excluyente con "Es Exterior": un OEE tiene RUC paraguayo por '
             'definición.',
    )
    fe_py_tipo_contribuyente_id = fields.Many2one(
        'fe_py.tipo_contribuyente_receptor', string='FEPy Tipo de Contribuyente',
        compute='_compute_fe_py_tipo_contribuyente', store=True, readonly=False,
        help='Se informa como iTiContRec. Se propone según el tipo de '
             'Contacto (Empresa = Jurídica, Individual = Física), pero queda '
             'editable: puede haber un contribuyente registrado como Empresa '
             'en Odoo que legalmente sea Persona Física.',
    )
    fe_py_identificacion_texto = fields.Char(
        string='FEPy Descripción de la Identificación',
        help='Solo aplica cuando el Tipo de Identificación Fiscal se informa '
             'a SIFEN como "Otro". Ahí el usuario escribe el dato real: '
             '"CUIT", "RFC", "NIT", "Tax ID".',
    )
    fe_py_tipo_impuesto_id = fields.Many2one(
        'fe_py.tipo_impuesto', string='FEPy Tipo de Impuesto Afectado',
        help='Se informa como iTImp. Valor por defecto para las facturas de '
             'este Cliente — queda editable por operación.',
    )
    fe_py_indicador_presencia_id = fields.Many2one(
        'fe_py.indicador_presencia', string='FEPy Indicador de Presencia',
        help='Se informa como iIndPres. Presencial = venta física en el '
             'local; Electrónica = e-commerce; Cíclica = facturación '
             'recurrente de contrato. Valor por defecto para este Cliente.',
    )
    fe_py_es_exterior = fields.Boolean(
        string='FEPy Es del Exterior', compute='_compute_fe_py_es_exterior',
        help='Calculado desde la Posición Fiscal marcada como "Es Exterior" '
             'en local_py, que ya valida su coherencia con el País, el Tipo '
             'de Identificación Fiscal y el Incoterm del Contacto.',
    )
    fe_py_es_contribuyente = fields.Boolean(
        string='FEPy Es Contribuyente', compute='_compute_fe_py_es_contribuyente',
        help='Se informa como iNatRec. Automático: es Contribuyente si su '
             'Tipo de Identificación Fiscal es RUC; en cualquier otro caso '
             '(cédula, pasaporte, identificación extranjera) va como No '
             'Contribuyente.',
    )

    @api.depends('is_company')
    def _compute_fe_py_tipo_contribuyente(self):
        Cat = self.env['fe_py.tipo_contribuyente_receptor']
        juridica = Cat.search([('codigo', '=', '2')], limit=1)
        fisica = Cat.search([('codigo', '=', '1')], limit=1)
        for partner in self:
            if not partner.fe_py_tipo_contribuyente_id:
                partner.fe_py_tipo_contribuyente_id = juridica if partner.is_company else fisica

    @api.depends('property_account_position_id', 'property_account_position_id.local_py_es_exterior')
    def _compute_fe_py_es_exterior(self):
        for partner in self:
            partner.fe_py_es_exterior = bool(
                partner.property_account_position_id
                and partner.property_account_position_id.local_py_es_exterior
            )

    @api.depends('l10n_py_tipo_identificacion_fiscal_id',
                 'l10n_py_tipo_identificacion_fiscal_id.fe_py_es_ruc')
    def _compute_fe_py_es_contribuyente(self):
        for partner in self:
            tipo = partner.l10n_py_tipo_identificacion_fiscal_id
            partner.fe_py_es_contribuyente = bool(tipo and tipo.fe_py_es_ruc)

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
