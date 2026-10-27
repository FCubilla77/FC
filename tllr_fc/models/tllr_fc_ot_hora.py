# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

LIMITE_HORAS_DIA = 12.0


class TllrFcOtHora(models.Model):
    """Horas trabajadas por una persona en la OT (total por persona y día)."""
    _name = 'tllr_fc.ot.hora'
    _description = "Horas trabajadas en la orden de trabajo"
    _order = 'fecha desc, id desc'

    ot_id = fields.Many2one(
        'tllr_fc.ot', string="OT", required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(
        'res.company', string="Compañía", related='ot_id.company_id',
        store=True, index=True)
    currency_id = fields.Many2one(
        'res.currency', related='ot_id.company_id.currency_id', string="Moneda")
    personal_id = fields.Many2one(
        'tllr_fc.personal', string="Personal", required=True, ondelete='restrict')
    puesto_line_id = fields.Many2one(
        'tllr_fc.ot.puesto', string="Puesto", ondelete='restrict', index=True,
        domain="[('ot_id', '=', ot_id)]",
        help="Puesto de la OT en el que se trabajaron las horas.")
    servicio_id = fields.Many2one(
        'tllr_fc.ot.servicio', string="Servicio", ondelete='restrict', index=True,
        domain="[('ot_id', '=', ot_id), ('puesto_line_id', '=', puesto_line_id)]",
        help="Servicio de la OT al que corresponden las horas.")
    personal_permitido_ids = fields.Many2many(
        'tllr_fc.personal', string="Personal que puede cargar estas horas",
        compute='_compute_personal_permitido')
    funcion_id = fields.Many2one(
        'tllr_fc.funcion', string="Función", readonly=True, ondelete='restrict',
        help="Se copia del personal al cargar las horas y no se recalcula: un cambio "
             "posterior de función no altera los costos de la OT.")
    fecha = fields.Date(string="Fecha", required=True, default=fields.Date.context_today)
    horas = fields.Float(string="Horas", required=True)
    costo_hora = fields.Monetary(
        string="Costo por hora", currency_field='currency_id',
        compute='_compute_costo', groups='tllr_fc.group_supervisor')
    costo = fields.Monetary(
        string="Costo", currency_field='currency_id',
        compute='_compute_costo', groups='tllr_fc.group_supervisor')
    horas_dia_persona = fields.Float(
        string="Horas del día (persona)", compute='_compute_horas_dia_persona')
    aviso = fields.Char(string="Aviso", compute='_compute_horas_dia_persona')

    @api.model
    def default_get(self, campos):
        """Con un solo servicio (o un solo puesto) en la OT, propone puesto y servicio."""
        valores = super().default_get(campos)
        ot = self.env['tllr_fc.ot'].browse(
            valores.get('ot_id') or self.env.context.get('default_ot_id'))
        if ot:
            servicio, puesto = ot._tllr_fc_servicio_puesto_unicos()
            if servicio and 'servicio_id' in campos and not valores.get('servicio_id'):
                valores['servicio_id'] = servicio.id
            if puesto and 'puesto_line_id' in campos and not valores.get('puesto_line_id'):
                valores['puesto_line_id'] = puesto.id
        return valores

    @api.depends('puesto_line_id.personal_ids', 'ot_id.state', 'ot_id.personal_horas_ids')
    def _compute_personal_permitido(self):
        for hora in self:
            if hora.ot_id.state == 'calidad':
                hora.personal_permitido_ids = hora.ot_id.personal_horas_ids
            else:
                hora.personal_permitido_ids = hora.puesto_line_id.personal_ids

    @api.depends('funcion_id', 'fecha', 'horas')
    def _compute_costo(self):
        for hora in self:
            costo_hora = hora.funcion_id._costo_a_fecha(hora.fecha) if (
                hora.funcion_id and hora.fecha) else 0.0
            hora.costo_hora = costo_hora
            hora.costo = costo_hora * hora.horas

    @api.depends('personal_id', 'fecha', 'horas')
    def _compute_horas_dia_persona(self):
        personal = self.mapped('personal_id').ids
        fechas = self.mapped('fecha')
        totales = {}
        if personal and fechas:
            datos = self.env['tllr_fc.ot.hora'].sudo()._read_group(
                [('personal_id', 'in', personal), ('fecha', 'in', fechas)],
                ['personal_id', 'fecha:day'], ['horas:sum'])
            totales = {(p.id, f): total for p, f, total in datos}
        for hora in self:
            total = totales.get((hora.personal_id.id, hora.fecha), 0.0)
            if not hora.id:  # línea nueva, todavía sin guardar
                total += hora.horas
            hora.horas_dia_persona = total
            hora.aviso = (
                "%s suma %.2f h el %s (más de %s h)." % (
                    hora.personal_id.name, total, hora.fecha, int(LIMITE_HORAS_DIA))
                if total > LIMITE_HORAS_DIA else False)

    @api.onchange('puesto_line_id')
    def _onchange_puesto_line_id(self):
        if self.servicio_id and self.servicio_id.puesto_line_id != self.puesto_line_id:
            self.servicio_id = False

    @api.onchange('servicio_id')
    def _onchange_servicio_id(self):
        if self.servicio_id and not self.puesto_line_id:
            self.puesto_line_id = self.servicio_id.puesto_line_id

    @api.constrains('servicio_id', 'puesto_line_id', 'ot_id')
    def _check_servicio_puesto(self):
        for hora in self:
            if hora.servicio_id and hora.servicio_id.ot_id != hora.ot_id:
                raise ValidationError("El servicio de las horas no pertenece a la OT.")
            if hora.puesto_line_id and hora.puesto_line_id.ot_id != hora.ot_id:
                raise ValidationError("El puesto de las horas no pertenece a la OT.")
            if (hora.servicio_id and hora.puesto_line_id
                    and hora.servicio_id.puesto_line_id != hora.puesto_line_id):
                raise ValidationError(
                    "El servicio «%s» no pertenece al puesto «%s»." % (
                        hora.servicio_id.display_name, hora.puesto_line_id.name))

    @api.constrains('horas')
    def _check_horas(self):
        for hora in self:
            if hora.horas <= 0 or hora.horas > 24:
                raise ValidationError("Las horas deben ser mayores que cero y no más de 24 por línea.")

    # ------------------------------------------------------------------
    def _tllr_fc_verificar(self, ots):
        for ot in ots:
            if ot.state not in ('espera', 'proceso', 'calidad'):
                raise UserError(
                    "La OT %s está en estado «%s»: ya no se pueden modificar las horas." % (
                        ot.name, dict(ot._fields['state'].selection)[ot.state]))
            ot._tllr_fc_verificar_no_detenida("cargar horas")

    def _tllr_fc_verificar_personal(self):
        """Las horas se cargan solo al personal asignado a la línea de puesto del servicio.

        Rige también para el supervisor. En control de calidad las carga el responsable del
        control (el supervisor queda exceptuado allí, como antes).
        """
        for hora in self:
            if hora.ot_id.state == 'calidad':
                if self.env.user.has_group('tllr_fc.group_supervisor'):
                    continue
                if hora.personal_id not in hora.ot_id.personal_horas_ids:
                    raise ValidationError(
                        "En control de calidad solo el responsable del control (%s) puede "
                        "registrar horas en la OT %s." % (
                            ', '.join(hora.ot_id.personal_horas_ids.mapped('name')) or '-',
                            hora.ot_id.name))
                continue
            linea = hora.puesto_line_id
            if not linea:
                # Horas sin puesto (solo con el contexto técnico): rige el personal de la OT.
                if hora.personal_id not in (hora.ot_id.personal_ids | hora.ot_id.responsable_id):
                    raise ValidationError(
                        "%s no está asignado a ningún puesto de la OT %s: solo el personal "
                        "asignado puede registrar horas." % (hora.personal_id.name, hora.ot_id.name))
                continue
            if not linea.personal_ids:
                raise ValidationError(
                    "El puesto «%s» no tiene personal asignado: asignalo en «Puestos y personal» "
                    "antes de cargar horas." % linea.name)
            if hora.personal_id not in linea.personal_ids:
                raise ValidationError(
                    "%s no está asignado al %s (%s). Solo el personal de esa línea puede cargar "
                    "horas en él; asignalo en «Puestos y personal»." % (
                        hora.personal_id.name,
                        "servicio «%s» del puesto «%s»" % (
                            hora.servicio_id.product_id.display_name, linea.name)
                        if hora.servicio_id else "puesto «%s»" % linea.name,
                        ', '.join(linea.personal_ids.mapped('name'))))

    def _tllr_fc_verificar_linea_activa(self):
        for hora in self:
            linea = hora.puesto_line_id
            if linea and linea.state == 'pendiente' and hora.ot_id.state != 'calidad':
                raise UserError(
                    "El puesto «%s» todavía no está activo: las horas se cargan cuando "
                    "el puesto está activo o terminado." % linea.name)

    @api.model_create_multi
    def create(self, vals_list):
        ots = self.env['tllr_fc.ot'].browse([v['ot_id'] for v in vals_list if v.get('ot_id')])
        self._tllr_fc_verificar(ots)
        for vals in vals_list:
            personal = self.env['tllr_fc.personal'].browse(vals.get('personal_id'))
            vals['funcion_id'] = personal.funcion_id.id
            if vals.get('servicio_id') and not vals.get('puesto_line_id'):
                vals['puesto_line_id'] = self.env['tllr_fc.ot.servicio'].browse(
                    vals['servicio_id']).puesto_line_id.id
            if not vals.get('puesto_line_id') and not self.env.context.get('tllr_fc_sin_servicio'):
                raise UserError("Indicá el puesto en el que se trabajaron las horas.")
            if not vals.get('servicio_id') and not self.env.context.get('tllr_fc_sin_servicio'):
                linea = self.env['tllr_fc.ot.puesto'].browse(vals.get('puesto_line_id'))
                if linea.servicio_ids:
                    raise UserError("Indicá el servicio al que corresponden las horas.")
        horas = super().create(vals_list)
        horas._tllr_fc_verificar_personal()
        horas._tllr_fc_verificar_linea_activa()
        return horas

    def write(self, vals):
        if 'funcion_id' in vals or 'ot_id' in vals:
            raise UserError("La función y la OT de una línea de horas no se modifican.")
        self._tllr_fc_verificar(self.ot_id)
        if 'personal_id' in vals:
            vals = dict(vals, funcion_id=self.env['tllr_fc.personal'].browse(
                vals['personal_id']).funcion_id.id)
        resultado = super().write(vals)
        if {'personal_id', 'puesto_line_id', 'servicio_id'} & set(vals):
            self._tllr_fc_verificar_personal()
            self._tllr_fc_verificar_linea_activa()
        return resultado

    @api.ondelete(at_uninstall=False)
    def _unlink_validar(self):
        self._tllr_fc_verificar(self.ot_id)


class TllrFcOtHerramientaDanada(models.Model):
    """Herramienta dañada durante la OT. Solo registro: no mueve inventario."""
    _name = 'tllr_fc.ot.herramienta_danada'
    _description = "Herramienta dañada en la orden de trabajo"
    _order = 'id desc'

    ot_id = fields.Many2one(
        'tllr_fc.ot', string="OT", required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(
        'res.company', string="Compañía", related='ot_id.company_id',
        store=True, index=True)
    product_id = fields.Many2one(
        'product.product', string="Herramienta", required=True, ondelete='restrict',
        domain="[('tllr_fc_uso_taller', '=', 'herramienta')]")
    cantidad = fields.Float(string="Cantidad", default=1.0)
    motivo = fields.Text(string="Motivo", required=True)
    personal_id = fields.Many2one(
        'tllr_fc.personal', string="Personal", ondelete='restrict')

    @api.constrains('cantidad', 'product_id')
    def _check_valores(self):
        for linea in self:
            if linea.cantidad <= 0:
                raise ValidationError("La cantidad de herramientas dañadas debe ser mayor que cero.")
            if linea.product_id.tllr_fc_uso_taller != 'herramienta':
                raise ValidationError(
                    "«%s» no es una herramienta (revisá el uso en taller de su ficha)."
                    % linea.product_id.display_name)

    def _tllr_fc_verificar(self, ots):
        for ot in ots:
            if ot.state in ('entregado', 'cancelada'):
                raise UserError("La OT %s ya está cerrada." % ot.name)

    @api.model_create_multi
    def create(self, vals_list):
        self._tllr_fc_verificar(
            self.env['tllr_fc.ot'].browse([v['ot_id'] for v in vals_list if v.get('ot_id')]))
        lineas = super().create(vals_list)
        for linea in lineas:
            linea.ot_id.message_post(body="Herramienta dañada: %s × %s. %s" % (
                linea.product_id.display_name, linea.cantidad, linea.motivo or ''))
        return lineas

    def write(self, vals):
        self._tllr_fc_verificar(self.ot_id)
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_validar(self):
        self._tllr_fc_verificar(self.ot_id)
