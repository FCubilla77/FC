# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

# NOTA DE MIGRACIÓN: a partir de esta versión, todo lo relacionado al
# paquete de Localización Fiscal (plan de cuentas, grupos de cuenta,
# impuestos predeterminados, moneda de compañía, país fiscal, e impuestos
# de venta/compra por defecto) pasó a ser responsabilidad exclusiva del
# módulo l10n_py (paquete nativo "Paraguay - Contabilidad", seleccionable
# desde Ajustes > Facturación > Localización Fiscal > Paquete).
#
# local_py continúa haciéndose cargo de todo lo que ese paquete nativo no
# cubre: Tipo Fiscal, RUT, Timbrado/Nro. Documento y Libro Ventas/Compras.
# El reporte de Plan de Cuentas y el refuerzo de permisos contables (los
# usuarios con Contabilidad/Administrador reciben también el grupo que
# habilita las cuentas de ingreso/gasto en productos y categorías y las
# cuentas por cobrar/pagar en contactos) los provee ahora el módulo
# l10n_py; local_py ya no los duplica.

# "Ajustes > Facturación > Impuestos > Precios" NO se guarda como un valor
# simple de ir.config_parameter: se implementa mediante dos grupos de
# usuario mutuamente excluyentes (exactamente uno de los dos debe estar
# activo): account.group_show_line_subtotals_tax_excluded ("Impuestos
# excluidos", el default) y account.group_show_line_subtotals_tax_included
# ("Impuestos incluidos"). Por eso hay que aplicarlo vía res.config.settings
# (igual que si se tildara la opción desde la pantalla de Ajustes), no
# escribiendo un ir.config_parameter directamente.


def _configure_tax_display(env):
    """Fuerza 'Ajustes > Facturación > Impuestos > Precios' a 'Impuestos
    incluidos'.

    Confirmado contra el código fuente real de Odoo 19
    (addons/account/models/company.py): el campo es
    'account_price_include' en res.company (Selection:
    'tax_included'/'tax_excluded', default 'tax_excluded').

    Odoo bloquea este cambio con un ValidationError si la compañía ya tiene
    contabilidad iniciada (facturas u otros movimientos ya posteados) —
    ver la constraint '_check_set_account_price_include'. En ese caso se
    registra un warning y se continúa sin romper el resto de
    configure_paraguay().
    """
    company = env.ref('base.main_company')
    if company.account_price_include == 'tax_included':
        return
    try:
        company.account_price_include = 'tax_included'
        _logger.info("local_py: 'Impuestos > Precios' configurado como 'Impuestos incluidos'.")
    except Exception:
        _logger.warning(
            "local_py: no se pudo configurar 'Impuestos > Precios' como 'Impuestos "
            "incluidos' — probablemente la compañía ya tiene contabilidad iniciada "
            "(facturas u otros movimientos posteados). Ajustarlo manualmente si "
            "corresponde desde Ajustes > Facturación > Impuestos > Precios."
        )


def _backfill_tipo_fiscal_codes(env):
    """Fuerza el código oficial (Tabla 4 DNIT) en los 5 registros de Tipo
    Fiscal que ya existían antes de esta versión. Son datos noupdate="1":
    la recarga del archivo XML por sí sola no actualiza registros ya
    creados, por eso se refuerza acá."""
    codes = {
        'tipo_fiscal_factura': '109',
        'tipo_fiscal_factura_electronica': '109',
        'tipo_fiscal_nota_debito': '111',
        'tipo_fiscal_nota_credito': '110',
        'tipo_fiscal_autofactura': '101',
    }
    for xml_id, code in codes.items():
        record = env.ref('local_py.%s' % xml_id, raise_if_not_found=False)
        if record and record.code != code:
            record.code = code


def _backfill_partner_tipo_identificacion(env):
    """Asigna 'RUC' como Tipo de Identificación Fiscal por defecto a todos
    los contactos de tipo Empresa que todavía no tengan ese campo
    completado (aplica tanto a los ya existentes como salvaguarda para
    cualquier importación previa a esta versión)."""
    ruc = env.ref('local_py.tipo_identificacion_ruc', raise_if_not_found=False)
    if not ruc:
        return
    partners = env['res.partner'].sudo().search([
        ('is_company', '=', True),
        ('local_py_tipo_identificacion_fiscal_id', '=', False),
    ])
    if partners:
        partners.write({'local_py_tipo_identificacion_fiscal_id': ruc.id})
        _logger.info(
            "local_py: %s contacto(s) de tipo Empresa recibieron 'RUC' como Tipo de "
            "Identificación Fiscal por defecto.",
            len(partners),
        )


def _asegurar_configuracion(env):
    """Asegura que exista el registro de Configuraciones Localización Py de cada
    Compañía, vacío.

    Antes, acá se creaban los Diarios de Retención y de Cheques de Clientes y se
    completaban las Cuentas de la Configuración buscándolas por su Código en el plan
    estándar de Paraguay ('1.01.03.02.006' y compañía). Eso ataba local_py a ese plan:
    con un plan propio del cliente, ninguno de esos códigos existe y la configuración
    quedaba vacía sin explicación.

    Ahora la configuración se carga con la plantilla Excel (Ajustes > Configuración
    local_py > Configuración por plantilla), donde el usuario indica qué cuenta de SU
    plan cumple cada función. Este hook solo deja el registro creado, para que la
    pantalla de Configuraciones Localización Py se abra sin tener que crearlo a mano.
    """
    Config = env['local_py.configuracion_localizacion'].sudo()
    for company in env['res.company'].sudo().search([]):
        if not Config.search([('company_id', '=', company.id)], limit=1):
            Config.create({'company_id': company.id})
            _logger.info(
                "local_py: se creó el registro de Configuraciones Localización Py para "
                "la compañía '%s'. Complete la configuración con la plantilla Excel "
                "(Ajustes > Configuración local_py).", company.name,
            )


def configure_paraguay(env):
    """Punto de entrada único de los ajustes de local_py que no forman
    parte del paquete nativo de Localización Fiscal (l10n_py):
      - Visualización de precios/impuestos incluidos.
      - Códigos oficiales de Tipo Fiscal y Tipo de Identificación Fiscal por
        defecto en contactos existentes.
      - Registro de Configuraciones Localización Py de cada Compañía (vacío;
        se completa con la plantilla Excel de configuración).

    Es seguro invocarla más de una vez (instalación y, manualmente, desde el
    asistente de reconfiguración).
    """
    _configure_tax_display(env)
    _backfill_tipo_fiscal_codes(env)
    _backfill_partner_tipo_identificacion(env)
    _asegurar_configuracion(env)

    _logger.info("local_py: configuración de Paraguay (local_py) aplicada correctamente.")


def post_init_hook(env):
    configure_paraguay(env)
