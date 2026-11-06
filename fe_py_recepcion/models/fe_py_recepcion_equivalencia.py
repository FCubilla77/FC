# -*- coding: utf-8 -*-
from odoo import api, fields, models

from . import utilidades


class FePyRecepcionEquivalencia(models.Model):
    """Qué producto propio corresponde a cada ítem de un proveedor.

    Se llena sola al confirmar una recepción, y sirve para sugerir el producto
    la próxima vez que ese proveedor facture lo mismo. Es una tabla propia (y
    no la lista de proveedores del producto) para no tocar los precios de
    compra de Compras.

    Cada fila relaciona UN ítem del proveedor con UN producto. Un mismo producto
    puede tener varios ítems del proveedor (varias filas), y un mismo ítem puede
    haberse asignado a distintos productos con el tiempo (varias filas): se
    conservan todas y se sugiere la usada más recientemente.
    """
    _name = 'fe_py_recepcion.equivalencia'
    _inherit = ['fe_py_recepcion.mixin.licencia']
    _description = 'Equivalencia de producto del proveedor'
    _order = 'partner_id, codigo, descripcion, ultimo_uso desc'

    partner_id = fields.Many2one('res.partner', string='Proveedor', required=True, index=True,
                                 ondelete='cascade')
    codigo = fields.Char(string='Código del proveedor',
                         help='Código interno (dCodInt) que usa el proveedor en su factura.')
    descripcion = fields.Char(string='Descripción del proveedor',
                              help='Se usa para reconocer el ítem cuando el proveedor no informa código.')
    producto_id = fields.Many2one('product.product', string='Producto', required=True,
                                  ondelete='cascade')
    producto_referencia = fields.Char(
        string='Referencia', related='producto_id.default_code', store=True,
        help='Referencia interna de la ficha del producto. Se actualiza sola si cambia en la ficha.')
    ultimo_uso = fields.Datetime(
        string='Último uso', default=fields.Datetime.now,
        help='Última vez que se confirmó una factura con esta relación. Si un mismo ítem del '
             'proveedor tiene varios productos, se sugiere el de uso más reciente.')
    company_id = fields.Many2one('res.company', string='Compañía', required=True,
                                 default=lambda self: self.env.company)

    @api.model
    def _filas_del_item(self, partner, codigo, descripcion, company):
        """Equivalencias de ese ítem del proveedor (puede haber varias, con distintos productos).

        Si el proveedor informa código, se busca por código; si no, por descripción
        exacta entre las equivalencias que tampoco tienen código.
        """
        existentes = self.sudo().search([
            ('partner_id', '=', partner.id), ('company_id', '=', company.id)])
        codigo_n = utilidades.normalizar_clave(codigo)
        descripcion_n = utilidades.normalizar_clave(descripcion)
        if codigo_n:
            return existentes.filtered(lambda e: utilidades.normalizar_clave(e.codigo) == codigo_n)
        if descripcion_n:
            return existentes.filtered(
                lambda e: not utilidades.normalizar_clave(e.codigo)
                and utilidades.normalizar_clave(e.descripcion) == descripcion_n)
        return existentes.browse()

    @api.model
    def buscar_producto(self, partner, codigo, descripcion, company):
        """Producto sugerido para el ítem: el de la equivalencia usada más recientemente
        (ignora productos archivados o que ya no se pueden comprar)."""
        filas = self._filas_del_item(partner, codigo, descripcion, company).filtered(
            lambda e: e.producto_id.active and e.producto_id.purchase_ok)
        elegido = utilidades.elegir_mas_reciente(
            [(f.producto_id.id, f.ultimo_uso, f.id) for f in filas])
        return self.env['product.product'].browse(elegido) if elegido else self.env['product.product']

    @api.model
    def registrar(self, partner, codigo, descripcion, producto, company):
        """Registra que ese ítem del proveedor corresponde a ese producto.

        Si ya existe esa misma relación, solo actualiza su último uso; si el ítem
        estaba relacionado con otro producto, crea una relación nueva y conserva las
        anteriores.
        """
        if not (partner and producto and ((codigo or '').strip() or (descripcion or '').strip())):
            return
        existente = self._filas_del_item(partner, codigo, descripcion, company).filtered(
            lambda e: e.producto_id == producto)[:1]
        ahora = fields.Datetime.now()
        if existente:
            existente.ultimo_uso = ahora
            return
        self.sudo().create({
            'partner_id': partner.id,
            'codigo': (codigo or '').strip(),
            'descripcion': (descripcion or '').strip(),
            'producto_id': producto.id,
            'company_id': company.id,
            'ultimo_uso': ahora,
        })
