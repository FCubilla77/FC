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
                'pendiente_aprobacion').ids)]
            valores['producto_ids'] = [(6, 0, ot.producto_ids.filtered(
                'pendiente_aprobacion').ids)]
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
        if (servicios.filtered(lambda s: not s.pendiente_aprobacion)
                or productos.filtered(lambda p: not p.pendiente_aprobacion)):
            raise UserError("Solo se registra la aprobación de líneas pendientes de aprobación.")
        detalle = self.env['tllr_fc.ot.aprobacion']._tllr_fc_detalle_lineas(servicios, productos)
        aprobacion = self.env['tllr_fc.ot.aprobacion'].create({
            'ot_id': self.ot_id.id, 'medio': self.medio, 'persona': self.persona,
            'fecha': self.fecha, 'estado': self.estado, 'notas': self.notas,
            'detalle': detalle,
            'servicio_ids': [(6, 0, servicios.ids)],
            'producto_ids': [(6, 0, productos.ids)],
        })
        if self.estado == 'aprobado':
            self.env['tllr_fc.ot.aprobacion']._tllr_fc_aprobar_lineas(aprobacion, servicios, productos)
            self.ot_id.message_post(body="Adicionales aprobados por %s (%s).<br/>%s" % (
                self.persona, dict(self._fields['medio'].selection)[self.medio],
                detalle.replace('\n', '<br/>')))
        else:
            nuevos_s = servicios.filtered(lambda s: s.state_aprobacion == 'pendiente')
            nuevos_p = productos.filtered(lambda p: p.state_aprobacion == 'pendiente')
            exceso_s, exceso_p = servicios - nuevos_s, productos - nuevos_p
            if (nuevos_s.filtered(lambda s: s.estado != 'pendiente' and not s.cobrar_cliente)
                    or nuevos_p.filtered(
                        lambda p: p.cantidad_consumida and not p.cobrar_cliente)
                    or exceso_s.filtered(lambda s: s.estado != 'pendiente')
                    or exceso_p.filtered(
                        lambda p: p.cantidad_consumida > p.cantidad_cubierta
                        or p.cantidad_utilizada > p.cantidad_cubierta)):
                raise UserError("No se puede rechazar: ya se ejecutó parte de los trabajos.")
            self.ot_id.message_post(body="Adicionales RECHAZADOS por %s (%s). Se quitan de la OT (las líneas a cobrar de una garantía quedan cubiertas por la garantía; los excedentes de cantidad vuelven a lo cubierto).<br/>%s" % (
                self.persona, dict(self._fields['medio'].selection)[self.medio],
                detalle.replace('\n', '<br/>')))
            # En una OT de garantía, el cliente que rechaza pagar no quita la línea: queda
            # cubierta por la garantía (se deja de cobrar).
            cobros_s = nuevos_s.filtered('cobrar_cliente')
            cobros_p = nuevos_p.filtered('cobrar_cliente')
            for lineas in (cobros_s, cobros_p):
                lineas.with_context(tllr_fc_permitir_write=True).write({'cobrar_cliente': False})
            (nuevos_s - cobros_s).with_context(tllr_fc_permitir_write=True).unlink()
            (nuevos_p - cobros_p).with_context(tllr_fc_permitir_write=True).unlink()
            # Excedentes: la cantidad vuelve a lo cubierto.
            for servicio in exceso_s:
                servicio.with_context(tllr_fc_permitir_write=True).cantidad = servicio.cantidad_cubierta
            for producto in exceso_p:
                producto.with_context(tllr_fc_permitir_write=True).cantidad_reservada = (
                    producto.cantidad_cubierta + producto.cantidad_no_utilizada)
        return {'type': 'ir.actions.act_window_close'}
