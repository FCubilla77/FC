# -*- coding: utf-8 -*-
from odoo import api, models
from odoo.exceptions import ValidationError


class TllrFcOtHora(models.Model):
    _inherit = 'tllr_fc.ot.hora'

    @api.constrains('servicio_id')
    def _check_servicio_no_tercerizado(self):
        for hora in self:
            if hora.servicio_id.tercerizado:
                raise ValidationError(
                    "El servicio «%s» es tercerizado: no suma horas ni mano de obra."
                    % hora.servicio_id.display_name)
