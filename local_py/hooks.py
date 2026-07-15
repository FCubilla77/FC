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

# Clave del parámetro de sistema que controla "Ajustes > Facturación >
# Impuestos > Precios": si los subtotales de línea se muestran con
# impuestos incluidos o excluidos.
TAX_DISPLAY_CONFIG_PARAM = 'account.show_line_subtotals_tax_selection'
TAX_DISPLAY_CONFIG_VALUE = 'tax_included'


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
    incluidos' (subtotales de línea mostrados con impuestos incluidos)."""
    env['ir.config_parameter'].sudo().set_param(
        TAX_DISPLAY_CONFIG_PARAM, TAX_DISPLAY_CONFIG_VALUE,
    )
    _logger.info(
        "local_py: 'Impuestos > Precios' configurado como '%s'.",
        TAX_DISPLAY_CONFIG_VALUE,
    )


def configure_paraguay(env):
    """Punto de entrada único de los ajustes de local_py que no forman
    parte del paquete nativo de Localización Fiscal (l10n_py):
      - Refuerzo de permisos contables.
      - Visualización de precios/impuestos incluidos.
      - Reconstrucción del reporte de Plan de Cuentas.

    Es seguro invocarla más de una vez (instalación y, manualmente, desde el
    asistente de reconfiguración).
    """
    _configure_accounting_groups(env)
    _configure_tax_display(env)

    env['local_py.plan_cuentas.report'].sudo()._rebuild()

    _logger.info("local_py: configuración de Paraguay (local_py) aplicada correctamente.")


def post_init_hook(env):
    configure_paraguay(env)
