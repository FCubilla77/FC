# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class TllrFcWizardAprobacion(models.TransientModel):
    """Registra la aprobación (o el rechazo) del cliente de trabajos adicionales."""
    _name = 'tllr_fc.wizard.aprobacion'
    _description = "Registrar aprobación de adicionales"

    ot_id = fields.Many2one('tllr_fc.ot', string="OT", required=True, ondelete='cascade')
    medio = fields.Selection([
        ('telefono', "Teléfono"),
        ('mensaje', "Mensaje"),
        ('presencial', "Presencial"),
        ('otro', "Otro"),
    ], string="Medio", required=True, default='telefono')
    persona = fields.Char(string="Quién aprobó", required=True)
    fecha = fields.Datetime(string="Fecha", required=True, default=fields.Datetime.now)
    estado = fields.Selection([
        ('aprobado', "El cliente aprobó"),
        ('rechazado', "El cliente rechazó"),
    ], string="Resultado", required=True, default='aprobado')
    servicio_ids = fields.Many2many(
        'tllr_fc.ot.servicio', 'tllr_fc_wiz_aprob_servicio_rel', 'wizard_id', 'servicio_id',
        string="Servicios")
    producto_ids = fields.Many2many(
        'tllr_fc.ot.producto', 'tllr_fc_wiz_aprob_producto_rel', 'wizard_id', 'producto_id',
        string="Repuestos, insumos y accesorios")
    notas = fields.Text(string="Notas")

    @api.model
    def default_get(self, campos):
        valores = super().default_get(campos)
        ot = self.env['tllr_fc.ot'].browse(
            valores.get('ot_id') or self.env.context.get('default_ot_id'))
        if ot:
            valores['servicio_ids'] = [(6, 0, ot.servicio_ids.filtered(
                lambda s: s.state_aprobacion == 'pendiente').ids)]
            valores['producto_ids'] = [(6, 0, ot.producto_ids.filtered(
                lambda p: p.state_aprobacion == 'pendiente').ids)]
        return valores

    def action_registrar(self):
        self.ensure_one()
        if not self.env.user.has_group('tllr_fc.group_supervisor'):
            raise AccessError("Solo el supervisor o el administrador de taller registran aprobaciones.")
        servicios, productos = self.servicio_ids, self.producto_ids
        if not servicios and not productos:
            raise UserError("Elegí al menos una línea.")
        if any(linea.ot_id != self.ot_id for linea in servicios) or any(
                linea.ot_id != self.ot_id for linea in productos):
            raise UserError("Las líneas deben pertenecer a la OT.")
        if (servicios.filtered(lambda s: s.state_aprobacion != 'pendiente')
                or productos.filtered(lambda p: p.state_aprobacion != 'pendiente')):
            raise UserError("Solo se registra la aprobación de líneas pendientes de aprobación.")
        detalle = '\n'.join(
            ["Servicio: %s" % s.product_id.display_name for s in servicios]
            + ["Producto: %s × %s" % (p.product_id.display_name, p.cantidad_reservada) for p in productos])
        aprobacion = self.env['tllr_fc.ot.aprobacion'].create({
            'ot_id': self.ot_id.id, 'medio': self.medio, 'persona': self.persona,
            'fecha': self.fecha, 'estado': self.estado, 'notas': self.notas,
            'detalle': detalle,
            'servicio_ids': [(6, 0, servicios.ids)],
            'producto_ids': [(6, 0, productos.ids)],
        })
        ctx = self.with_context(tllr_fc_permitir_write=True)
        if self.estado == 'aprobado':
            servicios.with_context(tllr_fc_permitir_write=True).write(
                {'state_aprobacion': 'aprobado', 'aprobacion_id': aprobacion.id})
            productos.with_context(tllr_fc_permitir_write=True).write(
                {'state_aprobacion': 'aprobado', 'aprobacion_id': aprobacion.id})
            self.ot_id.message_post(body="Adicionales aprobados por %s (%s).<br/>%s" % (
                self.persona, dict(self._fields['medio'].selection)[self.medio],
                detalle.replace('\n', '<br/>')))
        else:
            if (servicios.filtered(lambda s: s.estado != 'pendiente' and not s.cobrar_cliente)
                    or productos.filtered(
                        lambda p: p.cantidad_consumida and not p.cobrar_cliente)):
                raise UserError("No se puede rechazar: ya se ejecutó parte de los trabajos.")
            self.ot_id.message_post(body="Adicionales RECHAZADOS por %s (%s). Se quitan de la OT (las líneas a cobrar de una garantía quedan cubiertas por la garantía).<br/>%s" % (
                self.persona, dict(self._fields['medio'].selection)[self.medio],
                detalle.replace('\n', '<br/>')))
            # En una OT de garantía, el cliente que rechaza pagar no quita la línea: queda
            # cubierta por la garantía (se deja de cobrar).
            cobros_s = servicios.filtered('cobrar_cliente')
            cobros_p = productos.filtered('cobrar_cliente')
            for lineas in (cobros_s, cobros_p):
                lineas.with_context(tllr_fc_permitir_write=True).write({'cobrar_cliente': False})
            (servicios - cobros_s).with_context(tllr_fc_permitir_write=True).unlink()
            (productos - cobros_p).with_context(tllr_fc_permitir_write=True).unlink()
        return {'type': 'ir.actions.act_window_close'}
