# -*- coding: utf-8 -*-
"""2026.19.002: la configuración pasa del modelo fe_py_recepcion.configuracion a campos
de la compañía (mostrados en Ajustes). Copia los valores ya cargados antes de que Odoo
quite el modelo anterior. Es defensivo: si la tabla vieja no existe, no hace nada."""
import logging

_logger = logging.getLogger(__name__)

# columna vieja -> columna nueva en res_company (tipo)
COLUMNAS = (
    ('diario_id', 'fe_py_recepcion_diario_id', 'integer'),
    ('impuesto_iva10_id', 'fe_py_recepcion_impuesto_iva10_id', 'integer'),
    ('impuesto_iva5_id', 'fe_py_recepcion_impuesto_iva5_id', 'integer'),
    ('impuesto_exento_id', 'fe_py_recepcion_impuesto_exento_id', 'integer'),
    # columna que agregaba el módulo puente con Compras (si estaba instalado)
    ('vincular_compras', 'fe_py_recepcion_vincular_compras', 'boolean'),
)


def _existe_columna(cr, tabla, columna):
    cr.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (tabla, columna))
    return bool(cr.fetchone())


def migrate(cr, version):
    cr.execute("SELECT to_regclass('fe_py_recepcion_configuracion')")
    if not cr.fetchone()[0]:
        return
    for vieja, nueva, tipo in COLUMNAS:
        if not _existe_columna(cr, 'fe_py_recepcion_configuracion', vieja):
            continue
        cr.execute('ALTER TABLE res_company ADD COLUMN IF NOT EXISTS "%s" %s' % (nueva, tipo))
        cr.execute(
            'UPDATE res_company c SET "%s" = k."%s" FROM fe_py_recepcion_configuracion k '
            'WHERE k.company_id = c.id AND k."%s" IS NOT NULL' % (nueva, vieja, vieja))
    # el diario de facturas también se propone para notas de crédito y de débito
    if _existe_columna(cr, 'fe_py_recepcion_configuracion', 'diario_id'):
        for nueva in ('fe_py_recepcion_diario_nc_id', 'fe_py_recepcion_diario_nd_id'):
            cr.execute('ALTER TABLE res_company ADD COLUMN IF NOT EXISTS "%s" integer' % nueva)
            cr.execute(
                'UPDATE res_company c SET "%s" = k.diario_id FROM fe_py_recepcion_configuracion k '
                'WHERE k.company_id = c.id AND k.diario_id IS NOT NULL AND c."%s" IS NULL'
                % (nueva, nueva))
    _logger.info("FE_Py Recepción: configuración migrada a la compañía.")
