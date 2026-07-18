# -*- coding: utf-8 -*-
import logging

from odoo.fields import Command

_logger = logging.getLogger(__name__)

# NOTA DE MIGRACIÓN: a partir de esta versión, todo lo relacionado al
# paquete de Localización Fiscal (plan de cuentas, grupos de cuenta,
# impuestos predeterminados, moneda de compañía, país fiscal, e impuestos
# de venta/compra por defecto) pasó a ser responsabilidad exclusiva del
# módulo l10n_py (paquete nativo "Paraguay - Contabilidad", seleccionable
# desde Ajustes > Facturación > Localización Fiscal > Paquete).
#
# local_py continúa haciéndose cargo de todo lo que ese paquete nativo no
# cubre: Tipo Fiscal, RUT, Timbrado/Nro. Documento, Libro Ventas/Compras,
# el reporte de Plan de Cuentas (que sigue funcionando igual, ya que lee
# account.account/account.group en tiempo real sin importar qué módulo
# cargó esos datos), y el refuerzo de permisos contables.

# Grupo base cuyos usuarios deben recibir automáticamente el grupo
# complementario de abajo (Requerimiento: acceso contable a cuentas de
# productos/categorías/clientes/proveedores y asientos, sin ajustes manuales).
ACCOUNTING_BASE_GROUP_XML_ID = 'account.group_account_manager'

# "Mostrar características de contabilidad completas": implica
# account.group_account_invoice y account.group_account_readonly. Este
# último es el que exige la vista nativa de Odoo (account.product_template
# _form_view) para mostrar las cuentas de ingreso/gasto en productos y
# categorías, y el que habilita las cuentas por cobrar/pagar en clientes y
# proveedores. Ver también data/account_groups_data.xml.
ACCOUNTING_EXTRA_GROUP_XML_ID = 'account.group_account_user'

# "Ajustes > Facturación > Impuestos > Precios" NO se guarda como un valor
# simple de ir.config_parameter: se implementa mediante dos grupos de
# usuario mutuamente excluyentes (exactamente uno de los dos debe estar
# activo): account.group_show_line_subtotals_tax_excluded ("Impuestos
# excluidos", el default) y account.group_show_line_subtotals_tax_included
# ("Impuestos incluidos"). Por eso hay que aplicarlo vía res.config.settings
# (igual que si se tildara la opción desde la pantalla de Ajustes), no
# escribiendo un ir.config_parameter directamente.


def _configure_accounting_groups(env):
    """Refuerza, sobre los usuarios existentes, el acceso contable completo
    para quienes tengan el grupo Contabilidad/Administrador
    (account.group_account_manager).

    La cobertura "automática hacia adelante" (cualquier usuario que reciba
    el grupo Manager en el futuro) queda garantizada de forma permanente por
    el implied_ids agregado en data/account_groups_data.xml. Esta función
    complementa ese ajuste aplicándolo también, de forma explícita, sobre los
    usuarios que ya tenían el grupo Manager antes de instalar/actualizar
    local_py (o antes de que se recalculara el cascada de grupos), y se
    invoca tanto en la instalación como desde el asistente "Restablecer
    configuración Paraguay".

    Esto habilita, sin ajustes manuales adicionales:
      - Ver y editar cuentas de ingreso/gasto en productos y categorías de
        producto.
      - Ver y editar cuentas por cobrar/pagar en clientes y proveedores.
      - Ver los asientos contables generados, incluyendo los de movimientos
        de stock, y confirmarlos (la confirmación ya la cubre el propio
        grupo Manager; el grupo complementario solo agrega visibilidad).
    """
    manager_group = env.ref(ACCOUNTING_BASE_GROUP_XML_ID, raise_if_not_found=False)
    extra_group = env.ref(ACCOUNTING_EXTRA_GROUP_XML_ID, raise_if_not_found=False)
    if not manager_group or not extra_group:
        _logger.warning(
            "local_py: no se encontraron los grupos contables esperados (%s / %s); "
            "se omite el refuerzo de permisos contables.",
            ACCOUNTING_BASE_GROUP_XML_ID, ACCOUNTING_EXTRA_GROUP_XML_ID,
        )
        return

    users_to_update = manager_group.all_user_ids - extra_group.all_user_ids
    if users_to_update:
        users_to_update.write({'groups_id': [Command.link(extra_group.id)]})
        _logger.info(
            "local_py: %s usuario(s) con Contabilidad/Administrador reforzado(s) con el "
            "grupo complementario '%s' (acceso a cuentas de productos, categorías, "
            "clientes/proveedores y asientos contables).",
            len(users_to_update), extra_group.name,
        )


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
        ('l10n_py_tipo_identificacion_fiscal_id', '=', False),
    ])
    if partners:
        partners.write({'l10n_py_tipo_identificacion_fiscal_id': ruc.id})
        _logger.info(
            "local_py: %s contacto(s) de tipo Empresa recibieron 'RUC' como Tipo de "
            "Identificación Fiscal por defecto.",
            len(partners),
        )


def configure_paraguay(env):
    """Punto de entrada único de los ajustes de local_py que no forman
    parte del paquete nativo de Localización Fiscal (l10n_py):
      - Refuerzo de permisos contables.
      - Visualización de precios/impuestos incluidos.
      - Códigos oficiales de Tipo Fiscal y Tipo de Identificación Fiscal por
        defecto en contactos existentes.
      - Reconstrucción del reporte de Plan de Cuentas.

    Es seguro invocarla más de una vez (instalación y, manualmente, desde el
    asistente de reconfiguración).
    """
    _configure_accounting_groups(env)
    _configure_tax_display(env)
    _backfill_tipo_fiscal_codes(env)
    _backfill_partner_tipo_identificacion(env)

    env['local_py.plan_cuentas.report'].sudo()._rebuild()

    _logger.info("local_py: configuración de Paraguay (local_py) aplicada correctamente.")


def post_init_hook(env):
    configure_paraguay(env)
