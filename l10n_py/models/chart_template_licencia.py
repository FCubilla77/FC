# -*- coding: utf-8 -*-
import logging

from odoo import models
from odoo.exceptions import UserError

from .l10n_py_licencia import (
    L10N_PY_CODIGO_PAQUETE_FISCAL,
    L10N_PY_LICENCIA_MENSAJE,
    l10n_py_control_activo,
)

_logger = logging.getLogger(__name__)


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    def try_loading(self, template_code, company, install_demo=False, force_create=True):
        """Exige licencia vigente para asignar el paquete fiscal Paraguay ("py").

        `try_loading` es el único punto de entrada público para cargar un paquete
        (Ajustes > Facturación > Localización Fiscal, recarga, instalación del módulo,
        alta de compañías): todos convergen acá. La carga recursiva a las compañías
        hijas la hace `_load` por dentro, así que la licencia se valida una sola vez,
        sobre la compañía recibida, y la cascada nativa a las subsidiarias no cambia.

        Si no hay licencia válida:
          * en una acción explícita (Ajustes, recarga, scripts): UserError con el
            aviso de que falta la licencia;
          * en una carga automática (instalación/actualización del módulo, o alta de
            compañía con país): se omite en silencio, para no impedir instalar el
            módulo ni crear la compañía; el paquete queda sin asignar.
        """
        if company and l10n_py_control_activo(self.env):
            compania = self.env['res.company'].browse(company) if isinstance(company, int) else company
            codigo = template_code or self._guess_chart_template(compania.country_id)
            if codigo == L10N_PY_CODIGO_PAQUETE_FISCAL and not compania._l10n_py_licencia_valida():
                if not self.env.registry.ready or self.env.context.get('l10n_py_licencia_auto'):
                    _logger.info(
                        "l10n_py: no se asigna el paquete fiscal Paraguay en %s "
                        "automáticamente porque falta una licencia válida. Cárguela en "
                        "Ajustes > Configuración l10n_py y luego seleccione el paquete.",
                        compania.display_name)
                    return None
                raise UserError(L10N_PY_LICENCIA_MENSAJE)
        return super().try_loading(
            template_code, company, install_demo=install_demo, force_create=force_create)
