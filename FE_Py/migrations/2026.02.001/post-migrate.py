# -*- coding: utf-8 -*-
"""Aplica el mapeo iTipIDRec en instalaciones ya existentes.

`post_init_hook` solo corre en instalación nueva, así que en un upgrade
hay que invocar el mismo backfill desde acá. Se reutiliza la función del
hook para no duplicar la tabla de mapeo en dos lugares (que fue justo el
tipo de duplicación que ya causó bugs en este proyecto).
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    from odoo.addons.FE_Py.hooks import _backfill_itipidrec

    env = api.Environment(cr, SUPERUSER_ID, {})
    _backfill_itipidrec(env)
    _logger.info("FE_Py 2026.02.001: backfill de iTipIDRec ejecutado en upgrade.")
