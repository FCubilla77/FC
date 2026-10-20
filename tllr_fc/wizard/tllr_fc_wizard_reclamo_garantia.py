# -*- coding: utf-8 -*-
from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError


class TllrFcWizardReclamoGarantia(models.TransientModel):
    """Reclamo de garantía: genera la recepción (tipo Garantía) del vehículo."""
    _name = 'tllr_fc.wizard.reclamo_garantia'
    _description = "Reclamo de garantía"
    _inherit = ['tllr_fc.mixin.wizard']

    ot_id = fields.Many2one('tllr_fc.ot', string="OT original", required=True, readonly=True)
    garantia_ids = fields.Many2many(
        'tllr_fc.garantia', string="Garantías reclamadas", required=True,
        domain="[('ot_id', '=', ot_id), ('reclamo_ot_id', '=', False)]")
    kilometraje_actual = fields.Integer(string="Kilometraje actual", required=True)
    descripcion = fields.Text(string="Descripción del reclamo", required=True)
    aviso = fields.Char(string="Aviso", compute='_compute_aviso')

    @api.model
    def default_get(self, campos):
        valores = super().default_get(campos)
        ot = self.env['tllr_fc.ot'].browse(valores.get('ot_id') or self.env.context.get('default_ot_id'))
        if ot:
            valores['kilometraje_actual'] = max(
                ot.vehiculo_id.kilometraje, ot.kilometraje_salida)
        return valores

    def _vencidas(self):
        self.ensure_one()
        hoy = fields.Date.context_today(self)
        return self.garantia_ids.filtered(
            lambda g: g._tllr_fc_estado_a(hoy, self.kilometraje_actual) != 'vigente')

    @api.depends('garantia_ids', 'kilometraje_actual')
    def _compute_aviso(self):
        for asistente in self:
            vencidas = asistente._vencidas() if asistente.garantia_ids else False
            asistente.aviso = (
                "Garantía vencida: %s. Solo un administrador de taller puede autorizar el reclamo." %
                ', '.join(vencidas.mapped('product_id.display_name'))) if vencidas else False

    def action_reclamar(self):
        self.ensure_one()
        ot = self.ot_id
        if not self.garantia_ids:
            raise UserError("Elegí al menos una garantía.")
        if self.garantia_ids.filtered(lambda g: g.reclamo_ot_id or g.ot_id != ot):
            raise UserError("Alguna garantía elegida ya tiene un reclamo o no pertenece a la OT.")
        if self._vencidas() and not self.env.context.get('tllr_fc_excepcion'):
            if not self.env.user.has_group('tllr_fc.group_administrador'):
                raise AccessError(
                    "Hay garantías vencidas: el reclamo solo lo autoriza un administrador de taller.")
            return self._tllr_fc_abrir_excepcion(
                'action_reclamar', 'administrador',
                "Reclamo fuera de plazo de la OT %s: %s." % (
                    ot.name, ', '.join(self._vencidas().mapped('product_id.display_name'))))
        servicios = self.garantia_ids.product_id.filtered(lambda p: p.type == 'service')
        if not servicios:
            servicios = ot.servicio_ids.filtered(lambda s: s.estado == 'terminado').product_id
        if not servicios:
            raise UserError("No hay servicios de la OT original para repetir en la garantía.")
        recepcion = self.env['tllr_fc.recepcion'].create({
            'company_id': ot.company_id.id,
            'vehiculo_id': ot.vehiculo_id.id,
            'partner_id': ot.partner_id.id,
            'kilometraje': self.kilometraje_actual,
            'tipo_ot_propuesto': 'garantia',
            'ot_origen_id': ot.id,
            'observaciones': "Reclamo de garantía de %s:\n%s" % (ot.name, self.descripcion),
            'servicio_ids': [Command.create({
                'product_id': p.id, 'observacion': "Garantía de %s" % ot.name}) for p in servicios],
        })
        self.garantia_ids.sudo().write({'reclamo_recepcion_id': recepcion.id})
        ot.message_post(body="Reclamo de garantía: se generó la recepción %s. %s" % (
            recepcion._get_html_link(), self.descripcion))
        return {
            'type': 'ir.actions.act_window', 'res_model': 'tllr_fc.recepcion',
            'res_id': recepcion.id, 'view_mode': 'form', 'target': 'current'}
