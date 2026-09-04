# -*- coding: utf-8 -*-

from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    fe_py_idcsc = fields.Char(
        string='IdCSC (Diario)',
        help='Si este Diario/Punto de Expedición tiene un IdCSC propio '
             'asignado por la DNIT, indicarlo acá — sobreescribe el de la '
             'Compañía solo para los comprobantes de este Diario. Dejar '
             'vacío para usar el de la Compañía.',
    )
    fe_py_csc = fields.Char(string='CSC (Diario)')

    def fe_py_get_idcsc_csc(self):
        """Devuelve (idcsc, csc) efectivos para este Diario: los propios si
        están cargados, o los de la Compañía como valor por defecto."""
        self.ensure_one()
        config = self.env['fe_py.configuracion']._get_config(self.company_id)
        idcsc = self.fe_py_idcsc or config.fe_py_idcsc
        csc = self.fe_py_csc or config.fe_py_csc
        return idcsc, csc
