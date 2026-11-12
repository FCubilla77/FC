# -*- coding: utf-8 -*-
"""Utilidades de bajo nivel contra la base de datos.

No importa nada del propio módulo: se carga primero en models/__init__.py para
que cualquier otro archivo pueda usarla sin riesgo de import circular.
"""


def local_py_tabla_existe(cr, tabla):
    """True si `tabla` existe en la base de datos.

    Hay que preguntar ANTES de leer un modelo cuya tabla podría no existir
    todavía. El caso concreto: Odoo evalúa el `default` de un campo nuevo
    durante el `_auto_init` del módulo (para completar las filas que ya
    existen), y ese momento puede llegar antes de que estén creadas todas las
    tablas del módulo — el orden depende de en qué posición se importa cada
    archivo en models/__init__.py.

    No se puede resolver con `try/except`: en PostgreSQL una consulta que falla
    aborta la transacción completa, así que un `UndefinedTable` atrapado deja la
    instalación inutilizable igual. Por eso se consulta `to_regclass`, que
    devuelve NULL en lugar de fallar cuando el nombre no existe.
    """
    cr.execute("SELECT to_regclass(%s)", (tabla,))
    return cr.fetchone()[0] is not None
