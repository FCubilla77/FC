# -*- coding: utf-8 -*-
import logging

from odoo.fields import Command

_logger = logging.getLogger(__name__)

# Cuentas contables a utilizar en las líneas de distribución de los impuestos,
# según el plan de cuentas de Paraguay cargado por este mismo módulo
# (data/account_account_data.xml). Ventas -> IVA A PAGAR (2.01.03.03);
# Compras -> IVA - CRÉDITO FISCAL (1.01.03.05.03).
TAX_ACCOUNT_SALE_NAME = 'IVA A PAGAR'
TAX_ACCOUNT_PURCHASE_NAME = 'IVA - CRÉDITO FISCAL'

# Definición de los 6 impuestos predeterminados de Paraguay (Requerimiento 001)
TAXES_DATA = [
    {
        'xml_id': 'tax_iva_10_ventas',
        'name': 'IVA 10% Ventas',
        'type_tax_use': 'sale',
        'amount': 10,
        'tax_group_xml_id': 'local_py.tax_group_iva_10',
        'include_base_amount': False,
    },
    {
        'xml_id': 'tax_iva_5_ventas',
        'name': 'IVA 5% Ventas',
        'type_tax_use': 'sale',
        'amount': 5,
        'tax_group_xml_id': 'local_py.tax_group_iva_5',
        'include_base_amount': False,
    },
    {
        'xml_id': 'tax_exentas_ventas',
        'name': 'Exentas Ventas',
        'type_tax_use': 'sale',
        'amount': 0,
        'tax_group_xml_id': 'local_py.tax_group_exentas',
        'include_base_amount': True,
    },
    {
        'xml_id': 'tax_iva_10_compras',
        'name': 'IVA 10% Compras',
        'type_tax_use': 'purchase',
        'amount': 10,
        'tax_group_xml_id': 'local_py.tax_group_iva_10',
        'include_base_amount': False,
    },
    {
        'xml_id': 'tax_iva_5_compras',
        'name': 'IVA 5% Compras',
        'type_tax_use': 'purchase',
        'amount': 5,
        'tax_group_xml_id': 'local_py.tax_group_iva_5',
        'include_base_amount': False,
    },
    {
        'xml_id': 'tax_exentas_compras',
        'name': 'Exentas Compras',
        'type_tax_use': 'purchase',
        'amount': 0,
        'tax_group_xml_id': 'local_py.tax_group_exentas',
        'include_base_amount': True,
    },
]


# Códigos de los Títulos de nivel 1 (raíz) que eran solo referenciales en la
# planilla original: Odoo ya distingue Activo/Pasivo/Patrimonio/Ingresos/Gastos
# a través del campo account_type de cada cuenta, así que estos grupos no
# hacen falta como account.group.
LEGACY_ROOT_GROUP_CODES = ['1', '2', '3', '4', '5', '6', '7']


def _cleanup_chart_of_accounts(env, company):
    """Ajustes de limpieza sobre el plan de cuentas de Paraguay:

    1) Elimina los account.group de nivel 1 (Títulos raíz) que hayan quedado
       de una versión anterior del módulo: eran solo referenciales, Odoo ya
       distingue esas categorías por account_type. Sus grupos hijos (nivel 2)
       quedan directamente como raíz del árbol de reportes.
    2) Fuerza la moneda PYG en todas las cuentas Imputables propias del plan
       de cuentas de Paraguay (creadas por este módulo).
    3) Archiva (active=False) cualquier cuenta contable de la compañía que NO
       forme parte del plan de cuentas de Paraguay cargado por local_py (por
       ejemplo, cuentas que ya existían en la base antes de instalar el
       módulo). No se eliminan físicamente para evitar errores si ya tienen
       algún uso; quedan archivadas y disponibles para borrado manual.

    Atención: el paso 3 se ejecuta cada vez que se corre esta función
    (instalación y asistente de reconfiguración). Si más adelante se agregan
    cuentas manualmente fuera del plan de cuentas de Paraguay, quedarán
    archivadas la próxima vez que se use "Restablecer configuración Paraguay".
    """
    for code in LEGACY_ROOT_GROUP_CODES:
        group = env.ref('local_py.account_group_%s' % code, raise_if_not_found=False)
        if group:
            group.unlink()

    own_account_ids = set(env['ir.model.data'].search([
        ('module', '=', 'local_py'),
        ('model', '=', 'account.account'),
    ]).mapped('res_id'))

    company_accounts = env['account.account'].search([('company_ids', 'in', company.id)])
    own_accounts = company_accounts.filtered(lambda a: a.id in own_account_ids)
    extra_accounts = company_accounts - own_accounts

    pyg = env.ref('base.PYG')
    own_accounts.write({'currency_id': pyg.id})

    if extra_accounts:
        extra_codes = ', '.join(extra_accounts.mapped('code'))
        extra_accounts.write({'active': False})
        _logger.info(
            "local_py: se archivaron %s cuenta(s) preexistente(s) que no forman parte "
            "del plan de cuentas de Paraguay: %s",
            len(extra_accounts), extra_codes,
        )


