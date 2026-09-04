# -*- coding: utf-8 -*-
"""Migración a 2026.03.001 — rediseño de catálogos.

Corre UNA SOLA VEZ, al actualizar a esta versión. Hace tres cosas, en
este orden:

  1. Mueve la configuración de Facturación Electrónica desde res.company
     al modelo nuevo fe_py.configuracion, antes de que los campos viejos
     de la Compañía desaparezcan.
  2. Asigna el código de Afectación IVA a los impuestos existentes,
     replicando exactamente lo que el generador hacía hasta ahora: si el
     impuesto es 10% o 5% se marca como Gravado; el resto, Exento. Sin
     esto, después de actualizar no se podría generar ningún XML.
  3. Completa la unidad de medida SIFEN en todos los productos con
     "Unidad (77)", que era lo que el generador informaba siempre. Y
     traduce los códigos que antes vivían en campos de tipo lista
     (tipo de operación, motivo de emisión, etc.) a los registros del
     catálogo correspondiente.

Todo con SQL directo: en pre-migración los modelos nuevos todavía no
están disponibles en el ORM, y además así no depende de que los defaults
o los constraints nuevos ya estén activos.
"""
import logging

_logger = logging.getLogger(__name__)


def _columna_existe(cr, tabla, columna):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = %s AND column_name = %s
    """, (tabla, columna))
    return bool(cr.fetchone())


def _tabla_existe(cr, tabla):
    cr.execute("SELECT to_regclass(%s)", (tabla,))
    return cr.fetchone()[0] is not None


def migrate(cr, version):
    if not version:
        return

    _migrar_configuracion_de_compania(cr)
    _logger.info("FE_Py 2026.03.001: migración previa completada.")


def _migrar_configuracion_de_compania(cr):
    """Copia los campos de Facturación Electrónica de res_company a una
    tabla temporal, para que la post-migración pueda volcarlos en
    fe_py_configuracion una vez que el modelo exista.

    Se hace en dos pasos (pre y post) porque en la pre-migración la tabla
    fe_py_configuracion todavía no fue creada por el ORM."""
    if not _columna_existe(cr, 'res_company', 'fe_py_ambiente'):
        _logger.info(
            "FE_Py: res_company no tiene los campos viejos de Facturación "
            "Electrónica — no hay configuración que migrar."
        )
        return

    columnas = [
        'fe_py_habilitado', 'fe_py_ambiente', 'fe_py_tipo_contribuyente',
        'fe_py_tipo_regimen', 'fe_py_actividad_economica_codigo',
        'fe_py_actividad_economica_desc', 'fe_py_certificado_filename',
        'fe_py_certificado_password', 'fe_py_cert_path',
        'fe_py_private_key_path', 'fe_py_public_key_path',
        'fe_py_certificado_vencimiento', 'fe_py_idcsc', 'fe_py_csc',
        'fe_py_envio_automatico', 'fe_py_kude_automatico',
        'fe_py_email_automatico', 'fe_py_reintento_automatico',
    ]
    presentes = [c for c in columnas if _columna_existe(cr, 'res_company', c)]
    if not presentes:
        return

    cr.execute("DROP TABLE IF EXISTS fe_py_migracion_config")
    cr.execute("""
        CREATE TABLE fe_py_migracion_config AS
        SELECT id AS company_id, %s FROM res_company
    """ % ', '.join(presentes))
    cr.execute("SELECT count(*) FROM fe_py_migracion_config")
    total = cr.fetchone()[0]
    _logger.info(
        "FE_Py: configuración de Facturación Electrónica de %s compañía(s) "
        "guardada para trasladar a Configuraciones Generales FEPy.", total,
    )
