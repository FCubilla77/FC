# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class TllrFcWizardCancelar(models.TransientModel):
    """Cancelación de la OT, con o sin liquidación de lo ejecutado."""
    _name = 'tllr_fc.wizard.cancelar'
    _description = "Cancelación de OT"
    _inherit = ['tllr_fc.mixin.wizard']

    ot_id = fields.Many2one('tllr_fc.ot', string="OT", required=True, readonly=True)
    motivo_id = fields.Many2one(
        'tllr_fc.motivo', string="Motivo de cancelación", required=True,
        domain="[('tipo', '=', 'cancelacion')]")
    trabajo_realizado = fields.Boolean(compute='_compute_datos')
    puede_liquidar = fields.Boolean(compute='_compute_datos')
    liquidar = fields.Boolean(
        string="Cancelar y facturar lo realizado",
        help="Factura solo los servicios terminados y los repuestos consumidos. "
             "Solo en OT de cliente con trabajo realizado.")
    vista_previa = fields.Html(string="Qué ocurrirá", compute='_compute_vista_previa', sanitize=False)
    confirmo = fields.Boolean(string="Confirmo la cancelación de la OT")

    @api.depends('ot_id')
    def _compute_datos(self):
        for asistente in self:
            ot = asistente.ot_id
            realizado = bool(ot) and ot._tllr_fc_trabajo_realizado()
            asistente.trabajo_realizado = realizado
            asistente.puede_liquidar = realizado and ot.tipo == 'cliente'

    @api.depends('ot_id', 'liquidar')
    def _compute_vista_previa(self):
        for asistente in self:
            ot = asistente.ot_id
            if not ot:
                asistente.vista_previa = False
                continue
            items = []
            reservas = ot.producto_ids.filtered(
                lambda p: p.cantidad_reservada > p.cantidad_consumida)
            if reservas:
                items.append("Se liberan las reservas de stock sin consumir (%s línea/s)." % len(reservas))
            consumos = ot.producto_ids.filtered('cantidad_consumida')
            if consumos:
                items.append("Los consumos ya validados (%s línea/s) no se devuelven a stock." % len(consumos))
            borradores = ot._tllr_fc_facturas().filtered(lambda m: m.state == 'draft')
            if borradores:
                items.append("Se elimina la factura en borrador de la OT.")
            terminados = ot.servicio_ids.filtered(lambda s: s.estado == 'terminado')
            if asistente.liquidar:
                items.append("Se genera la factura de lo realizado: %s servicio/s terminado/s y los "
                             "repuestos consumidos." % len(terminados))
            elif asistente.trabajo_realizado:
                items.append("<b>Se cancela sin liquidar lo ejecutado:</b> requiere la autorización "
                             "de un supervisor con motivo.")
            asistente.vista_previa = "<ul>%s</ul>" % ''.join('<li>%s</li>' % i for i in items)

    @api.onchange('puede_liquidar')
    def _onchange_puede_liquidar(self):
        if not self.puede_liquidar:
            self.liquidar = False

    def action_confirmar(self):
        self.ensure_one()
        if not self.env.user.has_group('tllr_fc.group_supervisor'):
            raise AccessError("Solo el supervisor o el administrador de taller pueden cancelar la OT.")
        if not self.confirmo:
            raise UserError("Marcá la confirmación para cancelar la OT.")
        if self.liquidar and not self.puede_liquidar:
            raise UserError("Solo se liquida una OT de cliente con trabajo realizado.")
        if (self.trabajo_realizado and not self.liquidar
                and not self.env.context.get('tllr_fc_excepcion')):
            return self._tllr_fc_abrir_excepcion(
                'action_confirmar', 'supervisor',
                "Cancelar la OT %s sin liquidar lo ejecutado." % self.ot_id.name)
        if (self.liquidar and self.ot_id.adicionales_pendientes
                and not self.env.context.get('tllr_fc_excepcion')):
            return self._tllr_fc_abrir_excepcion(
                'action_confirmar', 'supervisor',
                "Hay %s adicional(es) (líneas nuevas o cantidades mayores) sin aprobación del "
                "cliente. Si continuás, solo se facturará lo aprobado." %
                self.ot_id.adicionales_pendientes)
        self.ot_id._tllr_fc_cancelar(self.motivo_id, self.liquidar)
        # Tras cancelar se pregunta si el vehículo se entrega al cliente.
        return {
            'type': 'ir.actions.act_window', 'name': "Entrega del vehículo",
            'res_model': 'tllr_fc.wizard.entrega_cancelada', 'view_mode': 'form',
            'target': 'new', 'context': {'default_ot_id': self.ot_id.id}}


class TllrFcWizardEntregaCancelada(models.TransientModel):
    """Pregunta, al cancelar una OT, si se entrega el vehículo al cliente."""
    _name = 'tllr_fc.wizard.entrega_cancelada'
    _description = "Entrega del vehículo de una OT cancelada"

    ot_id = fields.Many2one('tllr_fc.ot', string="OT", required=True, readonly=True)

    def _responder(self, entregar):
        self.ensure_one()
        ot = self.ot_id
        if not self.env.user.has_group('tllr_fc.group_supervisor'):
            raise AccessError("Solo el supervisor o el administrador de taller pueden decidir la entrega.")
        if ot.state != 'cancelada':
            raise UserError("La OT no está cancelada.")
        if entregar:
            ot.write({'entrega_habilitada': True})
            ot.message_post(body="Se habilitó la entrega del vehículo al cliente.")
        else:
            ot.message_post(body="Se decidió no entregar el vehículo por ahora (entrega no habilitada).")
        return {'type': 'ir.actions.act_window_close'}

    def action_si(self):
        return self._responder(True)

    def action_no(self):
        return self._responder(False)
