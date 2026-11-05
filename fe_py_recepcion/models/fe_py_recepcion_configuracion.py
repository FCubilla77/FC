# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FePyRecepcionConfiguracion(models.Model):
    """Configuración por compañía de la recepción de facturas electrónicas.

    Misma convención que local_py y FE_Py: una pantalla de configuración
    propia, una por compañía, en vez de campos sueltos en Ajustes.
    """
    _name = 'fe_py_recepcion.configuracion'
    _description = 'Configuración de Recepción de Facturas Electrónicas'
    _rec_name = 'company_id'

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, index=True,
        default=lambda self: self.env.company)
    diario_id = fields.Many2one(
        'account.journal', string='Diario de compra por defecto',
        domain="[('type', '=', 'purchase'), ('company_id', '=', company_id)]",
        help='Diario con el que se generan las facturas de proveedor. Se puede '
             'cambiar en cada recepción. Debe ser un diario de compra con Tipo '
             'Fiscal "Factura".')
    impuesto_iva10_id = fields.Many2one(
        'account.tax', string='Impuesto IVA 10%',
        domain="[('type_tax_use', '=', 'purchase'), ('company_id', '=', company_id)]",
        help='Impuesto de compra para las líneas con IVA 10%. Los precios del XML '
             'ya incluyen el IVA, así que debe tener "Incluido en el precio".')
    impuesto_iva5_id = fields.Many2one(
        'account.tax', string='Impuesto IVA 5%',
        domain="[('type_tax_use', '=', 'purchase'), ('company_id', '=', company_id)]",
        help='Impuesto de compra para las líneas con IVA 5% (con IVA incluido en el precio).')
    impuesto_exento_id = fields.Many2one(
        'account.tax', string='Impuesto Exento',
        domain="[('type_tax_use', '=', 'purchase'), ('company_id', '=', company_id)]",
        help='Impuesto de compra (0%) para las líneas exentas.')

    @api.constrains('company_id')
    def _check_company_unica(self):
        for config in self:
            otra = self.sudo().search_count(
                [('company_id', '=', config.company_id.id), ('id', '!=', config.id)])
            if otra:
                raise ValidationError(_(
                    'Ya existe una configuración para la compañía "%s".', config.company_id.name))

    @api.model
    def _get_config(self, company, crear=True):
        """Configuración de la compañía. Si no existe y `crear`, la crea vacía."""
        config = self.sudo().search([('company_id', '=', company.id)], limit=1)
        if not config and crear:
            config = self.sudo().create({'company_id': company.id})
        return config
