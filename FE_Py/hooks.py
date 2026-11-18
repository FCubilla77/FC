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
    configs = env['fe_py.configuracion'].sudo().search([('idcsc', '=', False)])
    if configs:
        configs.write({'idcsc': IDCSC_GENERICO, 'csc': CSC_GENERICO})
        _logger.info(
            "FE_Py: IdCSC/CSC genérico (Ambiente de Test) aplicado a %s configuración(es).",
            len(configs),
        )


def _crear_configuracion(env):
    """Crea la Configuración FEPy de cada Compañía en una instalación
    nueva. Reutiliza el mismo método que usa el resto del módulo, para no
    duplicar la lista de valores por defecto en dos lugares."""
    Config = env['fe_py.configuracion'].sudo()
    creadas = 0
    for company in env['res.company'].sudo().search([]):
        if Config.search([('company_id', '=', company.id)], limit=1):
            continue
        Config._crear_para_compania(company)
        creadas += 1
    if creadas:
        _logger.info("FE_Py: %s Configuración(es) Generales FEPy creadas.", creadas)


def post_init_hook(env):
    _crear_configuracion(env)
    _crear_mapeo_inicial(env)


def _crear_mapeo_inicial(env):
    """Deja una fila por cada dato que FE_Py necesita del exterior, y
    completa las que pueda detectar por nombre de campo.

    No falla si no encuentra nada: deja las filas vacías para que el
    usuario las complete en Doc. Electrónicos Py > Mapeo de Datos. FE_Py
    no sabe ni necesita saber qué módulo provee cada campo.
    """
    Mapeo = env['fe_py.mapeo'].sudo()
    creadas = Mapeo._crear_filas_faltantes()
    Mapeo.action_fe_py_cargar_sugeridos()
    faltan = Mapeo._faltantes()
    if faltan:
        _logger.warning(
            "FE_Py: el Mapeo de Datos quedó incompleto (%s filas creadas). "
            "Falta indicar de qué campo salen: %s. Hasta completarlo no se "
            "pueden emitir Documentos Electrónicos.",
            creadas, ', '.join(faltan))
    else:
        _logger.info("FE_Py: Mapeo de Datos completo (%s filas).", creadas)
