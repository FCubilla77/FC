# -*- coding: utf-8 -*-
import json

from odoo import models
from odoo.addons.account.models.chart_template import template

from . import plantilla_excel as excel


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    def _l10n_py_datos_plantilla(self):
        """Datos del plan del cliente si la compañía que se está cargando (o su
        compañía principal) eligió «Plan del cliente» y tiene una plantilla validada;
        None si se carga el plan estándar."""
        company = self.env.company.root_id
        if company.l10n_py_modo_plan != 'plantilla':
            return None
        plantilla = company.l10n_py_plantilla_id
        if not plantilla or plantilla.state == 'error':
            return None
        return json.loads(plantilla.datos) if plantilla.datos else None

    def _parse_csv(self, template_code, model, module=None):
        """Punto único por el que Odoo lee cuentas, grupos, impuestos, posiciones fiscales
        (y, desde la 018, plazos de pago): si la compañía usa el plan del cliente, los
        datos salen de la plantilla Excel en lugar de los CSV del módulo."""
        if template_code == 'py' and module in (None, 'l10n_py'):
            datos = self._l10n_py_datos_plantilla()
            if datos is not None:
                return excel.registros_odoo(datos).get(model, {})
        return super()._parse_csv(template_code, model, module=module)

    @template('py', 'account.payment.term')
    def _get_py_account_payment_term(self):
        return self._parse_csv('py', 'account.payment.term')

    def _post_load_data(self, template_code, company, template_data):
        res = super()._post_load_data(template_code, company, template_data)
        if template_code == 'py':
            raiz = company.root_id
            if raiz.l10n_py_modo_plan == 'plantilla' and raiz.l10n_py_plantilla_id.state == 'validada':
                raiz.l10n_py_plantilla_id.sudo().state = 'cargada'
        return res
