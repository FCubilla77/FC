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
        tiene por qué tener una Empresa asociada."""
        for this in self:
            if this.is_company or this.l10n_py_creado_desde_usuario_empleado:
                continue
            if not this.parent_id or not this.parent_id.is_company:
                raise exceptions.ValidationError(
                    "Los contactos individuales solo pueden crearse dentro de un "
                    "contacto de tipo Empresa. Seleccione una Empresa relacionada."
                )

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('l10n_py_partner_from_user_or_employee'):
            for vals in vals_list:
                vals.setdefault('l10n_py_creado_desde_usuario_empleado', True)
        result = super(ResPartner, self).create(vals_list)
        result.val_ruc()
        return result

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