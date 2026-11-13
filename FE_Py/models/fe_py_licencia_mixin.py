# -*- coding: utf-8 -*-
from odoo import api, models

from .fe_py_licencia import fe_py_licencia_verificar


class FePyMixinLicencia(models.AbstractModel):
    """Bloquea la CREACIÓN si la compañía no tiene una licencia válida.

    Se agrega por `_inherit` solo a los modelos propios de FE_Py que lo requieran:
    el catálogo base (y por lo tanto los 14 catálogos DNIT que heredan de él), las
    Configuraciones Generales FEPy y los Eventos SIFEN. Nunca se aplica al Log de
    Operaciones, a las cuotas de un documento, a los informes ni a modelos nativos
    de Odoo.

    El Documento Electrónico NO lleva este mixin a propósito: su creación ocurre
    dentro de `account.move._post()`, donde el control se hace antes, sobre la
    confirmación del comprobante (ver `account_move.py`), para que el bloqueo deje
    la factura en Borrador en vez de dejarla emitida sin poder llegar a SIFEN."""
    _name = 'fe_py.mixin.licencia'
    _description = "Control de licencia FE_Py: creación"

    @api.model_create_multi
    def create(self, vals_list):
        Company = self.env['res.company']
        for vals in vals_list:
            fe_py_licencia_verificar(
                self.env,
                Company.browse(vals['company_id']) if vals.get('company_id') else None)
        return super().create(vals_list)


class FePyMixinLicenciaEdicion(models.AbstractModel):
    """Bloquea la EDICIÓN si la compañía no tiene una licencia válida.

    Solo para las Configuraciones Generales FEPy y los Eventos SIFEN. No se aplica a
    los catálogos: una licencia vencida no debe impedir corregir un dato ya cargado.
    Tampoco al Documento Electrónico, que tiene campos `related store=True` sobre la
    factura (compañía, cliente, diario, tipo fiscal): un bloqueo general de `write`
    ahí se dispararía al editar esos datos en la factura, por el recálculo del
    related almacenado, sin aportar protección."""
    _name = 'fe_py.mixin.licencia.edicion'
    _description = "Control de licencia FE_Py: edición"

    def write(self, vals):
        if 'company_id' in self._fields:
            for company in self.mapped('company_id') or self.env.company:
                fe_py_licencia_verificar(self.env, company)
        else:
            fe_py_licencia_verificar(self.env, None)
        return super().write(vals)
