# -*- coding: utf-8 -*-
import logging

from odoo.fields import Command

_logger = logging.getLogger(__name__)

# Nombre de la cuenta contable a utilizar en las líneas de distribución de los
# impuestos. Se busca por nombre porque el plan de cuentas no es parte de este
# módulo (se instala aparte); si no se encuentra, los impuestos se crean
# igual, pero sin cuenta asignada en sus líneas de distribución.
TAX_ACCOUNT_NAME = 'Impuesto recibido'

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


def _get_tax_account(env, company):
    """Busca la cuenta contable 'Impuesto recibido' en el plan de cuentas de
    la compañía. Si no existe todavía (por ejemplo porque aún no se cargó un
    plan de cuentas de Paraguay), se registra un warning y se continúa: los
    impuestos se crean igual, pero sin cuenta en sus líneas de distribución.
    """
    account = env['account.account'].search([
        ('company_ids', 'in', company.id),
        ('name', '=', TAX_ACCOUNT_NAME),
    ], limit=1)
    if not account:
        _logger.warning(
            "local_py: no se encontró la cuenta contable '%s' en la compañía '%s'. "
            "Los 6 impuestos predeterminados se crearán/actualizarán sin cuenta en sus "
            "líneas de distribución; deberá asignarla manualmente cuando el plan de "
            "cuentas esté disponible.",
            TAX_ACCOUNT_NAME, company.name,
        )
    return account


def _repartition_line_vals(document_type, tax_account):
    """Devuelve las 2 líneas de distribución estándar (base + impuesto) para
    un tipo de documento ('invoice' o 'refund'), según el Requerimiento 001:
    % 100, Con base en 'de impuesto', Cuenta 'Impuesto recibido'."""
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


def _create_or_update_taxes(env, company, tax_account):
    """Crea o actualiza (si ya existen por xml_id) los 6 impuestos
    predeterminados. Devuelve un dict {xml_id: recordset account.tax}."""
    country_py = env.ref('base.py')
    taxes = {}
    for data in TAXES_DATA:
        xml_id = 'local_py.%s' % data['xml_id']
        tax = env.ref(xml_id, raise_if_not_found=False)
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

    tax_account = _get_tax_account(env, company)
    taxes = _create_or_update_taxes(env, company, tax_account)
    _configure_company(env, company, taxes)

    _logger.info("local_py: configuración inicial de Paraguay aplicada correctamente.")


def post_init_hook(env):
    configure_paraguay(env)
