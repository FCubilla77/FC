# -*- coding: utf-8 -*-
"""2026.19.016: el valor fijo de un campo relacional o de selección pasa de texto a una lista.

Convierte las filas de mapeo ya cargadas: el texto (identificador externo, nombre exacto o valor)
se busca en la tabla del campo de destino. Lo que no se encuentre queda como estaba y se
avisa en el log para corregirlo a mano en la pantalla de mapeo."""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Mapeo = env['fe_py_recepcion.mapeo'].with_context(active_test=False)
    for mapeo in Mapeo.search([('origen', '=', 'fijo'), ('valor_fijo', '!=', False)]):
        campo = mapeo.campo_destino_id
        texto = (mapeo.valor_fijo or '').strip()
        try:
            if campo.ttype == 'many2one' and not mapeo.valor_fijo_id:
                ok, id_registro = mapeo._resolver_relacion(campo, texto)
                if ok:
                    mapeo.write({'valor_fijo_id': id_registro, 'valor_fijo': False})
                    continue
            elif campo.ttype == 'selection' and not mapeo.valor_fijo_opcion_id:
                opcion = env['ir.model.fields.selection'].search([
                    ('field_id', '=', campo.id), '|', ('value', '=ilike', texto),
                    ('name', '=ilike', texto)], limit=1)
                if opcion:
                    mapeo.write({'valor_fijo_opcion_id': opcion.id, 'valor_fijo': False})
                    continue
            else:
                continue
        except Exception as error:  # una fila rota no debe frenar la actualización
            _logger.warning('FE_Py Recepción: no se pudo convertir el mapeo %s: %s', mapeo.id, error)
            continue
        _logger.warning(
            'FE_Py Recepción: el valor fijo «%s» del mapeo %s no se encontró en %s; elíjalo de la '
            'lista en Configuración > Mapeo de Campos.', texto, mapeo.id, campo.relation or campo.model)
