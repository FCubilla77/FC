# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.fe_py_recepcion.models import utilidades

EPSILON_CANTIDAD = 1e-6


class FePyRecepcionDocumento(models.Model):
    _inherit = 'fe_py_recepcion.documento'

    vincular_compras = fields.Boolean(compute='_compute_vincular_compras')
    purchase_id = fields.Many2one(
        'purchase.order', string='Cotización', tracking=True, copy=False, ondelete='set null',
        domain="[('company_id', '=', company_id), ('state', 'in', ('purchase', 'done')), "
               "('invoice_status', '!=', 'invoiced')]",
        help='Orden de compra confirmada con algo pendiente de facturar. Como en el estándar '
             'de Odoo, las líneas del XML se pueden vincular o dejar sin vincular.')

    @api.depends('company_id.fe_py_recepcion_vincular_compras')
    def _compute_vincular_compras(self):
        for doc in self:
            doc.vincular_compras = doc.company_id.fe_py_recepcion_vincular_compras

    def _diagnostico(self):
        bloqueos, avisos = super()._diagnostico()
        if self.vincular_compras and self.purchase_id and self.partner_id:
            if self.purchase_id.partner_id.commercial_partner_id != self.partner_id.commercial_partner_id:
                avisos.append(_(
                    'La cotización %(orden)s es de otro proveedor (%(proveedor)s).',
                    orden=self.purchase_id.name, proveedor=self.purchase_id.partner_id.display_name))
        return bloqueos, avisos

    def _vals_factura(self, avisos=None):
        vals = super()._vals_factura(avisos)
        if self.vincular_compras and self.purchase_id:
            vals['invoice_origin'] = self.purchase_id.name
        return vals

    def _vals_linea_factura(self, linea, avisos=None):
        vals = super()._vals_linea_factura(linea, avisos)
        if self.vincular_compras and linea.purchase_line_id:
            vals['purchase_line_id'] = linea.purchase_line_id.id
        return vals

    def _post_confirmar(self, move):
        super()._post_confirmar(move)
        if self.vincular_compras and self.purchase_id:
            self.purchase_id.message_post(body=_(
                'Factura de proveedor %(factura)s generada desde la factura electrónica recibida %(doc)s.',
                factura=move.display_name, doc=self.name))

    # ------------------------------------------------------------------
    # Coincidencia exacta entre el XML y la cotización
    # ------------------------------------------------------------------
    def _cantidad_pendiente(self, linea_compra):
        """Cantidad de la línea de la cotización que todavía no se facturó.

        Odoo cuenta como facturada la cantidad de toda factura no cancelada, también las que
        están en borrador. La factura que generó esta misma recepción no debe restarse de lo
        pendiente: si no, después de generarla la cotización parecería no tener nada pendiente
        y la factura no podría publicarse sola."""
        pendiente = linea_compra.product_qty - linea_compra.qty_invoiced
        propia = self.move_id
        if propia and propia.state != 'cancel':
            for linea in propia.invoice_line_ids.filtered(
                    lambda l: l.purchase_line_id == linea_compra):
                cantidad = linea.product_uom_id._compute_quantity(
                    linea.quantity, linea_compra.product_uom_id)
                # Odoo suma las facturas y resta las notas de crédito en qty_invoiced
                pendiente += cantidad if propia.move_type == 'in_invoice' else -cantidad
        return pendiente

    def _lineas_pendientes(self, orden):
        return orden.order_line.filtered(
            lambda pl: not pl.display_type and self._cantidad_pendiente(pl) > EPSILON_CANTIDAD)

    def _elegir_linea_compra(self, linea, lineas_compra, usadas):
        """Línea de la cotización para una línea del XML: del mismo producto, todavía sin usar,
        y de preferencia con la misma cantidad pendiente."""
        candidatas = lineas_compra.filtered(
            lambda pl: pl.product_id == linea.producto_id and pl not in usadas)
        exactas = candidatas.filtered(
            lambda pl: abs(self._cantidad_pendiente(pl) - linea.cantidad) <= EPSILON_CANTIDAD)
        return (exactas or candidatas)[:1]

    def _diferencias_con_cotizacion(self, orden):
        """Lista de diferencias entre el XML y la cotización. Vacía si coinciden exactamente:
        mismos productos (uno a uno, sin líneas de más), misma cantidad y mismos totales e
        IVA dentro de la tolerancia de la compañía."""
        self.ensure_one()
        diferencias = []
        if orden.currency_id != self.currency_id:
            diferencias.append(_('la moneda es %s', orden.currency_id.name))
        tolerancia = self.company_id._fe_py_recepcion_tolerancia_en(self.currency_id)
        lineas_compra = self._lineas_pendientes(orden)
        usadas = self.env['purchase.order.line']
        for linea in self.line_ids.sorted('orden'):
            etiqueta = _('línea %s', linea.orden)
            candidata = self._elegir_linea_compra(linea, lineas_compra, usadas)
            if not candidata:
                diferencias.append(_('%s: el producto no está pendiente en la cotización', etiqueta))
                continue
            usadas |= candidata
            pendiente = self._cantidad_pendiente(candidata)
            if abs(pendiente - linea.cantidad) > EPSILON_CANTIDAD:
                diferencias.append(_(
                    '%(linea)s: la cantidad del XML (%(xml)s) no es la pendiente de la cotización (%(oc)s)',
                    linea=etiqueta, xml=linea.cantidad, oc=pendiente))
            proporcion = pendiente / candidata.product_qty if candidata.product_qty else 0.0
            if not utilidades.dentro_de_tolerancia(candidata.price_total * proporcion - linea.total_xml, tolerancia):
                diferencias.append(_('%s: el total no coincide', etiqueta))
            if not utilidades.dentro_de_tolerancia(candidata.price_tax * proporcion - linea.iva_xml, tolerancia):
                diferencias.append(_('%s: el IVA no coincide', etiqueta))
        sobrantes = lineas_compra - usadas
        if sobrantes:
            diferencias.append(_(
                'la cotización tiene productos pendientes que el XML no trae (%s)',
                ', '.join(sobrantes.mapped('product_id.display_name'))))
        return diferencias

    def _cotizaciones_candidatas(self):
        """Órdenes de compra confirmadas del proveedor con algo pendiente de facturar que
        tienen al menos un producto en común con la recepción."""
        self.ensure_one()
        comercial = self.partner_id.commercial_partner_id
        ordenes = self.env['purchase.order'].search([
            ('company_id', '=', self.company_id.id),
            ('partner_id', 'child_of', comercial.id),
            ('state', 'in', ('purchase', 'done')),
            ('invoice_status', '!=', 'invoiced'),
        ])
        productos = self.line_ids.mapped('producto_id')
        return ordenes.filtered(
            lambda o: any(pl.product_id in productos for pl in self._lineas_pendientes(o)))

    def _preparar_cotizacion_automatica(self):
        """Vincula la cotización que coincide exactamente.
        - Sin cotizaciones candidatas: sigue sin vincular.
        - Una que coincide exacta: se vincula.
        - Candidatas sin coincidencia exacta, o varias que coinciden: corta (el registro queda en
          Cargado) para que el usuario elija la cotización a mano y no se facture dos veces."""
        super()._preparar_cotizacion_automatica()
        if not self.vincular_compras:
            return
        if self.purchase_id:
            self.action_vincular_lineas()
            return
        candidatas = self._cotizaciones_candidatas()
        if not candidatas:
            return
        exactas = candidatas.filtered(lambda o: not self._diferencias_con_cotizacion(o))
        if len(exactas) == 1:
            self.purchase_id = exactas
            self.action_vincular_lineas()
            if self.line_ids.filtered(lambda l: not l.purchase_line_id):
                raise UserError(_('No se pudieron vincular todas las líneas con la cotización %s.',
                                  exactas.name))
            return
        if len(exactas) > 1:
            raise UserError(_(
                'Hay más de una cotización que coincide exactamente (%s). Elija la que corresponde '
                'y use «Reprocesar».', ', '.join(exactas.mapped('name'))))
        detalle = '; '.join(
            '%s (%s)' % (orden.name, ', '.join(self._diferencias_con_cotizacion(orden)[:3]))
            for orden in candidatas[:3])
        raise UserError(_(
            'El proveedor tiene cotizaciones con productos de este documento, pero ninguna '
            'coincide exactamente: %s. Elija la cotización a mano, o quite el vínculo, y use '
            '«Reprocesar».', detalle))

    def _motivos_cotizacion(self):
        motivos = super()._motivos_cotizacion()
        if self.vincular_compras and self.purchase_id:
            diferencias = self._diferencias_con_cotizacion(self.purchase_id)
            if diferencias:
                motivos.append(_(
                    'La cotización %(orden)s no coincide exactamente con el XML: %(dif)s.',
                    orden=self.purchase_id.name, dif=', '.join(diferencias)))
        return motivos

    def _motivos_recepcion_pendiente(self):
        """Un producto que se factura «sobre cantidades recibidas» no puede facturarse antes de
        recibirse: la factura queda en borrador hasta que haya recepción. El módulo no toca la
        recepción de mercadería, que es del encargado de depósito."""
        motivos = super()._motivos_recepcion_pendiente()
        if not (self.vincular_compras and self.purchase_id):
            return motivos
        for linea in self.line_ids.filtered('purchase_line_id'):
            linea_compra = linea.purchase_line_id
            if linea_compra.product_id.purchase_method == 'receive' \
                    and linea_compra.qty_received + EPSILON_CANTIDAD < linea.cantidad:
                motivos.append(_(
                    'Línea %(linea)s: "%(producto)s" se factura sobre cantidades recibidas y la '
                    'cotización %(orden)s tiene recibido %(recibido)s de %(xml)s.',
                    linea=linea.orden, producto=linea.producto_id.display_name,
                    orden=self.purchase_id.name, recibido=linea_compra.qty_received,
                    xml=linea.cantidad))
        return motivos

    def _linea_con_lote_cubierta(self, linea):
        """Con la línea vinculada a una cotización, el lote o serie se asigna al recibir la
        mercadería: no impide publicar la factura."""
        return bool(self.vincular_compras and linea.purchase_line_id) or \
            super()._linea_con_lote_cubierta(linea)

    def action_vincular_lineas(self):
        """Vincula las líneas que tienen producto con la línea de la cotización del mismo
        producto que todavía no se usó (de preferencia con la misma cantidad pendiente). Las
        demás quedan sin vincular."""
        for doc in self:
            if not doc.purchase_id:
                raise UserError(_('Primero elija la cotización.'))
            lineas_compra = doc.purchase_id.order_line.filtered(lambda pl: not pl.display_type)
            usadas = doc.line_ids.mapped('purchase_line_id')
            for linea in doc.line_ids.filtered(lambda l: l.producto_id and not l.purchase_line_id):
                candidata = doc._elegir_linea_compra(linea, lineas_compra, usadas)
                if candidata:
                    linea.purchase_line_id = candidata
                    usadas |= candidata
        return True
