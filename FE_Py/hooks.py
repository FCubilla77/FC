# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

# Valores genéricos publicados por la DNIT para el Ambiente de Test (ver
# Guía de Pruebas para ekuatia, "Set de Pruebas: Código de Seguridad del
# Contribuyente"). Sirven únicamente para Ambiente = Simulado/Test —
# reemplazar por los propios antes de pasar a Producción.
IDCSC_GENERICO = '0001'
CSC_GENERICO = 'ABCD0000000000000000000000000000'


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


def post_init_hook(env):
    _backfill_csc_generico(env)
