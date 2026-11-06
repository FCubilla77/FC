# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Las equivalencias existentes no tenían 'último uso': se toma su fecha de
    modificación, para que la sugerencia por más reciente tenga un criterio."""
    cr.execute("""
        UPDATE fe_py_recepcion_equivalencia
           SET ultimo_uso = COALESCE(write_date, create_date, now() AT TIME ZONE 'UTC')
         WHERE ultimo_uso IS NULL
    """)