def _get_account_by_name(env, company, name):
    """Busca una cuenta contable por nombre exacto en la compañía. Si no
    existe todavía (por ejemplo porque el plan de cuentas no se cargó por
    algún motivo), se registra un warning y se continúa sin cuenta."""
    account = env['account.account'].search([
        ('company_ids', 'in', company.id),
        ('name', '=', name),
    ], limit=1)
    if not account:
        _logger.warning(
            "local_py: no se encontró la cuenta contable '%s' en la compañía '%s'. "
            "Los impuestos correspondientes se crearán/actualizarán sin cuenta en sus "
            "líneas de distribución; deberá asignarla manualmente.",
            name, company.name,
        )
    return account


def _repartition_line_vals(document_type, tax_account):
    """Devuelve las 2 líneas de distribución estándar (base + impuesto) para
    un tipo de documento ('invoice' o 'refund'): % 100, Con base en 'de
    impuesto', Cuenta según corresponda (Ventas -> IVA A PAGAR, Compras ->
    IVA - CRÉDITO FISCAL)."""
    return [
        Command.create({
            'document_type': document_type,
            'repartition_type': 'base',
            'factor_percent': 100,
        }),
        Command.create({
            'document_type': document_type,
            'repartition_type': 'tax',
            'factor_percent': 100,
            'account_id': tax_account.id if tax_account else False,
        }),
    ]


def _create_or_update_taxes(env, company, sale_account, purchase_account):
    """Crea o actualiza (si ya existen por xml_id) los 6 impuestos
    predeterminados. Devuelve un dict {xml_id: recordset account.tax}."""
    country_py = env.ref('base.py')
    taxes = {}
    for data in TAXES_DATA:
        xml_id = 'local_py.%s' % data['xml_id']
        tax = env.ref(xml_id, raise_if_not_found=False)
        tax_account = sale_account if data['type_tax_use'] == 'sale' else purchase_account
        vals = {
            'name': data['name'],
            'type_tax_use': data['type_tax_use'],
            'amount_type': 'percent',
            'amount': data['amount'],
            'active': True,
            'company_id': company.id,
            'country_id': country_py.id,
            'tax_group_id': env.ref(data['tax_group_xml_id']).id,
            'price_include_override': 'tax_included',
            'description': data['name'],
            'include_base_amount': data['include_base_amount'],
            'invoice_repartition_line_ids': [Command.clear()] + _repartition_line_vals('invoice', tax_account),
            'refund_repartition_line_ids': [Command.clear()] + _repartition_line_vals('refund', tax_account),
        }
        if tax:
            tax.write(vals)
        else:
            tax = env['account.tax'].create(vals)
            env['ir.model.data'].create({
                'name': data['xml_id'],
                'module': 'local_py',
                'model': 'account.tax',
                'res_id': tax.id,
                'noupdate': True,
            })
        taxes[data['xml_id']] = tax
    _logger.info("local_py: %s impuestos predeterminados configurados.", len(taxes))
    return taxes


def _configure_company(env, company, taxes):
    """Aplica sobre la compañía principal: país, país fiscal, moneda
    principal e impuestos de venta/compra predeterminados."""
    country_py = env.ref('base.py')
    currency_pyg = env.ref('base.PYG')
    company.write({
        'country_id': country_py.id,
        'account_fiscal_country_id': country_py.id,
        'currency_id': currency_pyg.id,
        'account_sale_tax_id': taxes['tax_iva_10_ventas'].id,
        'account_purchase_tax_id': taxes['tax_iva_10_compras'].id,
    })
    _logger.info(
        "local_py: compañía '%s' configurada con país/país fiscal Paraguay, "
        "moneda principal PYG e impuestos de venta/compra predeterminados.",
        company.name,
    )


def configure_paraguay(env):
    """Punto de entrada único de la configuración inicial de Paraguay:
    activa la moneda PYG, crea/actualiza los impuestos predeterminados y
    aplica los ajustes de compañía (país, país fiscal, moneda principal,
    impuestos de venta/compra predeterminados).

    Es seguro invocarla más de una vez (instalación y, manualmente, desde el
    asistente de reconfiguración): busca por xml_id/nombre y actualiza en
    lugar de duplicar.
    """
    company = env.ref('base.main_company')

    currency_pyg = env.ref('base.PYG')
    if not currency_pyg.active:
        currency_pyg.active = True

    _cleanup_chart_of_accounts(env, company)

    sale_account = _get_account_by_name(env, company, TAX_ACCOUNT_SALE_NAME)
    purchase_account = _get_account_by_name(env, company, TAX_ACCOUNT_PURCHASE_NAME)
    taxes = _create_or_update_taxes(env, company, sale_account, purchase_account)
    _configure_company(env, company, taxes)

    env['l10n_py.plan_cuentas.report'].sudo()._rebuild()

    _logger.info("local_py: configuración inicial de Paraguay aplicada correctamente.")


def post_init_hook(env):
    configure_paraguay(env)
