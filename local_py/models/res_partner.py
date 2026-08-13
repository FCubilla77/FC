# -*- coding: utf-8 -*-
from odoo import models, fields, exceptions, api
import re


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # El campo city_id ya existe de forma nativa (base_address_extended), pero
    # sin dominio: se agrega acá para que solo ofrezca ciudades del Departamento
    # seleccionado.
    city_id = fields.Many2one(domain="[('state_id', '=', state_id)]")

    omitir_validacion = fields.Boolean(string='Omitir control de RUT', default=False)
    vat = fields.Char(string="RUT", index=True)
    l10n_py_tipo_identificacion_fiscal_id = fields.Many2one(
        'local_py.tipo_identificacion_fiscal',
        string='Tipo de Identificación Fiscal',
        help='Clasificación fiscal del contacto según la Tabla 3 de la '
             'Especificación Técnica de Marangatu (DNIT, RG 90/2021). '
             'Solo aplica a contactos de tipo Empresa.',
    )
    l10n_py_creado_desde_usuario_empleado = fields.Boolean(
        string='Creado desde Usuario',
        default=False,
        copy=False,
        help='Campo técnico de uso interno (no se muestra en la vista). Se '
             'marca automáticamente en 1/Verdadero cuando el contacto se '
             'origina al crear un Usuario; en ese caso no corresponde '
             'exigir Empresa relacionada. Se deja en 0/Falso para contactos '
             'creados normalmente desde Contactos.',
    )
    l10n_py_retencion_iva = fields.Boolean(
        string='Retención IVA', default=lambda self: self._default_l10n_py_retencion('l10n_py_retencion_iva'),
    )
    l10n_py_retencion_iva_porcentaje = fields.Float(
        string='Porcentaje Retención IVA', digits=(5, 2),
        default=lambda self: self._default_l10n_py_retencion('l10n_py_retencion_iva_porcentaje'),
    )
    l10n_py_retencion_renta = fields.Boolean(
        string='Retención Renta (Exterior)', default=lambda self: self._default_l10n_py_retencion('l10n_py_retencion_renta'),
    )
    l10n_py_concepto_iva_id = fields.Many2one(
        'local_py.concepto_iva', string='Concepto IVA',
        default=lambda self: self._default_l10n_py_retencion('l10n_py_concepto_iva_id'),
        help='Determina cómo se calcula la Retención IVA para este Proveedor: '
             '"IVA.1" (el predeterminado, proveedores locales) sigue el régimen habitual '
             '(acumulado mensual, Mínimo Imponible, Porcentaje configurado). Cualquier '
             'otro Concepto (por ejemplo, "IVA.2" — proveedores del exterior) dispara la '
             'Retención con Absorción: siempre se retiene el 100% de un IVA calculado '
             'temporalmente al 10%, sin acumulado ni mínimo, como un Gasto aparte para '
             'la Compañía (no se le descuenta nada al Proveedor).',
    )
    l10n_py_se_absorbe_iva = fields.Boolean(
        string='Se Absorbe IVA',
        help='Solo aplica a Proveedores del exterior (Concepto IVA = IVA.2). Si está '
             'tildado, la Retención IVA queda como un Gasto aparte para la Compañía, '
             'sin descontarle nada al Proveedor. Si no está tildado, se descuenta '
             'directo del pago (como una Retención local más).',
    )
    l10n_py_se_absorbe_renta = fields.Boolean(
        string='Se Absorbe Renta',
        help='Solo aplica a Proveedores del exterior con Concepto Renta No Residente '
             'configurado. Si está tildado, la Retención Renta queda como un Gasto '
             'aparte para la Compañía, sin descontarle nada al Proveedor. Si no está '
             'tildado, se descuenta directo del pago (como una Retención local más).',
    )
    l10n_py_concepto_renta_no_residente_ids = fields.Many2many(
        'local_py.concepto_renta_no_residente', string='Conceptos Renta No Residente',
        help='Los distintos tipos de operación por los que este Proveedor del exterior '
             'puede facturar (por ejemplo, servicios profesionales y también servicios '
             'digitales) — cada Factura puede elegir cuál de estos le corresponde.',
    )
    l10n_py_concepto_renta_no_residente_predeterminado_id = fields.Many2one(
        'local_py.concepto_renta_no_residente', string='Concepto Renta No Residente Predeterminado',
        help='Se copia solo en cada Factura nueva de este Proveedor — queda editable '
             'por Factura, para cuando una factura puntual corresponda a otro Concepto '
             'de los configurados arriba.',
    )
    l10n_py_localizacion_validada = fields.Boolean(
        string='Localización Validada', default=False, copy=False,
        help='Confirma que un humano revisó (y completó o corrigió si hacía falta) los '
             'datos de Retención de este Proveedor — nace destildada en cualquier '
             'Contacto nuevo, incluso si los campos de Retención se autocompletaron '
             'solos con los valores predeterminados de la Compañía. Mientras no esté '
             'tildada, Orden de Pago bloquea a este Proveedor si tiene alguna Retención '
             'activa (evita pagar con datos fiscales sin revisar).',
    )

    @api.onchange('country_id')
    def _onchange_country_id_retencion(self):
        """Al elegir el País de un Contacto Empresa, precarga los datos
        de Retención según sea Local o del Exterior — con los valores
        predeterminados de la Compañía, y la bandera "Localización
        Validada" siempre destildada: alguien tiene que revisar esto a
        mano antes de poder usar a este Proveedor en una Orden de Pago
        con Retención activa."""
        if not self.is_company or not self.country_id:
            return
        company_country = self.env.company.country_id
        config = self.env['local_py.configuracion_localizacion'].search(
            [('company_id', '=', self.env.company.id)], limit=1,
        )
        if self.country_id == company_country:
            self.l10n_py_retencion_renta = False
            self.l10n_py_se_absorbe_iva = False
            self.l10n_py_se_absorbe_renta = False
            if config:
                self.l10n_py_retencion_iva = config.l10n_py_retencion_iva
                self.l10n_py_retencion_iva_porcentaje = config.l10n_py_retencion_iva_porcentaje
                self.l10n_py_concepto_iva_id = config.l10n_py_concepto_iva_id
        else:
            self.l10n_py_retencion_iva = True
            self.l10n_py_retencion_renta = True
            concepto_iva_2 = self.env.ref('local_py.concepto_iva_2', raise_if_not_found=False)
            if concepto_iva_2:
                self.l10n_py_concepto_iva_id = concepto_iva_2
            if config and config.l10n_py_retencion_iva_porcentaje:
                self.l10n_py_retencion_iva_porcentaje = config.l10n_py_retencion_iva_porcentaje
        self.l10n_py_localizacion_validada = False

    @api.onchange('l10n_py_tipo_identificacion_fiscal_id')
    def _onchange_l10n_py_tipo_identificacion_fiscal_id(self):
        ruc = self.env.ref('local_py.tipo_identificacion_ruc', raise_if_not_found=False)
        for partner in self:
            tipo = partner.l10n_py_tipo_identificacion_fiscal_id
            if tipo:
                partner.omitir_validacion = not (ruc and tipo.id == ruc.id)

    def clear_vat(self, vat):
        allowed_characters = '1234567890-'
        if vat:
            for vat_character in vat:
                if vat_character not in allowed_characters:
                    vat = vat.replace(vat_character, '')
        return vat

    @api.depends('vat', 'omitir_validacion', 'is_company')
    def val_ruc(self):
        for this in self:
            # El campo RUT y sus validaciones (formato, dígito verificador,
            # "Omitir control RUT") solo aplican a contactos que SÍ son una
            # empresa. Los contactos individuales no llevan RUT propio (ver
            # también _check_individual_requiere_empresa): el campo queda
            # oculto en la vista y no corresponde validar nada aquí.
            if not this.is_company:
                continue
            ruc = this.clear_vat(this.vat)
            if not this.omitir_validacion:
                if ruc:
                    pattern = "^[0-9]+-[0-9]$"
                    if re.match(pattern, ruc):
                        ruc_das = str(ruc).split("-")
                        ruc_dig = ruc_das[1]
                        ruc_proper_dig = str(this.digito_verificador(ruc))
                        if ruc_proper_dig != ruc_dig:
                            raise exceptions.ValidationError("El digito verificador debería ser :" + ruc_proper_dig)
                    else:
                        raise exceptions.ValidationError("Error de formato de RUT...!!! (Ejemplo: 123456789-0)")
                    if this.vat != ruc:
                        this.vat = ruc

    def digito_verificador(self, ruc):
        ruc_asd = str(ruc).split("-")
        ruc_ci = ruc_asd[0]
        ruc_str = str(ruc_ci)[::-1]
        v_total = 0
        basemax = 11
        k = 2
        for i in range(0, len(ruc_str)):
            if k > basemax:
                k = 2
            v_total += int(ruc_str[i]) * k
            k += 1
            resto = v_total % basemax
        if resto > 1:
            return basemax - resto
        else:
            return 0

    @api.constrains('vat', 'is_company')
    def _check_vat_duplicado(self):
        """No permite dos contactos con el mismo RUT. Esta validación aplica
        únicamente a contactos que corresponden a una empresa (el campo RUT
        solo existe/es visible para ellos)."""
        for this in self:
            if not this.is_company or not this.vat:
                continue
            duplicado = self.env['res.partner'].search([
                ('id', '!=', this.id),
                ('is_company', '=', True),
                ('vat', '=', this.vat),
            ], limit=1)
            if duplicado:
                raise exceptions.ValidationError(
                    "Ya existe otro contacto (empresa) con el mismo RUT (%s): %s"
                    % (this.vat, duplicado.display_name)
                )

    @api.constrains('is_company', 'parent_id')
    def _check_individual_requiere_empresa(self):
        """Los contactos individuales (is_company=False) solo pueden
        crearse/existir asociados a un contacto de tipo empresa: deben tener
        'Empresa relacionada' (parent_id) establecida, y esa empresa
        relacionada debe ser, a su vez, un contacto de tipo empresa.

        Excepción: no aplica a contactos originados al crear un Usuario
        (l10n_py_creado_desde_usuario_empleado = True), ya que ese flujo no
        tiene por qué tener una Empresa asociada.

        Esta validación se revisa siempre antes que cualquier otra del
        Contacto (queda definida primero en el archivo, y Odoo respeta
        ese orden) — así, si alguna vez un registro llegara a activar
        más de una validación a la vez, la que se muestra es siempre la
        que corresponde a un contacto Individual, nunca la de Empresa."""
        for this in self:
            if this.is_company:
                continue
            if this.l10n_py_creado_desde_usuario_empleado:
                continue
            if not this.parent_id:
                raise exceptions.ValidationError(
                    "Los contactos individuales solo pueden crearse dentro de un "
                    "contacto de tipo Empresa. Seleccione una Empresa relacionada."
                )
            if not this.parent_id.is_company:
                raise exceptions.ValidationError(
                    "Los contactos individuales solo pueden crearse dentro de un "
                    "contacto de tipo Empresa. Seleccione una Empresa relacionada."
                )

    def _default_l10n_py_retencion(self, campo):
        config = self.env['local_py.configuracion_localizacion'].search(
            [('company_id', '=', self.env.company.id)], limit=1,
        )
        return config[campo] if config else False

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('l10n_py_partner_from_user_or_employee'):
            for vals in vals_list:
                vals.setdefault('l10n_py_creado_desde_usuario_empleado', True)
        result = super(ResPartner, self).create(vals_list)
        result.val_ruc()
        return result

    @api.constrains(
        'is_company', 'name', 'street', 'country_id', 'state_id', 'city_id',
        'l10n_py_tipo_identificacion_fiscal_id', 'property_payment_term_id',
        'property_supplier_payment_term_id', 'vat',
    )
    def _check_datos_obligatorios_empresa(self):
        """Un contacto de tipo Empresa necesita, como mínimo, estos datos
        completos — de lo contrario, después faltan justo en el momento
        de facturar, pagar, o declarar ante la DNIT.

        Guarda explícita y separada (no "if not is_company: continue"):
        esta validación NUNCA debe mirar a un contacto Individual — se
        escribe así, en 2 pasos, para que quede sin ninguna ambigüedad
        de lectura."""
        for partner in self:
            es_empresa = bool(partner.is_company)
            if not es_empresa:
                continue
            faltantes = []
            if not partner.name:
                faltantes.append('Nombre')
            if not partner.street:
                faltantes.append('Calle')
            if not partner.country_id:
                faltantes.append('País')
            if not partner.state_id:
                faltantes.append('Departamento')
            if not partner.city_id:
                faltantes.append('Ciudad')
            if not partner.l10n_py_tipo_identificacion_fiscal_id:
                faltantes.append('Tipo de Identificación Fiscal')
            if not partner.property_payment_term_id:
                faltantes.append('Términos de Pago Venta')
            if not partner.property_supplier_payment_term_id:
                faltantes.append('Términos de Pago Compra')
            if not partner.vat:
                faltantes.append('RUT')
            if faltantes:
                raise exceptions.ValidationError(
                    'Para guardar un Contacto de tipo Empresa, hace falta completar: %s.'
                    % ', '.join(faltantes)
                )

    @api.constrains('is_company', 'l10n_py_tipo_identificacion_fiscal_id', 'country_id', 'l10n_py_concepto_iva_id')
    def _check_consistencia_proveedor_exterior(self):
        """Un Proveedor del Exterior se define por 3 datos juntos: Tipo de
        Identificación Fiscal = "Identificación Tributaria", País
        distinto de Paraguay, y Concepto IVA = "IVA.2". Si alguno de los
        3 indica "exterior", los otros 2 tienen que coincidir también —
        no alcanza con uno solo suelto (por ejemplo, cambiar el País sin
        actualizar también el Concepto IVA)."""
        tipo_tributaria = self.env.ref('local_py.tipo_identificacion_tributaria', raise_if_not_found=False)
        paraguay = self.env.ref('base.py', raise_if_not_found=False)
        concepto_iva_2 = self.env.ref('local_py.concepto_iva_2', raise_if_not_found=False)
        if not (tipo_tributaria and paraguay and concepto_iva_2):
            return
        for partner in self:
            if not partner.is_company:
                continue
            if not (
                partner.l10n_py_tipo_identificacion_fiscal_id
                or partner.country_id
                or partner.l10n_py_concepto_iva_id
            ):
                continue
            es_tipo_exterior = partner.l10n_py_tipo_identificacion_fiscal_id == tipo_tributaria
            es_pais_exterior = bool(partner.country_id) and partner.country_id != paraguay
            es_concepto_exterior = partner.l10n_py_concepto_iva_id == concepto_iva_2
            señales = (es_tipo_exterior, es_pais_exterior, es_concepto_exterior)
            if any(señales) and not all(señales):
                raise exceptions.ValidationError(
                    'Los datos de este Proveedor no son consistentes para determinar si es '
                    'del Exterior o local — un Proveedor del Exterior debe cumplir los 3 '
                    'datos juntos: Tipo de Identificación Fiscal = "Identificación '
                    'Tributaria", País distinto de Paraguay, y Concepto IVA = "IVA.2 — Pago '
                    'Único y Definitivo por acreditamiento...". Revise estos 3 campos en la '
                    'ficha del Proveedor.'
                )

    @api.constrains(
        'is_company', 'country_id', 'l10n_py_retencion_iva', 'l10n_py_retencion_iva_porcentaje',
        'l10n_py_concepto_iva_id', 'l10n_py_se_absorbe_iva', 'l10n_py_retencion_renta',
        'l10n_py_concepto_renta_no_residente_predeterminado_id', 'supplier_rank',
    )
    def _check_retenciones_local_o_exterior(self):
        """Reglas de Retención según el Proveedor sea local o del
        exterior — se define comparando su País contra el de la
        Compañía (dato más simple y directo que el cruce de 3 señales
        de _check_consistencia_proveedor_exterior, que sigue aplicando
        aparte para la Absorción de IVA). Aplica solo a Proveedores
        (supplier_rank > 0) — un Cliente puro no tiene por qué cumplir
        ninguna de estas reglas, aunque sea de tipo Empresa.

        - Local: no puede tener "Retención Renta" activada. Si tiene
          "Retención IVA" activada, necesita Porcentaje y Concepto IVA
          completos, y no puede tener "Se Absorbe IVA" tildado (la
          Absorción es exclusiva de proveedores del exterior).
        - Exterior: tiene que tener "Retención IVA" y "Retención
          Renta" activadas, las dos. En Retención IVA necesita
          Porcentaje y Concepto IVA puntualmente en "IVA.2" (no
          cualquier Concepto — tiene que coincidir con el que dispara
          la Absorción/cálculo del exterior); en Retención Renta
          necesita el Concepto Renta No Residente Predeterminado (trae
          el porcentaje incluido). "Se Absorbe IVA"/"Se Absorbe Renta"
          quedan libres — pueden estar tildadas las dos, una sola, o
          ninguna."""
        concepto_iva_2 = self.env.ref('local_py.concepto_iva_2', raise_if_not_found=False)
        company_country = self.env.company.country_id
        for partner in self:
            if not partner.is_company or not partner.country_id or partner.supplier_rank <= 0:
                continue
            es_local = partner.country_id == company_country
            faltantes = []
            if es_local:
                if partner.l10n_py_retencion_renta:
                    faltantes.append('un Proveedor local no puede tener "Retención Renta (Exterior)" activada')
                if partner.l10n_py_retencion_iva:
                    if not partner.l10n_py_retencion_iva_porcentaje:
                        faltantes.append('Porcentaje Retención IVA')
                    if not partner.l10n_py_concepto_iva_id:
                        faltantes.append('Concepto IVA')
                    if partner.l10n_py_se_absorbe_iva:
                        faltantes.append('un Proveedor local no puede tener "Se Absorbe IVA" tildado')
            else:
                if not partner.l10n_py_retencion_iva:
                    faltantes.append('un Proveedor del exterior debe tener "Retención IVA" activada')
                if not partner.l10n_py_retencion_renta:
                    faltantes.append('un Proveedor del exterior debe tener "Retención Renta (Exterior)" activada')
                if partner.l10n_py_retencion_iva:
                    if not partner.l10n_py_retencion_iva_porcentaje:
                        faltantes.append('Porcentaje Retención IVA')
                    if not concepto_iva_2 or partner.l10n_py_concepto_iva_id != concepto_iva_2:
                        faltantes.append('Concepto IVA tiene que ser puntualmente "IVA.2"')
                if partner.l10n_py_retencion_renta:
                    if not partner.l10n_py_concepto_renta_no_residente_predeterminado_id:
                        faltantes.append('Concepto Renta No Residente Predeterminado')
            if faltantes:
                raise exceptions.ValidationError(
                    'Revisar la configuración de Retenciones de este Proveedor (%s): %s.'
                    % ('local' if es_local else 'del exterior', '; '.join(faltantes))
                )

    @api.constrains(
        'l10n_py_concepto_renta_no_residente_predeterminado_id', 'l10n_py_concepto_renta_no_residente_ids',
    )
    def _check_concepto_renta_predeterminado(self):
        for partner in self:
            predeterminado = partner.l10n_py_concepto_renta_no_residente_predeterminado_id
            if predeterminado and predeterminado not in partner.l10n_py_concepto_renta_no_residente_ids:
                raise exceptions.ValidationError(
                    'El Concepto Renta No Residente Predeterminado tiene que ser uno de los '
                    'que están cargados en "Conceptos Renta No Residente", en la misma ficha '
                    'del Proveedor.'
                )

    def write(self, vals):
        result = super(ResPartner, self).write(vals)
        if vals.get('vat'):
            self.val_ruc()
        return result

    # @api.model
    # def name_search(self, name, args=None, operator='ilike', limit=100):
    #     result = super(ResPartner, self).name_search(name, args=args, operator=operator, limit=limit)
    #     if not result:
    #         result = self.env['res.partner'].search([('vat', 'ilike', name)])
    #         return result.name_get()
    #     else:
    #         return result