# -*- coding: utf-8 -*-
from odoo import api, fields, models


class FePyRecepcionEquivalencia(models.Model):
    """Qué producto propio corresponde a cada ítem de un proveedor.

    Se llena sola al confirmar una recepción, y sirve para sugerir el producto
    la próxima vez que ese proveedor facture lo mismo. Es una tabla propia (y
    no la lista de proveedores del producto) para no tocar los precios de
    compra de Compras.
    """
    _name = 'fe_py_recepcion.equivalencia'
    _description = 'Equivalencia de producto del proveedor'
    _order = 'partner_id, codigo, descripcion'

    partner_id = fields.Many2one('res.partner', string='Proveedor', required=True, index=True,
                                 ondelete='cascade')
    codigo = fields.Char(string='Código del proveedor',
                         help='Código interno (dCodInt) que usa el proveedor en su factura.')
    descripcion = fields.Char(string='Descripción del proveedor',
                              help='Se usa para reconocer el ítem cuando el proveedor no informa código.')
    producto_id = fields.Many2one('product.product', string='Producto', required=True,
                                  ondelete='cascade')
    company_id = fields.Many2one('res.company', string='Compañía', required=True,
                                 default=lambda self: self.env.company)

    @staticmethod
    def _clave(texto):
        return (texto or '').strip().casefold()

    @api.model
    def _buscar(self, partner, codigo, descripcion, company):
        """Registro de equivalencia para ese ítem, o vacío.

        Si el proveedor informa código, se busca por código; si no, por
        descripción exacta.
        """
        existentes = self.sudo().search([
            ('partner_id', '=', partner.id), ('company_id', '=', company.id)])
        codigo, descripcion = self._clave(codigo), self._clave(descripcion)
        if codigo:
            return existentes.filtered(lambda e: self._clave(e.codigo) == codigo)[:1]
        if descripcion:
            return existentes.filtered(
                lambda e: not self._clave(e.codigo) and self._clave(e.descripcion) == descripcion)[:1]
        return existentes.browse()

    @api.model
    def buscar_producto(self, partner, codigo, descripcion, company):
        return self._buscar(partner, codigo, descripcion, company).producto_id

    @api.model
    def registrar(self, partner, codigo, descripcion, producto, company):
        """Crea o actualiza la equivalencia de ese ítem del proveedor."""
        if not (partner and producto and ((codigo or '').strip() or (descripcion or '').strip())):
            return
        existente = self._buscar(partner, codigo, descripcion, company)
        if existente:
            if existente.producto_id != producto:
                existente.producto_id = producto
            return
        self.sudo().create({
            'partner_id': partner.id,
            'codigo': (codigo or '').strip(),
            'descripcion': (descripcion or '').strip(),
            'producto_id': producto.id,
            'company_id': company.id,
        })
