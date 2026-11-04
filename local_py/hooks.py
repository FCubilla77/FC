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


def _buscar_cuenta(env, company, code):
    """Busca una cuenta por su Código dentro de la Compañía.

    No se referencian por ID externo (l10n_py.py_1_01_...) porque el sistema
    de plantillas de Odoo crea una copia por Compañía, con un ID externo
    distinto al del template — buscar por Código es lo que funciona igual en
    mono y multi-compañía."""
    return env['account.account'].sudo().search([
        ('code', '=', code),
        ('company_ids', 'in', company.id),
    ], limit=1)


# Diarios que local_py necesita para operar, con la Cuenta del plan de
# l10n_py que les corresponde. Los Diarios de VENTA (Factura, Nota de
# Crédito, Nota de Débito) quedan deliberadamente afuera: exigen Timbrado,
# Nro. Documento, Nro. Documento Final y fechas de vigencia — datos reales
# del timbrado asignado por la DNIT, que solo puede cargar el usuario.
DIARIOS_LOCAL_PY = [
    # (campo en Configuración, nombre, código, tipo, código de cuenta)
    ('l10n_py_diario_retencion_iva_id', 'Retención IVA', 'RIVA', 'general', '2.01.03.01.004'),
    ('l10n_py_diario_retencion_renta_id', 'Retención Renta', 'RRTA', 'general', '2.01.03.01.004'),
    ('l10n_py_diario_retencion_recibida_id', 'Retención Recibida', 'RREC', 'general', '1.01.03.02.006'),
    ('l10n_py_diario_cheque_cliente_id', 'Cheques de Clientes', 'CHCL', 'bank', '1.01.01.01.004'),
]

# Cuentas de Configuraciones Localización Py, por Código del plan de l10n_py.
CUENTAS_LOCAL_PY = [
    ('l10n_py_cuenta_gasto_absorcion_id', '7.02.17.01.001'),
    ('l10n_py_cuenta_gasto_absorcion_renta_id', '7.02.17.01.001'),
    ('l10n_py_cuenta_retencion_a_confirmar_id', '1.01.03.02.006'),
    ('l10n_py_cuenta_retenciones_recibidas_iva_id', '1.01.03.02.002'),
    ('l10n_py_cuenta_retenciones_recibidas_renta_id', '1.01.03.02.005'),
]


def _configure_diarios_y_cuentas(env):
    """Crea los Diarios que local_py necesita (Retención IVA, Retención
    Renta, Retención Recibida y Cheques de Clientes) y completa las Cuentas
    de Configuraciones Localización Py, tomándolas del plan de cuentas de
    l10n_py por su Código.

    Es idempotente y no invasiva: solo crea un Diario si no existe otro con
    el mismo código en esa Compañía, y solo completa un campo de
    Configuración que esté vacío — nunca pisa una elección hecha a mano.
    Si el plan de l10n_py todavía no está instalado en una Compañía, esa
    Compañía se saltea con un aviso en el log, sin cortar el proceso.
    """
    Journal = env['account.journal'].sudo()
    Config = env['local_py.configuracion_localizacion'].sudo()

    for company in env['res.company'].sudo().search([]):
        # Si no encuentra ni una de las cuentas esperadas, esta Compañía no
        # tiene cargado el plan de l10n_py — no tiene sentido seguir.
        if not _buscar_cuenta(env, company, '1.01.03.02.006'):
            _logger.info(
                "local_py: la compañía '%s' no tiene el plan de cuentas de l10n_py "
                "cargado — se omite la configuración automática de Diarios y Cuentas.",
                company.name,
            )
            continue

        config = Config.search([('company_id', '=', company.id)], limit=1)
        if not config:
            config = Config.create({'company_id': company.id})
            _logger.info(
                "local_py: se creó el registro de Configuraciones Localización Py para "
                "la compañía '%s'.", company.name,
            )

        vals_config = {}

        for campo, nombre, codigo_diario, tipo, codigo_cuenta in DIARIOS_LOCAL_PY:
            if config[campo]:
                continue  # ya configurado a mano — no se toca
            journal = Journal.search([
                ('code', '=', codigo_diario), ('company_id', '=', company.id),
            ], limit=1)
            if not journal:
                cuenta = _buscar_cuenta(env, company, codigo_cuenta)
                if not cuenta:
                    _logger.warning(
                        "local_py: no se encontró la Cuenta %s en la compañía '%s' — no se "
                        "creó el Diario '%s'. Créelo a mano desde Contabilidad > "
                        "Configuración > Diarios.",
                        codigo_cuenta, company.name, nombre,
                    )
                    continue
                journal = Journal.create({
                    'name': nombre,
                    'code': codigo_diario,
                    'type': tipo,
                    'company_id': company.id,
                    'default_account_id': cuenta.id,
                })
                _logger.info(
                    "local_py: Diario '%s' (%s) creado en la compañía '%s' con la Cuenta %s.",
                    nombre, codigo_diario, company.name, codigo_cuenta,
                )
            vals_config[campo] = journal.id

        for campo, codigo_cuenta in CUENTAS_LOCAL_PY:
            if config[campo]:
                continue  # ya configurado a mano — no se toca
            cuenta = _buscar_cuenta(env, company, codigo_cuenta)
            if cuenta:
                vals_config[campo] = cuenta.id
            else:
                _logger.warning(
                    "local_py: no se encontró la Cuenta %s en la compañía '%s' — el campo "
                    "'%s' queda sin completar.", codigo_cuenta, company.name, campo,
                )

        if vals_config:
            config.write(vals_config)
            _logger.info(
                "local_py: Configuraciones Localización Py completada automáticamente para "
                "la compañía '%s' (%s campo(s)).", company.name, len(vals_config),
            )


def configure_paraguay(env):
    """Punto de entrada único de los ajustes de local_py que no forman
    parte del paquete nativo de Localización Fiscal (l10n_py):
      - Refuerzo de permisos contables.
      - Visualización de precios/impuestos incluidos.
      - Códigos oficiales de Tipo Fiscal y Tipo de Identificación Fiscal por
        defecto en contactos existentes.
      - Creación de los Diarios de Retención (IVA, Renta, Recibida) y de
        Cheques de Clientes, y completado de las Cuentas de Configuraciones
        Localización Py desde el plan de cuentas de l10n_py.
      - Reconstrucción del reporte de Plan de Cuentas.

    Es seguro invocarla más de una vez (instalación y, manualmente, desde el
    asistente de reconfiguración).
    """
    _configure_accounting_groups(env)
    _configure_tax_display(env)
    _backfill_tipo_fiscal_codes(env)
    _backfill_partner_tipo_identificacion(env)
    _configure_diarios_y_cuentas(env)

    env['local_py.plan_cuentas.report'].sudo()._rebuild()

    _logger.info("local_py: configuración de Paraguay (local_py) aplicada correctamente.")


def post_init_hook(env):
    configure_paraguay(env)
