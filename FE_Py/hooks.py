# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

# Valores genéricos publicados por la DNIT para el Ambiente de Test (ver
# Guía de Pruebas para ekuatia, "Set de Pruebas: Código de Seguridad del
# Contribuyente"). Sirven únicamente para Ambiente = Simulado/Test —
# reemplazar por los propios antes de pasar a Producción.
IDCSC_GENERICO = '0001'
CSC_GENERICO = 'ABCD0000000000000000000000000000'

# Nombres de los Tipos Fiscales que deben quedar marcados como
# electrónicos. Se refuerza acá en Python, sin depender únicamente del
# XML de datos que actualiza el registro "Factura Electronica" (que
# pertenece a local_py, no a FE_Py) — así queda garantizado
# independientemente de cómo se haya resuelto esa actualización cruzada
# entre módulos en cada instalación puntual.
NOMBRES_TIPO_FISCAL_ELECTRONICO = (
    'Factura Electronica',
    'Nota de Credito Electronica',
    'Nota de Debito Electronica',
)


def _backfill_csc_generico(env):
    """Completa IdCSC/CSC genérico en las Compañías que todavía no tengan
    nada cargado (los 'default' del campo solo aplican a compañías nuevas,
    no retroactivamente a las que ya existían antes de instalar FE_Py) —
    así el módulo queda utilizable en modo Simulado apenas se instala, sin
    pasos manuales previos."""
    companies = env['res.company'].sudo().search([('fe_py_idcsc', '=', False)])
    if companies:
        companies.write({'fe_py_idcsc': IDCSC_GENERICO, 'fe_py_csc': CSC_GENERICO})
        _logger.info(
            "FE_Py: IdCSC/CSC genérico (Ambiente de Test) aplicado a %s compañía(s).",
            len(companies),
        )


def _backfill_tipo_fiscal_electronico(env):
    """Refuerzo explícito: marca fe_py_es_electronico=True en los 3 Tipos
    Fiscales electrónicos, por nombre, sin depender de que la actualización
    vía XML de datos sobre el registro de local_py se haya aplicado.

    Además sincroniza local_py_es_fisico como su opuesto exacto — desde
    2026.02.001 ambos campos tienen un constraint que exige que sean
    siempre contrarios entre sí."""
    TipoFiscal = env['local_py.tipo_fiscal'].sudo()

    tipos = TipoFiscal.search([
        ('name', 'in', list(NOMBRES_TIPO_FISCAL_ELECTRONICO)),
    ])
    a_corregir = tipos.filtered(
        lambda t: not t.fe_py_es_electronico or t.local_py_es_fisico
    )
    if a_corregir:
        a_corregir.write({'fe_py_es_electronico': True, 'local_py_es_fisico': False})
        _logger.info(
            "FE_Py: Es Electrónico / Es Físico sincronizado en %s Tipo(s) Fiscal(es): %s",
            len(a_corregir), ', '.join(a_corregir.mapped('name')),
        )

    # Los que NO son electrónicos deben quedar como físicos — cubre el caso
    # de un registro que hubiera quedado con ambos campos en False.
    otros = TipoFiscal.search([
        ('name', 'not in', list(NOMBRES_TIPO_FISCAL_ELECTRONICO)),
        ('local_py_es_fisico', '=', False),
        ('fe_py_es_electronico', '=', False),
    ])
    if otros:
        otros.write({'local_py_es_fisico': True})
        _logger.info(
            "FE_Py: %s Tipo(s) Fiscal(es) no electrónico(s) marcados como físicos.",
            len(otros),
        )


def _backfill_itipidrec(env):
    """Carga el mapeo Tipo de Identificación Fiscal (local_py, Tabla 3
    Marangatu) -> iTipIDRec (SIFEN, Tabla D208).

    Se hace por Python y no por XML de datos a propósito: los registros
    del catálogo pertenecen a local_py y están marcados noupdate="1", así
    que un <record> desde FE_Py no los actualiza de forma confiable (ya
    ocurrió con fe_py_es_electronico, que hubo que tildar a mano).

    Solo completa los que estén vacíos — nunca pisa un mapeo que alguien
    haya ajustado a mano."""
    mapeo = {
        'local_py.tipo_identificacion_cedula': '1',            # Cédula paraguaya
        'local_py.tipo_identificacion_pasaporte': '2',         # Pasaporte
        'local_py.tipo_identificacion_cedula_extranjero': '3',  # Cédula extranjera
        'local_py.tipo_identificacion_sin_nombre': '5',        # Innominado
        'local_py.tipo_identificacion_diplomatico': '6',       # Tarjeta Diplomática
        'local_py.tipo_identificacion_tributaria': '9',        # Otro + descripción libre
        # "RUC" (código 11) no se mapea: un receptor con RUC se informa por
        # dRucRec/dDVRec, no pasa por la tabla iTipIDRec.
    }
    aplicados = 0
    for xmlid, codigo in mapeo.items():
        registro = env.ref(xmlid, raise_if_not_found=False)
        if registro and not registro.fe_py_itipidrec:
            registro.sudo().fe_py_itipidrec = codigo
            aplicados += 1
    if aplicados:
        _logger.info("FE_Py: mapeo iTipIDRec aplicado a %s tipo(s) de identificación.", aplicados)


def post_init_hook(env):
    _backfill_csc_generico(env)
    _backfill_tipo_fiscal_electronico(env)
    _backfill_itipidrec(env)
