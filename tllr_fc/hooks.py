# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Crea las secuencias del módulo para las compañías ya existentes.

    Las compañías nuevas reciben sus secuencias al crearse
    (ver models/res_company.py).
    """
    companias = env['res.company'].sudo().search([])
    companias._tllr_fc_crear_secuencias()
    _logger.info("Taller: secuencias verificadas para %s compañía(s).", len(companias))
