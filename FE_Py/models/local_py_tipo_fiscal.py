# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Tipos Fiscales que FE_Py trata como electrónicos. Se usa tanto para el
# refuerzo en hooks.py como para la migración de datos existentes.
NOMBRES_TIPO_FISCAL_ELECTRONICO = (
    'Factura Electronica',
    'Nota de Credito Electronica',
    'Nota de Debito Electronica',
)


class LocalPyTipoFiscal(models.Model):
    _inherit = 'local_py.tipo_fiscal'

    fe_py_es_electronico = fields.Boolean(
        string='Es Electrónico',
        help='Marca los Tipos Fiscales que corresponden a un Documento '
             'Electrónico SIFEN (Factura Electrónica, Nota de Crédito '
             'Electrónica, Nota de Débito Electrónica, etc.). FE_Py usa este '
             'campo, al confirmar un comprobante, para saber si corresponde '
             'generar su Documento Electrónico automáticamente.\n\n'
             'Es siempre lo OPUESTO de "Es Físico" (local_py): un Tipo Fiscal '
             'es electrónico o es físico, nunca ambos ni ninguno.',
    )

    # ------------------------------------------------------------------
    # Sincronización con local_py_es_fisico
    #
    # local_py define su propio campo `local_py_es_fisico` (default True)
    # sobre este mismo modelo, representando el mismo concepto desde el
    # ángulo opuesto. Son dos fuentes de verdad para el mismo dato, así que
    # acá se fuerza que sean siempre coherentes entre sí — sin tocar ningún
    # archivo de local_py.
    #
    # El auto-destilde es bidireccional para que sea imposible llegar al
    # estado inválido desde cualquiera de los dos campos.
    # ------------------------------------------------------------------
    @api.onchange('fe_py_es_electronico')
    def _onchange_fe_py_es_electronico(self):
        for tipo in self:
            tipo.local_py_es_fisico = not tipo.fe_py_es_electronico

    @api.onchange('local_py_es_fisico')
    def _onchange_local_py_es_fisico_fe_py(self):
        for tipo in self:
            tipo.fe_py_es_electronico = not tipo.local_py_es_fisico

    @api.constrains('fe_py_es_electronico', 'local_py_es_fisico')
    def _check_fe_py_electronico_vs_fisico(self):
        for tipo in self:
            if tipo.fe_py_es_electronico == tipo.local_py_es_fisico:
                estado = 'ambos tildados' if tipo.fe_py_es_electronico else 'ambos sin tildar'
                raise ValidationError(
                    'El Tipo de Documento Fiscal "%s" tiene "Es Electrónico" y '
                    '"Es Físico" %s. Un Tipo Fiscal es electrónico O es físico: '
                    'exactamente una de las dos opciones debe estar tildada.'
                    % (tipo.name or '(sin nombre)', estado)
                )
