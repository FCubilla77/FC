# -*- coding: utf-8 -*-
"""2026.19.008: el estado «Confirmado» pasa a significar «factura publicada». Las recepciones
que estaban Confirmadas pero cuya factura sigue en borrador pasan al nuevo estado «Borrador»."""


def migrate(cr, version):
    cr.execute("""
        UPDATE fe_py_recepcion_documento d
           SET state = 'borrador'
          FROM account_move m
         WHERE d.move_id = m.id AND d.state = 'confirmado' AND m.state = 'draft'
    """)
