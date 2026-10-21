# -*- coding: utf-8 -*-
"""2026.19.011: «Entregado» de la revisión de inventario pasa de check a Sí / No."""


def migrate(cr, version):
    cr.execute("""
        SELECT data_type FROM information_schema.columns
         WHERE table_name = 'tllr_fc_entrega_linea' AND column_name = 'entregado'
    """)
    fila = cr.fetchone()
    if fila and fila[0] == 'boolean':
        cr.execute("""
            ALTER TABLE tllr_fc_entrega_linea
            ALTER COLUMN entregado TYPE varchar
            USING (CASE WHEN entregado THEN 'si' ELSE 'no' END)
        """)
