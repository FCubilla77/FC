# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class TllrFcOtAjusteCosto(models.Model):
    """Ajuste de costo posterior de una OT (solo administrador de taller)."""
    _name = 'tllr_fc.ot.ajuste_costo'
    _description = "Ajuste de costo de la orden de trabajo"
    _order = 'fecha desc, id desc'

    ot_id = fields.Many2one(
        'tllr_fc.ot', string="OT", required=True, ondelete='restrict', index=True,
        domain="[('state', 'in', ('listo', 'entregado', 'cancelada'))]")
    company_id = fields.Many2one(
        'res.company', string="Compañía", related='ot_id.company_id', store=True, index=True)
    currency_id = fields.Many2one('res.currency', related='ot_id.company_id.currency_id')
    asientos_activos = fields.Boolean(compute='_compute_asientos_activos')
    fecha = fields.Date(string="Fecha", required=True, default=fields.Date.context_today)
    monto = fields.Monetary(
        string="Monto del ajuste", currency_field='currency_id', required=True,
        help="Positivo: aumenta el costo de la OT. Negativo: lo disminuye.")
    motivo = fields.Text(string="Motivo", required=True)
    cuenta_debe_id = fields.Many2one(
        'account.account', string="Cuenta de costo", check_company=True,
        help="Cuenta de costo o gasto que se ajusta. Por defecto, la del tipo de OT.")
    cuenta_haber_id = fields.Many2one(
        'account.account', string="Contrapartida", check_company=True,
        help="Cuenta contra la que se registra la diferencia (por ejemplo, Inventario).")
    asiento_id = fields.Many2one(
        'account.move', string="Asiento", readonly=True, copy=False, ondelete='restrict')
    usuario_id = fields.Many2one(
        'res.users', string="Registrado por", default=lambda self: self.env.user, readonly=True)

    @api.depends('ot_id')
    def _compute_asientos_activos(self):
        for ajuste in self:
            ajuste.asientos_activos = bool(
                ajuste.ot_id and ajuste.ot_id._tllr_fc_asientos_activos())

    def _tllr_fc_cuenta_costo_defecto(self):
        self.ensure_one()
        compania = self.ot_id.company_id.sudo()
        ot = self.ot_id
        if ot.state == 'cancelada' and not ot.liquidada:
            return compania.tllr_fc_cuenta_perdida_id
        return {
            'cliente': compania.tllr_fc_cuenta_costo_ventas_id,
            'interno': compania.tllr_fc_cuenta_gasto_interna_id,
            'garantia': compania.tllr_fc_cuenta_gasto_garantia_id,
        }[ot.tipo]

    @api.onchange('ot_id')
    def _onchange_ot_id(self):
        if self.ot_id and not self.cuenta_debe_id:
            self.cuenta_debe_id = self._tllr_fc_cuenta_costo_defecto()

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.user.has_group('tllr_fc.group_administrador'):
            raise AccessError("Solo el administrador de taller registra ajustes de costo.")
        ajustes = super().create(vals_list)
        for ajuste in ajustes:
            ajuste._tllr_fc_generar()
        return ajustes

    def _tllr_fc_generar(self):
        self.ensure_one()
        ot = self.ot_id
        if ot.state not in ('listo', 'entregado', 'cancelada'):
            raise UserError(
                "El ajuste de costo se registra cuando la OT ya terminó (lista, entregada o cancelada).")
        if self.company_id.currency_id.is_zero(self.monto):
            raise UserError("El monto del ajuste no puede ser cero.")
        if not ot._tllr_fc_asientos_activos():
            ot.message_post(body="Ajuste de costo de %s registrado por %s (sin asiento: los "
                                 "asientos del taller están desactivados). Motivo: %s" % (
                                     self.monto, self.env.user.name, self.motivo))
            return
        debe = self.cuenta_debe_id or self._tllr_fc_cuenta_costo_defecto()
        haber = self.cuenta_haber_id
        if not debe or not haber:
            raise UserError(
                "Indicá la cuenta de costo y la contrapartida del ajuste (por ejemplo, Inventario).")
        monto = abs(self.monto)
        if self.monto > 0:
            lineas = [
                {'account': debe, 'debit': monto, 'credit': 0.0, 'analitica': True, 'name': self.motivo[:60]},
                {'account': haber, 'debit': 0.0, 'credit': monto, 'analitica': False, 'name': self.motivo[:60]}]
        else:
            lineas = [
                {'account': haber, 'debit': monto, 'credit': 0.0, 'analitica': False, 'name': self.motivo[:60]},
                {'account': debe, 'debit': 0.0, 'credit': monto, 'analitica': True, 'name': self.motivo[:60]}]
        self.with_context(tllr_fc_permitir_write=True).asiento_id = ot._tllr_fc_crear_asiento(
            'ajuste', lineas, "ajuste de costo", fecha=self.fecha)

    def write(self, vals):
        if not self.env.context.get('tllr_fc_permitir_write'):
            raise UserError("Un ajuste de costo no se modifica: registrá otro ajuste con el monto inverso.")
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_bloqueado(self):
        raise UserError("Un ajuste de costo no se elimina: registrá otro ajuste con el monto inverso.")
