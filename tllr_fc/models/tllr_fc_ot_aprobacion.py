# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TllrFcOtAprobacion(models.Model):
    """Aprobación (o rechazo) del cliente de trabajos adicionales."""
    _name = 'tllr_fc.ot.aprobacion'
    _description = "Aprobación de trabajos adicionales"
    _order = 'fecha desc, id desc'

    ot_id = fields.Many2one(
        'tllr_fc.ot', string="OT", required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(
        'res.company', string="Compañía", related='ot_id.company_id',
        store=True, index=True)
    medio = fields.Selection([
        ('telefono', "Teléfono"),
        ('mensaje', "Mensaje"),
        ('presencial', "Presencial"),
        ('otro', "Otro"),
        ('supervisor', "Autorización del supervisor"),
    ], string="Medio", required=True, default='telefono')
    persona = fields.Char(string="Quién aprobó", required=True)
    fecha = fields.Datetime(string="Fecha", required=True, default=fields.Datetime.now)
    estado = fields.Selection([
        ('aprobado', "Aprobado"),
        ('rechazado', "Rechazado"),
    ], string="Resultado", required=True, default='aprobado')
    servicio_ids = fields.Many2many(
        'tllr_fc.ot.servicio', 'tllr_fc_ot_aprobacion_servicio_rel', 'aprobacion_id',
        'servicio_id', string="Servicios")
    producto_ids = fields.Many2many(
        'tllr_fc.ot.producto', 'tllr_fc_ot_aprobacion_producto_rel', 'aprobacion_id',
        'producto_id', string="Repuestos, insumos y accesorios")
    detalle = fields.Text(
        string="Líneas cubiertas", readonly=True,
        help="Descripción de las líneas: se conserva aunque la línea se elimine.")
    notas = fields.Text(string="Notas")
    registrado_por_id = fields.Many2one(
        'res.users', string="Registrado por", default=lambda self: self.env.user, readonly=True)

    @api.model
    def _tllr_fc_detalle_lineas(self, servicios, productos):
        """Descripción de las líneas cubiertas (se conserva aunque la línea se elimine)."""
        lineas = []
        for servicio in servicios:
            if servicio.state_aprobacion == 'pendiente':
                lineas.append("Servicio: %s" % servicio.product_id.display_name)
            else:
                lineas.append("Servicio: %s: +%s (de %s a %s)" % (
                    servicio.product_id.display_name, servicio.cantidad_excedente,
                    servicio.cantidad_cubierta, servicio.cantidad))
        for producto in productos:
            if producto.state_aprobacion == 'pendiente':
                lineas.append("Producto: %s × %s" % (
                    producto.product_id.display_name, producto.cantidad_reservada))
            else:
                lineas.append("Producto: %s: +%s (de %s a %s)" % (
                    producto.product_id.display_name, producto.cantidad_excedente,
                    producto.cantidad_cubierta, producto._tllr_fc_cantidad_pedida()))
        return '\n'.join(lineas)

    @api.model
    def _tllr_fc_aprobar_lineas(self, aprobacion, servicios, productos):
        """Marca las líneas como aprobadas y cubre su cantidad."""
        for lineas in (servicios, productos):
            for linea in lineas:
                valores = {'aprobacion_id': aprobacion.id}
                if linea.state_aprobacion == 'pendiente':
                    valores['state_aprobacion'] = 'aprobado'
                linea.with_context(tllr_fc_permitir_write=True).write(valores)
            lineas._tllr_fc_cubrir()

    @api.model
    def _tllr_fc_registrar_autorizacion(self, ot, servicios, productos):
        """El supervisor autoriza sin aprobación del cliente: queda un registro propio."""
        detalle = self._tllr_fc_detalle_lineas(servicios, productos)
        aprobacion = self.create({
            'ot_id': ot.id, 'medio': 'supervisor', 'persona': self.env.user.name,
            'estado': 'aprobado', 'detalle': detalle,
            'notas': self.env.context.get('tllr_fc_motivo', ''),
            'servicio_ids': [(6, 0, servicios.ids)],
            'producto_ids': [(6, 0, productos.ids)],
        })
        for lineas in (servicios, productos):
            for linea in lineas:
                valores = {'aprobacion_id': aprobacion.id}
                if linea.state_aprobacion == 'pendiente':
                    valores['state_aprobacion'] = 'autorizado'
                linea.with_context(tllr_fc_permitir_write=True).write(valores)
            lineas._tllr_fc_cubrir()
        return aprobacion
