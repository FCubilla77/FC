# -*- coding: utf-8 -*-
"""Mixins que aplican el control de licencia a los modelos del Taller (ver
tllr_fc_licencia.py). Separados en dos para no bloquear la edición de registros
antiguos (solo la creación) salvo en los documentos que representan trabajo en
curso, que además bloquean la edición.
"""
from odoo import api, models

from .tllr_fc_licencia import tllr_fc_licencia_exenta, tllr_fc_licencia_verificar


class TllrFcMixinLicencia(models.AbstractModel):
    """Bloquea la creación de registros sin una licencia válida para la base."""
    _name = 'tllr_fc.mixin.licencia'
    _description = "Taller: control de licencia (creación)"

    @api.model_create_multi
    def create(self, vals_list):
        if not tllr_fc_licencia_exenta(self.env):
            Company = self.env['res.company']
            for vals in vals_list:
                company = (Company.browse(vals['company_id'])
                           if vals.get('company_id') else self.env.company)
                tllr_fc_licencia_verificar(self.env, company)
        return super().create(vals_list)


class TllrFcMixinLicenciaEdicion(models.AbstractModel):
    """Además bloquea la edición: para los documentos de trabajo en curso (OT,
    recepción, entrega, control de calidad, turno), de modo que una licencia
    vencida también detiene lo que ya estaba abierto, no solo lo nuevo."""
    _name = 'tllr_fc.mixin.licencia.edicion'
    _description = "Taller: control de licencia (edición)"

    def write(self, vals):
        if not tllr_fc_licencia_exenta(self.env):
            for record in self:
                tllr_fc_licencia_verificar(self.env, record.company_id)
        return super().write(vals)
