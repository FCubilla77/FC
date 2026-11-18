# -*- coding: utf-8 -*-
"""Campos que FE_Py agrega al Diario.

El Tipo de Documento Electrónico es lo que decide si un Diario emite
electrónicamente. Es un dato propio de FE_Py y no se lee de ninguna
localización: el código iTiDE que exige SIFEN no coincide con ninguna
tabla de Marangatu, así que no existe en otro módulo.

El resto de la configuración fiscal del Diario —timbrado, rango de
numeración, vigencia— NO se duplica acá: ya vive en la localización que
el cliente tenga instalada, y FE_Py la lee a través del Mapeo de Datos.
"""

from odoo import _, api, exceptions, fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    fe_py_tipo_documento_id = fields.Many2one(
        'fe_py.tipo_documento', string='Tipo de Documento Electrónico (SIFEN)',
        ondelete='restrict', tracking=True,
        help='Define qué tipo de Documento Electrónico emite este Diario '
             '(iTiDE del XML). Elegir "No aplica" en los Diarios de '
             'timbrado físico — dejarlo vacío significa que todavía no se '
             'configuró, no que sea no electrónico.\n\n'
             'Es independiente del Tipo de Documento Fiscal de la '
             'localización, que clasifica el mismo comprobante para '
             'Marangatu con otra tabla de códigos.',
    )
    fe_py_es_electronico = fields.Boolean(
        string='Emite Documentos Electrónicos',
        compute='_compute_fe_py_es_electronico', store=True,
        help='Calculado a partir del Tipo de Documento Electrónico. No se '
             'edita: así no puede contradecir al tipo elegido.',
    )

    @api.depends('fe_py_tipo_documento_id',
                 'fe_py_tipo_documento_id.es_electronico')
    def _compute_fe_py_es_electronico(self):
        for journal in self:
            journal.fe_py_es_electronico = bool(
                journal.fe_py_tipo_documento_id
                and journal.fe_py_tipo_documento_id.es_electronico
            )

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
        idcsc = self.fe_py_idcsc or config.idcsc
        csc = self.fe_py_csc or config.csc
        return idcsc, csc

    # ------------------------------------------------------------------
    # Numeración de los Diarios electrónicos
    #
    # FE_Py numera SOLO los Diarios que emiten Documentos Electrónicos, y
    # salta los números de su propia tabla de Documentos Anulados. Los
    # Diarios de timbrado físico los numera la localización, con su propia
    # tabla. Ninguno de los dos procedimientos consulta al otro.
    #
    # El timbrado y el rango no son datos de FE_Py: se leen por el Mapeo
    # de Datos, del campo que tenga la localización instalada.
    # ------------------------------------------------------------------
    @api.model
    def _fe_py_correlativo(self, numero):
        """Parte correlativa de un número 001-001-0000001, o None."""
        partes = (numero or '').split('-')
        if len(partes) != 3 or not partes[2].isdigit():
            return None
        return int(partes[2])

    @api.model
    def _fe_py_incrementar(self, numero):
        """Número siguiente, conservando Establecimiento y Punto."""
        correlativo = self._fe_py_correlativo(numero)
        if correlativo is None:
            return False
        return '%s%07d' % (numero[:8], correlativo + 1)

    def _fe_py_correlativo_maximo_usado(self):
        """Mayor correlativo ya asignado a un comprobante de este Diario,
        o None si todavía no hay ninguno."""
        self.ensure_one()
        campo = self.env['fe_py.mapeo']._mapa().get('move_nro_documento')
        if not campo or campo not in self.env['account.move']._fields:
            return None
        moves = self.env['account.move'].sudo().search([
            ('journal_id', '=', self.id), (campo, '!=', False),
        ])
        correlativos = [c for c in (self._fe_py_correlativo(m[campo]) for m in moves)
                        if c is not None]
        return max(correlativos) if correlativos else None

    def fe_py_siguiente_numero_disponible(self):
        """Próximo número a usar en este Diario electrónico.

        Parte del siguiente al último comprobante emitido (o del inicio del
        rango, si no hay ninguno) y saltea los que estén en Documentos
        Anulados. Devuelve False si el Diario no es electrónico o si falta
        el mapeo del rango — el aviso al usuario lo da quien llama.
        """
        self.ensure_one()
        if not self.fe_py_es_electronico:
            return False
        Mapeo = self.env['fe_py.mapeo']
        mapa = Mapeo._mapa()
        inicio = Mapeo._leer(self, 'journal_nro_documento', mapa)
        if not inicio:
            return False

        maximo = self._fe_py_correlativo_maximo_usado()
        candidato = ('%s%07d' % (inicio[:8], maximo + 1)) if maximo is not None else inicio

        anulados = set(self.env['fe_py.documento_anulado'].sudo().search([
            ('journal_id', '=', self.id),
        ]).mapped('numero'))

        final = Mapeo._leer(self, 'journal_nro_documento_final', mapa)
        tope = self._fe_py_correlativo(final) if final else None

        intentos = 0
        while candidato in anulados:
            candidato = self._fe_py_incrementar(candidato)
            intentos += 1
            if not candidato or intentos > 100000:
                raise exceptions.UserError(_(
                    'No se pudo calcular el próximo número disponible para el '
                    'Diario "%s" — revise los Documentos Anulados registrados.',
                    self.name))
        if tope is not None and (self._fe_py_correlativo(candidato) or 0) > tope:
            raise exceptions.UserError(_(
                'El Diario "%(diario)s" agotó su rango de numeración: el '
                'próximo número disponible (%(numero)s) supera el Nro. '
                'Documento final autorizado (%(final)s).',
                diario=self.name, numero=candidato, final=final))
        return candidato
