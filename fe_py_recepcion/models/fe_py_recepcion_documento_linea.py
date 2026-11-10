# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

from . import utilidades

AFECTACIONES = {
    '1': 'Gravado IVA',
    '2': 'Exonerado',
    '3': 'Exento',
    '4': 'Gravado parcial',
}


class FePyRecepcionDocumentoLinea(models.Model):
    """Línea (ítem) de una factura electrónica recibida."""
    _name = 'fe_py_recepcion.documento.linea'
    _description = 'Línea de Factura Electrónica Recibida'
    _order = 'documento_id, orden, id'

    documento_id = fields.Many2one('fe_py_recepcion.documento', string='Recepción', required=True,
                                   ondelete='cascade', index=True)
    company_id = fields.Many2one(related='documento_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='documento_id.currency_id')
    state = fields.Selection(related='documento_id.state')
    orden = fields.Integer(string='Nº', readonly=True)

    codigo = fields.Char(string='Código del proveedor', readonly=True)
    descripcion = fields.Char(string='Descripción', readonly=True)
    unidad_desc = fields.Char(string='Unidad del XML', readonly=True)
    unidad_codigo = fields.Char(string='Código de unidad (XML)', readonly=True)
    gtin = fields.Char(string='GTIN', readonly=True,
                       help='Código de barras del producto (GTIN) que informa el proveedor.')
    gtin_paquete = fields.Char(string='GTIN del paquete', readonly=True)
    lote = fields.Char(string='Lote', readonly=True)
    vencimiento_lote = fields.Date(string='Vencimiento del lote', readonly=True)
    serie = fields.Char(string='Serie', readonly=True)
    info_item = fields.Char(string='Información del ítem', readonly=True,
                            help='Texto libre del emisor sobre el ítem (algunos proveedores '
                                 'indican allí números de serie).')
    cantidad = fields.Float(string='Cantidad', digits=(16, 4), readonly=True)
    precio_xml = fields.Float(string='Precio del XML', digits='Product Price', readonly=True,
                              help='Precio unitario con IVA incluido, como lo informa el XML.')
    precio = fields.Float(string='Precio a cargar', digits='Product Price', readonly=True,
                          help='Precio unitario que se carga en la factura (con IVA incluido).')
    descuento = fields.Float(string='Desc. %', digits='Discount', readonly=True)
    total_xml = fields.Monetary(string='Total del XML', currency_field='currency_id', readonly=True)
    iva_xml = fields.Monetary(string='IVA del XML', currency_field='currency_id', readonly=True)

    afectacion = fields.Char(string='Afectación IVA', readonly=True)
    afectacion_texto = fields.Char(compute='_compute_textos')
    tasa = fields.Integer(string='Tasa IVA', readonly=True)
    tasa_texto = fields.Char(compute='_compute_textos')

    producto_id = fields.Many2one('product.product', string='Producto', check_company=True,
                                  domain="[('purchase_ok', '=', True)]")
    cuenta_id = fields.Many2one(
        'account.account', string='Cuenta', check_company=True,
        domain="[('account_type', 'not in', ('asset_receivable', 'liability_payable'))]",
        help='Obligatoria si no se elige producto.')
    impuesto_id = fields.Many2one(
        'account.tax', string='Impuesto', compute='_compute_impuesto', store=True, readonly=False,
        domain="[('type_tax_use', '=', 'purchase'), ('company_id', '=', company_id)]")
    producto_origen = fields.Selection(
        [('manual', 'Manual'), ('equivalencia', 'Equivalencia'), ('gtin', 'GTIN'),
         ('referencia', 'Referencia'), ('descripcion', 'Descripción')],
        string='Producto elegido por', readonly=True, copy=False,
        help='Cómo se eligió el producto: equivalencia ya confirmada con ese proveedor, '
             'coincidencia del GTIN con el código de barras, coincidencia con la referencia o el '
             'nombre de la ficha del producto, o manualmente.')
    aviso = fields.Char(string='Aviso', compute='_compute_aviso')

    def write(self, vals):
        # Si el usuario cambia el producto, deja de ser una sugerencia del sistema.
        if 'producto_id' in vals and 'producto_origen' not in vals:
            vals = dict(vals, producto_origen='manual' if vals['producto_id'] else False)
        return super().write(vals)

    @api.depends('afectacion', 'tasa')
    def _compute_textos(self):
        for linea in self:
            linea.afectacion_texto = '%s (%s)' % (AFECTACIONES.get(linea.afectacion, '?'), linea.afectacion or '-')
            linea.tasa_texto = _('IVA %s%%', linea.tasa) if linea.afectacion == '1' else _('Exento')

    @api.depends('afectacion', 'tasa', 'company_id')
    def _compute_impuesto(self):
        """Impuesto configurado para la afectación y tasa del XML.

        Las afectaciones 2 (exonerado) y 4 (gravado parcial) no se soportan:
        quedan sin impuesto y bloquean la recepción.
        """
        for linea in self:
            company = linea.company_id or self.env.company
            impuesto = self.env['account.tax']
            if linea.afectacion == '1' and linea.tasa == 10:
                impuesto = company.fe_py_recepcion_impuesto_iva10_id
            elif linea.afectacion == '1' and linea.tasa == 5:
                impuesto = company.fe_py_recepcion_impuesto_iva5_id
            elif linea.afectacion == '3':
                impuesto = company.fe_py_recepcion_impuesto_exento_id
            linea.impuesto_id = impuesto

    @api.depends('producto_id', 'unidad_desc')
    def _compute_aviso(self):
        for linea in self:
            aviso = False
            if linea.producto_id and utilidades.unidades_distintas(
                    linea.unidad_desc, linea.producto_id.uom_id.name):
                aviso = _('la unidad del XML (%(xml)s) es distinta a la del producto (%(odoo)s).',
                          xml=linea.unidad_desc, odoo=linea.producto_id.uom_id.name)
            linea.aviso = aviso
