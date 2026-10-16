# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

# (código de la secuencia, prefijo, nombre). Numeración por compañía, relleno 5.
TLLR_FC_SECUENCIAS = [
    ('tllr_fc.vehiculo', 'VEH/', 'Taller - Vehículos'),
    ('tllr_fc.personal', 'PER/', 'Taller - Personal'),
    ('tllr_fc.puesto', 'PUE/', 'Taller - Puestos'),
    ('tllr_fc.turno', 'TUR/', 'Taller - Turnos'),
    ('tllr_fc.recepcion', 'REC/', 'Taller - Recepciones'),
    ('tllr_fc.ot', 'OT/', 'Taller - Órdenes de trabajo'),
    ('tllr_fc.control', 'QC/', 'Taller - Controles de calidad'),
    ('tllr_fc.entrega', 'ENT/', 'Taller - Entregas'),
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    # --- Asientos contables ---
    tllr_fc_generar_asientos = fields.Boolean(
        string="Generar asientos contables del taller", default=False)
    tllr_fc_diario_id = fields.Many2one(
        'account.journal', string="Diario de asientos del taller")
    tllr_fc_cuenta_wip_id = fields.Many2one(
        'account.account', string="Cuenta de trabajo en proceso")
    tllr_fc_cuenta_gasto_interna_id = fields.Many2one(
        'account.account', string="Cuenta de gasto de OT internas")
    tllr_fc_cuenta_gasto_garantia_id = fields.Many2one(
        'account.account', string="Cuenta de gasto de garantías")
    tllr_fc_cuenta_perdida_id = fields.Many2one(
        'account.account', string="Cuenta de pérdida por OT cancelada")
    tllr_fc_asiento_horas = fields.Boolean(
        string="Generar asiento por horas del personal", default=False)
    tllr_fc_cuenta_mano_obra_id = fields.Many2one(
        'account.account', string="Cuenta de mano de obra aplicada")

    # --- Facturación ---
    tllr_fc_diario_venta_id = fields.Many2one(
        'account.journal', string="Diario de factura de venta")

    # --- Control de calidad por tipo de OT ---
    tllr_fc_qc_cliente = fields.Boolean(
        string="Control de calidad en OT de Cliente", default=False)
    tllr_fc_qc_interno = fields.Boolean(
        string="Control de calidad en OT Interna", default=False)
    tllr_fc_qc_garantia = fields.Boolean(
        string="Control de calidad en OT de Garantía", default=False)

    # --- Otros ---
    tllr_fc_usa_terceros = fields.Boolean(
        string="Usa mercadería de terceros", default=False)
    tllr_fc_ubicacion_terceros_id = fields.Many2one(
        'stock.location', string="Ubicación de mercadería de terceros")
    tllr_fc_aprobacion_adicional = fields.Selection(
        [('obligatoria', "Obligatoria"), ('recomendada', "Recomendada")],
        string="Aprobación de trabajos adicionales", default='obligatoria',
        required=True)

    @api.constrains(
        'tllr_fc_generar_asientos', 'tllr_fc_diario_id', 'tllr_fc_cuenta_wip_id',
        'tllr_fc_cuenta_gasto_interna_id', 'tllr_fc_cuenta_gasto_garantia_id',
        'tllr_fc_cuenta_perdida_id', 'tllr_fc_asiento_horas',
        'tllr_fc_cuenta_mano_obra_id')
    def _check_tllr_fc_asientos(self):
        for compania in self:
            if compania.tllr_fc_generar_asientos and not (
                    compania.tllr_fc_diario_id
                    and compania.tllr_fc_cuenta_wip_id
                    and compania.tllr_fc_cuenta_gasto_interna_id
                    and compania.tllr_fc_cuenta_gasto_garantia_id
                    and compania.tllr_fc_cuenta_perdida_id):
                raise ValidationError(
                    "Para generar asientos contables del taller debe indicar el diario "
                    "y las cuentas de trabajo en proceso, gasto de OT internas, "
                    "gasto de garantías y pérdida por OT cancelada.")
            if compania.tllr_fc_asiento_horas and not (
                    compania.tllr_fc_generar_asientos
                    and compania.tllr_fc_cuenta_mano_obra_id):
                raise ValidationError(
                    "El asiento por horas del personal requiere tener activados los "
                    "asientos contables del taller y la cuenta de mano de obra aplicada.")

    def _tllr_fc_crear_secuencias(self):
        """Crea (si faltan) las secuencias del taller de cada compañía."""
        secuencia = self.env['ir.sequence'].sudo()
        for compania in self:
            for codigo, prefijo, nombre in TLLR_FC_SECUENCIAS:
                existe = secuencia.search_count([
                    ('code', '=', codigo),
                    ('company_id', '=', compania.id),
                ])
                if not existe:
                    secuencia.create({
                        'name': nombre,
                        'code': codigo,
                        'prefix': prefijo,
                        'padding': 5,
                        'number_next': 1,
                        'number_increment': 1,
                        'company_id': compania.id,
                    })

    @api.model_create_multi
    def create(self, vals_list):
        companias = super().create(vals_list)
        companias._tllr_fc_crear_secuencias()
        return companias
