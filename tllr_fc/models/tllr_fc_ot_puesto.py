# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.tools import float_compare
from odoo.exceptions import UserError, ValidationError


class TllrFcOtPuesto(models.Model):
    """Puesto por el que pasa la OT (líneas ordenadas por el supervisor)."""
    _name = 'tllr_fc.ot.puesto'
    _description = "Puesto de la orden de trabajo"
    _order = 'sequence, id'
    _check_company_auto = True

    ot_id = fields.Many2one(
        'tllr_fc.ot', string="OT", required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(
        'res.company', string="Compañía", related='ot_id.company_id',
        store=True, index=True)
    sequence = fields.Integer(string="Orden", default=10)
    puesto_id = fields.Many2one(
        'tllr_fc.puesto', string="Puesto", required=True, ondelete='restrict',
        check_company=True)
    name = fields.Char(string="Nombre", related='puesto_id.name')
    state = fields.Selection([
        ('pendiente', "Pendiente"),
        ('activo', "Activo"),
        ('terminado', "Terminado"),
    ], string="Estado", required=True, default='pendiente', copy=False, index=True)
    personal_ids = fields.Many2many(
        'tllr_fc.personal', 'tllr_fc_ot_puesto_personal_rel', 'puesto_line_id', 'personal_id',
        string="Personal", check_company=True)
    servicio_ids = fields.One2many(
        'tllr_fc.ot.servicio', 'puesto_line_id', string="Servicios")
    servicio_id = fields.Many2one(
        'tllr_fc.ot.servicio', string="Servicio", compute='_compute_servicio_id',
        inverse='_inverse_servicio_id',
        domain="[('ot_id', '=', ot_id), ('estado', '!=', 'no_realizado')]",
        help="Servicio de la OT que se realiza en esta línea. Sin servicio, la línea es un "
             "puesto de paso (por ejemplo, un control general).")
    horas_cargadas = fields.Boolean(string="Con horas", compute='_compute_horas_cargadas')
    fecha_inicio = fields.Datetime(string="Inicio", readonly=True, copy=False)
    fecha_fin = fields.Datetime(string="Fin", readonly=True, copy=False)
    almacen_id = fields.Many2one(
        'stock.warehouse', related='puesto_id.almacen_id', string="Almacén")

    @api.depends('servicio_ids')
    def _compute_servicio_id(self):
        for linea in self:
            linea.servicio_id = linea.servicio_ids.sorted('id')[:1]

    def _compute_horas_cargadas(self):
        horas = self.env['tllr_fc.ot.hora'].sudo()._read_group(
            [('puesto_line_id', 'in', self.ids)], ['puesto_line_id'], ['__count'])
        con_horas = {linea.id for linea, _n in horas}
        for linea in self:
            linea.horas_cargadas = linea.id in con_horas

    def _inverse_servicio_id(self):
        """Elegir el servicio de la línea lo asocia a ella (y lo quita de otra, si procede)."""
        for linea in self:
            nuevo = linea.servicio_id
            actual = linea.servicio_ids.sorted('id')[:1]
            if nuevo == actual:
                continue
            if linea.state != 'pendiente' or linea.horas_cargadas:
                raise UserError(
                    "No se puede cambiar el servicio del puesto «%s»: ya está en curso o tiene "
                    "horas cargadas." % linea.name)
            ctx = self.env.context
            if nuevo:
                if nuevo.ot_id != linea.ot_id:
                    raise ValidationError("El servicio no pertenece a la OT de la línea.")
                origen = nuevo.puesto_line_id
                if origen and origen != linea:
                    linea._tllr_fc_verificar_traslado_servicio(nuevo, origen)
                if actual:
                    actual.with_context(tllr_fc_permitir_write=True).write({'puesto_line_id': False})
                nuevo.with_context(tllr_fc_permitir_write=True).write({'puesto_line_id': linea.id})
            elif actual:
                actual.with_context(tllr_fc_permitir_write=True).write({'puesto_line_id': False})

    def _tllr_fc_verificar_traslado_servicio(self, servicio, origen):
        """El servicio ya está en otra línea: solo pasa si esa línea tiene otros servicios."""
        self.ensure_one()
        if origen.state != 'pendiente' or servicio.estado != 'pendiente':
            raise UserError(
                "El servicio «%s» ya está asignado al puesto «%s» y no se puede mover porque "
                "esa línea ya está en curso." % (servicio.product_id.display_name, origen.name))
        horas = self.env['tllr_fc.ot.hora'].sudo().search_count(
            [('servicio_id', '=', servicio.id)])
        if horas:
            raise UserError(
                "El servicio «%s» tiene horas cargadas: no se puede asignar a otro puesto."
                % servicio.product_id.display_name)
        if not (origen.servicio_ids - servicio):
            raise UserError(
                "El servicio «%s» ya está asignado al puesto «%s» de esta OT: se estaría "
                "duplicando. Quitalo de esa línea antes de asignarlo a otra."
                % (servicio.product_id.display_name, origen.name))

    @api.constrains('puesto_id', 'personal_ids', 'ot_id')
    def _check_duplicado(self):
        """No se repite la misma línea: mismo puesto y servicio (o, sin servicio, mismo personal)."""
        for ot in self.ot_id:
            vistos = {}
            for linea in ot.puesto_line_ids:
                servicios = tuple(sorted(linea.servicio_ids.ids))
                clave = (linea.puesto_id.id, servicios,
                         () if servicios else tuple(sorted(linea.personal_ids.ids)))
                previa = vistos.get(clave)
                if previa:
                    raise ValidationError(
                        "La línea «%s»%s se está duplicando en la OT %s (mismo puesto%s)." % (
                            linea.name,
                            " con el servicio «%s»" % linea.servicio_id.product_id.display_name
                            if linea.servicio_id else "",
                            ot.name,
                            ", servicio" if servicios else " y personal"))
                vistos[clave] = linea

    @api.constrains('state', 'ot_id')
    def _check_un_solo_activo(self):
        for ot in self.ot_id:
            activos = ot.puesto_line_ids.filtered(lambda l: l.state == 'activo')
            if len(activos) > 1:
                raise ValidationError(
                    "La OT %s no puede tener más de un puesto activo a la vez." % ot.name)

    # ------------------------------------------------------------------
    def _tllr_fc_validar_cierre(self):
        """Controles para terminar el puesto (sin excepción).

        - Los servicios del puesto están Terminados (o No realizados) y tienen informe.
        - Cada servicio terminado tiene horas cargadas.
        - Las funciones de quien cargó horas en el puesto tienen costo por hora vigente.
        - Repuestos, insumos y accesorios del puesto: Utilizado + No utilizado = Reservado.
        """
        self.ensure_one()
        errores = []
        terminados = self.servicio_ids.filtered(lambda s: s.estado == 'terminado')
        sin_informe = terminados.filtered(lambda s: not (s.informe or '').strip())
        if sin_informe:
            errores.append("Falta el informe del servicio: %s." % ', '.join(
                sin_informe.mapped('product_id.name')))
        horas = self.ot_id.hora_ids.sudo()
        sin_horas = terminados.filtered(
            lambda s: s._tllr_fc_requiere_horas()
            and not horas.filtered(lambda h: h.servicio_id == s))
        if sin_horas:
            errores.append(
                "Faltan las horas trabajadas de: %s (pestaña «Resultado», horas trabajadas; "
                "las carga el personal asignado a ese servicio)." % ', '.join(
                    sin_horas.mapped('product_id.name')))
        horas_puesto = horas.filtered(lambda h: h.puesto_line_id == self)
        for funcion in horas_puesto.funcion_id:
            fechas = horas_puesto.filtered(lambda h: h.funcion_id == funcion).mapped('fecha')
            if any(not funcion._tiene_costo_a_fecha(fecha) for fecha in fechas):
                errores.append(
                    "La función «%s» no tiene costo por hora vigente asignado." % funcion.name)
        sin_funcion = horas_puesto.filtered(lambda h: not h.funcion_id).personal_id
        if sin_funcion:
            errores.append("Sin función asignada: %s." % ', '.join(sin_funcion.mapped('name')))
        productos = self.ot_id.producto_ids.sudo().filtered(
            lambda p: p.puesto_line_id == self and not p.provisto_cliente
            and p._tllr_fc_mueve_stock())
        for producto in productos:
            suma = producto.cantidad_utilizada + producto.cantidad_no_utilizada
            if float_compare(suma, producto.cantidad_reservada,
                             precision_rounding=producto.uom_id.rounding or 0.001) != 0:
                if producto.state_aprobacion == 'pendiente':
                    errores.append(
                        "«%s» está pendiente de aprobación del cliente: usá «Registrar "
                        "aprobación» (o «Autorizar sin aprobación») y luego registrá lo "
                        "utilizado o no utilizado." % producto.product_id.display_name)
                    continue
                errores.append(
                    "«%s»: Utilizado (%s) + No utilizado (%s) debe ser igual a lo reservado (%s)."
                    % (producto.product_id.display_name, producto.cantidad_utilizada,
                       producto.cantidad_no_utilizada, producto.cantidad_reservada))
        if errores:
            raise UserError(
                "No se puede terminar el puesto «%s»:\n- %s" % (self.name, '\n- '.join(errores)))

    def _tllr_fc_usuario_puede_operar(self):
        """Supervisor o personal asignado al puesto (por su usuario)."""
        self.ensure_one()
        if self.env.user.has_group('tllr_fc.group_supervisor'):
            return True
        return self.env.user in self.personal_ids.user_id

    def _tllr_fc_verificar_ot_editable(self, ots):
        for ot in ots:
            if ot.state not in ('espera', 'proceso'):
                raise UserError(
                    "La OT %s ya no admite cambios en sus puestos." % ot.name)

    @api.model_create_multi
    def create(self, vals_list):
        ots = self.env['tllr_fc.ot'].browse([v['ot_id'] for v in vals_list if v.get('ot_id')])
        self._tllr_fc_verificar_ot_editable(ots)
        elegido = []
        for vals in vals_list:
            vals['state'] = 'pendiente'
            elegido.append(bool(vals.get('servicio_id')))
        lineas = super().create(vals_list)
        # Los servicios de la OT sin puesto que este puesto realiza se le asocian
        # (salvo en la línea a la que se eligió expresamente un servicio).
        for linea, con_servicio in zip(lineas, elegido):
            if con_servicio:
                continue
            sin_puesto = linea.ot_id.servicio_ids.filtered(
                lambda s: not s.puesto_line_id
                and s.product_id.product_tmpl_id in linea.puesto_id.servicio_ids)
            if sin_puesto:
                sin_puesto.write({'puesto_line_id': linea.id})
        for ot in lineas.ot_id:
            ot._tllr_fc_asignar_puesto_productos()
        lineas._check_duplicado()
        return lineas

    def write(self, vals):
        if not self.env.context.get('tllr_fc_permitir_write'):
            if 'state' in vals or 'fecha_inicio' in vals or 'fecha_fin' in vals:
                raise UserError("El estado del puesto cambia con los botones de la OT.")
            self._tllr_fc_verificar_ot_editable(self.ot_id)
            if 'puesto_id' in vals and any(l.state != 'pendiente' for l in self):
                raise UserError("Solo se puede cambiar el puesto mientras está pendiente.")
            if 'puesto_id' in vals and any(l.horas_cargadas for l in self):
                raise UserError("No se puede cambiar el puesto de una línea con horas cargadas.")
        antes = {l.id: l.personal_ids for l in self} if 'personal_ids' in vals else {}
        resultado = super().write(vals)
        if antes:
            for linea in self:
                quitados = antes[linea.id] - linea.personal_ids
                con_horas = self.env['tllr_fc.ot.hora'].sudo().search([
                    ('puesto_line_id', '=', linea.id),
                    ('personal_id', 'in', quitados.ids)]).personal_id
                if con_horas:
                    raise UserError(
                        "No se puede quitar a %s del puesto «%s»: tiene horas cargadas en él." % (
                            ', '.join(con_horas.mapped('name')), linea.name))
        return resultado

    @api.ondelete(at_uninstall=False)
    def _unlink_validar(self):
        self._tllr_fc_verificar_ot_editable(self.ot_id)
        for linea in self:
            if linea.state != 'pendiente':
                raise UserError(
                    "Solo se puede quitar un puesto que todavía está pendiente (%s)." % linea.name)
            if linea.horas_cargadas:
                raise UserError(
                    "No se puede quitar el puesto «%s»: tiene horas cargadas." % linea.name)
            if linea.servicio_ids:
                linea.ot_id.message_post(body=(
                    "Se quitó el puesto «%s»: los servicios %s quedan sin puesto asignado." % (
                        linea.name, ', '.join(linea.servicio_ids.mapped('product_id.name')))))
