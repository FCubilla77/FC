# -*- coding: utf-8 -*-
import re

from odoo import models, fields, api, exceptions

# Máximo permitido para un campo de 8 dígitos (99.999.999)
TIMBRADO_MAX = 99999999

# Solo se permiten números y el carácter '-'
NRO_DOCUMENTO_PATTERN = re.compile(r'^[0-9-]*$')

# Formato completo exigido para Nro. Documento y Nro. Documento Final del
# Diario (999-999-9999999: Establecimiento-Punto de Expedición-Correlativo) —
# más estricto que NRO_DOCUMENTO_PATTERN, necesario acá porque hace falta
# poder comparar rangos numéricamente. No aplica al Nro. Documento de
# account.move (Factura/NC de Proveedor lo siguen cargando libre).
NRO_DOCUMENTO_FULL_PATTERN = re.compile(r'^(\d{3}-\d{3}-)(\d{7})$')


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    l10n_py_timbrado = fields.Integer(
        string='Timbrado',
        help='Número de timbrado asignado por la SET (hasta 8 dígitos, sin decimales, sin negativos). '
             'Aplica únicamente a diarios de venta.',
    )
    l10n_py_chequera_ids = fields.One2many(
        'local_py.chequera', 'diario_id', string='Chequeras',
        help='Chequeras asociadas a este Diario. Puede haber varias, pero solo una puede '
             'estar Activa a la vez.',
    )
    l10n_py_nro_documento = fields.Char(
        string='Nro. Documento',
        size=15,
        help='Número de documento/resolución, formato completo 999-999-9999999 '
             '(Establecimiento-Punto de Expedición-Correlativo). Aplica únicamente a '
             'diarios de venta. Una vez que el Diario ya tiene Facturas/Notas de '
             'Crédito/Débito o Documentos Anulados registrados, este valor queda '
             'bloqueado (no editable) — evita que el Establecimiento/Punto de '
             'Expedición cambie por debajo de documentos ya existentes.',
    )
    l10n_py_nro_documento_final = fields.Char(
        string='Nro. Documento Final',
        size=15,
        help='Último número del rango de este Timbrado, mismo formato y mismo '
             'Establecimiento-Punto de Expedición que Nro. Documento (solo cambia el '
             'Correlativo). El sistema bloquea la operación cuando la numeración llega '
             'a este límite — hay que habilitar otro Diario para continuar.',
    )
    l10n_py_venc_timbrado = fields.Date(
        string='Venc. Timbrado',
        help='Fecha de vencimiento del timbrado. Las facturas de venta con fecha posterior '
             'a esta no podrán guardarse. Aplica únicamente a diarios de venta.',
    )
    l10n_py_inicio_vigencia_timbrado = fields.Date(
        string='Inicio Vigencia Timbrado',
        help='Fecha desde la cual rige este Timbrado — dato exigido por la DNIT (Tesaka) '
             'para declarar comprobantes electrónicos. Aplica a diarios de venta y al '
             'Diario de Retención.',
    )

    def l10n_py_get_punto_expedicion(self):
        """El Punto de Expedición no se guarda aparte — el formato oficial
        de la DNIT (999-999-9999999) ya lo trae incluido en Nro.
        Documento: dígitos 1-3 = Establecimiento, dígitos 5-7 = Punto de
        Expedición, dígitos 9-15 = Número correlativo. Se extrae de ahí,
        tanto para Facturas/Notas de Crédito/Débito/Remisión como para
        el Diario de Retención."""
        self.ensure_one()
        nro = (self.l10n_py_nro_documento or '')
        partes = nro.split('-')
        return partes[1] if len(partes) >= 2 else ''

    local_py_tipo_fiscal_id = fields.Many2one(
        'local_py.tipo_fiscal',
        string='Tipo Fiscal',
        help='Tipo de comprobante fiscal asociado a este diario. Aplica a diarios de venta y de compra.',
    )

    # ------------------------------------------------------------------
    # Numeración: helpers reutilizables (pensados para que, el día que exista
    # Remisión como funcionalidad, pueda reusar exactamente esta misma lógica
    # sin importar en qué modelo termine viviendo, en vez de duplicarla).
    # ------------------------------------------------------------------
    @staticmethod
    def _l10n_py_correlativo(value):
        """Extrae el Correlativo (últimos 7 dígitos) de un Nro. Documento en
        formato completo, como entero — o None si no tiene ese formato."""
        match = NRO_DOCUMENTO_FULL_PATTERN.match(value or '')
        return int(match.group(2)) if match else None

    @staticmethod
    def _l10n_py_incrementar_nro_documento(value):
        """Incrementa en 1 solo el Correlativo (últimos 7 dígitos), manteniendo
        intacto el Establecimiento-Punto de Expedición."""
        match = NRO_DOCUMENTO_FULL_PATTERN.match(value or '')
        if not match:
            return value
        prefix, seq = match.groups()
        return '%s%07d' % (prefix, int(seq) + 1)

    def l10n_py_correlativo_maximo_usado(self):
        """Correlativo más alto entre las Facturas/Notas de Crédito/Débito ya
        creadas en este Diario (cualquier estado, incluido Borrador, ya que el
        número se reserva desde que se crea el comprobante) — o None si
        todavía no hay ninguna."""
        self.ensure_one()
        ultimo_move = self.env['account.move'].search([
            ('journal_id', '=', self.id),
            ('l10n_py_nro_documento', '!=', False),
        ], order='id desc', limit=1)
        return self._l10n_py_correlativo(ultimo_move.l10n_py_nro_documento) if ultimo_move else None

    def l10n_py_correlativo_maximo_registrado(self):
        """Igual que l10n_py_correlativo_maximo_usado, pero además considera los
        Documentos Anulados registrados para este Diario — usado para no poder
        bajar el Nro. Documento Final por debajo de ninguno de los dos."""
        self.ensure_one()
        maximo = self.l10n_py_correlativo_maximo_usado()
        anulados = self.env['local_py.documento_anulado'].search([('diario_id', '=', self.id)])
        for correlativo in anulados.mapped(lambda a: self._l10n_py_correlativo(a.numero)):
            if correlativo is not None and (maximo is None or correlativo > maximo):
                maximo = correlativo
        return maximo

    def l10n_py_siguiente_numero_disponible(self):
        """Calcula el próximo Nro. Documento a proponer para este Diario:
        parte del Correlativo siguiente al de la última Factura/NC/ND ya
        creada (o el Nro. Documento configurado, si todavía no hay ninguna),
        y salta los que estén registrados en Documentos Anulados — validando
        en cada salto que no se pase del Nro. Documento Final."""
        self.ensure_one()
        ultimo_move = self.env['account.move'].search([
            ('journal_id', '=', self.id),
            ('l10n_py_nro_documento', '!=', False),
        ], order='id desc', limit=1)
        candidato = (
            self._l10n_py_incrementar_nro_documento(ultimo_move.l10n_py_nro_documento)
            if ultimo_move else self.l10n_py_nro_documento
        )
        if not candidato:
            return candidato

        anulados = set(self.env['local_py.documento_anulado'].search([
            ('diario_id', '=', self.id),
        ]).mapped('numero'))

        intentos = 0
        while candidato in anulados:
            candidato = self._l10n_py_incrementar_nro_documento(candidato)
            intentos += 1
            if intentos > 100000:
                raise exceptions.UserError(
                    'No se pudo calcular el próximo Nro. Documento disponible para el '
                    'Diario "%s" — revise los Documentos Anulados registrados.' % self.name
                )

        self._l10n_py_controlar_limite(candidato)
        return candidato

    def _l10n_py_controlar_limite(self, candidato):
        self.ensure_one()
        if not self.l10n_py_nro_documento_final or not candidato:
            return
        correlativo_candidato = self._l10n_py_correlativo(candidato)
        correlativo_final = self._l10n_py_correlativo(self.l10n_py_nro_documento_final)
        if correlativo_candidato is not None and correlativo_final is not None and correlativo_candidato > correlativo_final:
            raise exceptions.UserError(
                'El Diario "%s" alcanzó su Nro. Documento Final (%s) — habilite otro '
                'Diario para continuar facturando con este Tipo Fiscal.'
                % (self.name, self.l10n_py_nro_documento_final)
            )

    def l10n_py_verificar_dentro_de_rango(self, numero):
        """Valida que 'numero' comparta Establecimiento-Punto de Expedición con
        este Diario y caiga dentro de [Nro. Documento, Nro. Documento Final] —
        usado por local_py.documento_anulado. Lanza ValidationError si no."""
        self.ensure_one()
        if not self.l10n_py_nro_documento or not self.l10n_py_nro_documento_final:
            raise exceptions.ValidationError(
                'El Diario "%s" no tiene configurado Nro. Documento y Nro. Documento '
                'Final — complete esos datos antes de registrar Documentos Anulados '
                'para este Diario.' % self.name
            )
        correlativo = self._l10n_py_correlativo(numero)
        if correlativo is None:
            raise exceptions.ValidationError(
                'El Número tiene que tener el formato completo 999-999-9999999.'
            )
        if numero[:7] != self.l10n_py_nro_documento[:7]:
            raise exceptions.ValidationError(
                'El Número tiene que compartir el mismo Establecimiento y Punto de '
                'Expedición que el Diario "%s" (%s).' % (self.name, self.l10n_py_nro_documento[:7])
            )
        correlativo_inicial = self._l10n_py_correlativo(self.l10n_py_nro_documento)
        correlativo_final = self._l10n_py_correlativo(self.l10n_py_nro_documento_final)
        if not (correlativo_inicial <= correlativo <= correlativo_final):
            raise exceptions.ValidationError(
                'El Número %s está fuera del rango configurado en el Diario "%s" (%s a %s).'
                % (numero, self.name, self.l10n_py_nro_documento, self.l10n_py_nro_documento_final)
            )

    def _l10n_py_tiene_documentos_registrados(self):
        self.ensure_one()
        if self.env['account.move'].search_count([
            ('journal_id', '=', self.id), ('l10n_py_nro_documento', '!=', False),
        ]):
            return True
        return bool(self.env['local_py.documento_anulado'].search_count([('diario_id', '=', self.id)]))

    def write(self, vals):
        if 'l10n_py_nro_documento' in vals:
            for journal in self:
                if vals['l10n_py_nro_documento'] != journal.l10n_py_nro_documento \
                        and journal._l10n_py_tiene_documentos_registrados():
                    raise exceptions.UserError(
                        'No se puede modificar el Nro. Documento del Diario "%s": ya tiene '
                        'Facturas/Notas de Crédito/Débito o Documentos Anulados '
                        'registrados.' % journal.name
                    )
        if 'l10n_py_nro_documento_final' in vals and vals['l10n_py_nro_documento_final']:
            nuevo_correlativo = self._l10n_py_correlativo(vals['l10n_py_nro_documento_final'])
            if nuevo_correlativo is not None:
                for journal in self:
                    tope = journal.l10n_py_correlativo_maximo_registrado()
                    if tope is not None and nuevo_correlativo < tope:
                        raise exceptions.UserError(
                            'No se puede bajar el Nro. Documento Final del Diario "%s" por '
                            'debajo del número más alto ya usado o registrado como Anulado '
                            '(Correlativo %07d).' % (journal.name, tope)
                        )
        return super().write(vals)

    # ------------------------------------------------------------------
    # Validaciones
    # ------------------------------------------------------------------
    @api.constrains('l10n_py_timbrado')
    def _check_l10n_py_timbrado(self):
        for journal in self:
            if journal.l10n_py_timbrado and journal.l10n_py_timbrado < 0:
                raise exceptions.ValidationError(
                    'El campo Timbrado no admite valores negativos.'
                )
            if journal.l10n_py_timbrado and journal.l10n_py_timbrado > TIMBRADO_MAX:
                raise exceptions.ValidationError(
                    'El campo Timbrado admite un máximo de 8 dígitos.'
                )

    @api.constrains('l10n_py_nro_documento')
    def _check_l10n_py_nro_documento(self):
        for journal in self:
            if journal.l10n_py_nro_documento and not NRO_DOCUMENTO_PATTERN.match(journal.l10n_py_nro_documento):
                raise exceptions.ValidationError(
                    'El campo Nro. Documento solo admite números y el carácter "-".'
                )

    @api.constrains('l10n_py_nro_documento', 'l10n_py_nro_documento_final')
    def _check_l10n_py_nro_documento_formato_completo(self):
        for journal in self:
            if journal.l10n_py_nro_documento and not NRO_DOCUMENTO_FULL_PATTERN.match(journal.l10n_py_nro_documento):
                raise exceptions.ValidationError(
                    'El campo Nro. Documento tiene que tener el formato completo '
                    '999-999-9999999 (Establecimiento-Punto de Expedición-Correlativo).'
                )
            if journal.l10n_py_nro_documento_final and not NRO_DOCUMENTO_FULL_PATTERN.match(journal.l10n_py_nro_documento_final):
                raise exceptions.ValidationError(
                    'El campo Nro. Documento Final tiene que tener el formato completo '
                    '999-999-9999999 (Establecimiento-Punto de Expedición-Correlativo).'
                )

    @api.constrains('l10n_py_nro_documento', 'l10n_py_nro_documento_final')
    def _check_l10n_py_nro_documento_final_coherente(self):
        for journal in self:
            if journal.l10n_py_nro_documento_final:
                if not journal.l10n_py_nro_documento:
                    raise exceptions.ValidationError(
                        'No se puede cargar Nro. Documento Final sin haber cargado antes '
                        'Nro. Documento.'
                    )
                if journal.l10n_py_nro_documento[:7] != journal.l10n_py_nro_documento_final[:7]:
                    raise exceptions.ValidationError(
                        'Nro. Documento y Nro. Documento Final tienen que compartir el mismo '
                        'Establecimiento y Punto de Expedición (los primeros 6 dígitos).'
                    )
                correlativo_inicial = journal._l10n_py_correlativo(journal.l10n_py_nro_documento)
                correlativo_final = journal._l10n_py_correlativo(journal.l10n_py_nro_documento_final)
                if correlativo_inicial is not None and correlativo_final is not None \
                        and correlativo_final < correlativo_inicial:
                    raise exceptions.ValidationError(
                        'Nro. Documento Final tiene que ser mayor o igual a Nro. Documento.'
                    )

    @api.constrains('type', 'local_py_tipo_fiscal_id', 'l10n_py_timbrado', 'l10n_py_nro_documento',
                     'l10n_py_nro_documento_final', 'l10n_py_venc_timbrado', 'l10n_py_inicio_vigencia_timbrado')
    def _check_l10n_py_configuracion_completa(self):
        """Con Tipo Fiscal configurado en un Diario de venta, no puede quedar
        ningún otro dato de la numeración sin completar — evita quedar a
        mitad de configurar (ej. con Nro. Documento pero sin Timbrado)."""
        for journal in self:
            if journal.type == 'sale' and journal.local_py_tipo_fiscal_id:
                faltantes = []
                if not journal.l10n_py_timbrado:
                    faltantes.append('Timbrado')
                if not journal.l10n_py_nro_documento:
                    faltantes.append('Nro. Documento')
                if not journal.l10n_py_nro_documento_final:
                    faltantes.append('Nro. Documento Final')
                if not journal.l10n_py_venc_timbrado:
                    faltantes.append('Venc. Timbrado')
                if not journal.l10n_py_inicio_vigencia_timbrado:
                    faltantes.append('Inicio Vigencia Timbrado')
                if faltantes:
                    raise exceptions.ValidationError(
                        'Con Tipo Fiscal configurado, este Diario necesita completar '
                        'también: %s.' % ', '.join(faltantes)
                    )

    @api.constrains('l10n_py_timbrado', 'l10n_py_nro_documento', 'l10n_py_venc_timbrado', 'l10n_py_nro_documento_final', 'type')
    def _check_l10n_py_only_sale_journal(self):
        for journal in self:
            if journal.type not in ('sale', 'general') and (
                journal.l10n_py_timbrado
                or journal.l10n_py_nro_documento
                or journal.l10n_py_venc_timbrado
                or journal.l10n_py_nro_documento_final
            ):
                raise exceptions.ValidationError(
                    'Los campos Timbrado, Nro. Documento, Nro. Documento Final y Venc. '
                    'Timbrado solo aplican a diarios de venta (o al Diario de Retención, '
                    'de tipo Misceláneo).'
                )

    @api.constrains('local_py_tipo_fiscal_id', 'type')
    def _check_local_py_tipo_fiscal_journal_type(self):
        for journal in self:
            if journal.type not in ('sale', 'purchase') and journal.local_py_tipo_fiscal_id:
                raise exceptions.ValidationError(
                    'El campo Tipo Fiscal solo aplica a diarios de venta y de compra.'
                )

    @api.constrains('l10n_py_timbrado', 'l10n_py_nro_documento', 'local_py_tipo_fiscal_id', 'type')
    def _check_l10n_py_unique_timbrado_per_tipo_fiscal(self):
        """No pueden existir dos diarios de venta con el mismo Tipo Fiscal que
        compartan el mismo Timbrado y Nro. Documento. Al comparar siempre
        contra el mismo Tipo Fiscal, la validación queda naturalmente separada
        por cada tipo (Factura, Factura Electronica, Nota de Debito,
        Nota de Credito, Autofactura, o cualquier otro que se agregue)."""
        for journal in self:
            if (
                journal.type == 'sale'
                and journal.local_py_tipo_fiscal_id
                and journal.l10n_py_timbrado
                and journal.l10n_py_nro_documento
            ):
                domain = [
                    ('id', '!=', journal.id),
                    ('type', '=', 'sale'),
                    ('local_py_tipo_fiscal_id', '=', journal.local_py_tipo_fiscal_id.id),
                    ('l10n_py_timbrado', '=', journal.l10n_py_timbrado),
                    ('l10n_py_nro_documento', '=', journal.l10n_py_nro_documento),
                    ('company_id', '=', journal.company_id.id),
                ]
                if self.search_count(domain):
                    raise exceptions.ValidationError(
                        'Ya existe otro diario de venta con el mismo Tipo Fiscal (%s), '
                        'Timbrado y Nro. Documento.' % journal.local_py_tipo_fiscal_id.name
                    )
