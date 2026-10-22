# -*- coding: utf-8 -*-
"""2026.19.017: la entrega de una OT cancelada se habilita al cancelar.

Las OT canceladas con liquidación que aún no se entregaron conservan la entrega habilitada.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE tllr_fc_ot
           SET entrega_habilitada = TRUE
         WHERE state = 'cancelada' AND liquidada AND fecha_entrega IS NULL
    """)
