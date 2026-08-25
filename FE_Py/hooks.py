# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

# Valores genéricos publicados por la DNIT para el Ambiente de Test (ver
# Guía de Pruebas para ekuatia, "Set de Pruebas: Código de Seguridad del
# Contribuyente"). Sirven únicamente para Ambiente = Simulado/Test —
# reemplazar por los propios antes de pasar a Producción.
IDCSC_GENERICO = '0001'
CSC_GENERICO = 'ABCD0000000000000000000000000000'

# Nombres de los Tipos Fiscales que deben quedar marcados como
# electrónicos. Se refuerza acá en Python, sin depender únicamente del
# XML de datos que actualiza el registro "Factura Electronica" (que
# pertenece a local_py, no a FE_Py) — así queda garantizado
# independientemente de cómo se haya resuelto esa actualización cruzada
# entre módulos en cada instalación puntual.
NOMBRES_TIPO_FISCAL_ELECTRONICO = (
    'Factura Electronica',
    'Nota de Credito Electronica',
    'Nota de Debito Electronica',
)


def _backfill_csc_generico(env):
    """Completa IdCSC/CSC genérico en las Compañías que todavía no tengan
    nada cargado (los 'default' del campo solo aplican a compañías nuevas,
    no retroactivamente a las que ya existían antes de instalar FE_Py) —
    así el módulo queda utilizable en modo Simulado apenas se instala, sin
    pasos manuales previos."""
    companies = env['res.company'].sudo().search([('fe_py_idcsc', '=', False)])
    if companies:
        companies.write({'fe_py_idcsc': IDCSC_GENERICO, 'fe_py_csc': CSC_GENERICO})
        _logger.info(
            "FE_Py: IdCSC/CSC genérico (Ambiente de Test) aplicado a %s compañía(s).",
            len(companies),
        )


def _backfill_tipo_fiscal_electronico(env):
    """Refuerzo explícito: marca fe_py_es_electronico=True en los 3 Tipos
    Fiscales electrónicos, por nombre, sin depender de que la actualización
    vía XML de datos sobre el registro de local_py se haya aplicado."""
    tipos = env['local_py.tipo_fiscal'].sudo().search([
        ('name', 'in', list(NOMBRES_TIPO_FISCAL_ELECTRONICO)),
        ('fe_py_es_electronico', '=', False),
    ])
    if tipos:
        tipos.write({'fe_py_es_electronico': True})
        _logger.info(
            "FE_Py: fe_py_es_electronico reforzado en %s Tipo(s) Fiscal(es): %s",
            len(tipos), ', '.join(tipos.mapped('name')),
        )


def post_init_hook(env):
    _backfill_csc_generico(env)
    _backfill_tipo_fiscal_electronico(env)
