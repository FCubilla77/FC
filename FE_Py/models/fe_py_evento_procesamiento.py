# -*- coding: utf-8 -*-
"""Cancelación e Inutilización: arma el XML del evento, lo firma
(certificado propio de la Compañía) y lo envía al WS Sincrónico de Eventos
de SIFEN (siRecepEvento) — real (Test/Producción) o Simulado, mismo
criterio que la Fase 5.

ALCANCE / LIMITACIONES:
  - Solo Cancelación e Inutilización (eventos de Emisor). Los eventos de
    Receptor (Conformidad, Disconformidad, Desconocimiento, Notificación)
    quedan fuera de alcance -- ademas, el propio Manual Tecnico los marca
    como "(futuro)" en la tabla de tipos de evento (dTiGDE 10-13).
  - "Aprobado con Observación" no aplica como estado propio de
    fe_py.evento (a diferencia de fe_py.documento_electronico) -- la
    respuesta de SIFEN para eventos ya viene en texto plano
    ("Aprobado"/"Aprobado con observación"/"Rechazado"); acá se simplifica
    cualquier variante de "Aprobado..." a estado Aprobado, guardando el
    texto completo en mensaje_respuesta para no perder el detalle.
"""
import logging

from lxml import etree

from odoo import exceptions, fields, models

from .fe_py_documento_electronico_xml import TIDE_POR_TIPO_FISCAL

_logger = logging.getLogger(__name__)

try:
    import signxml
    from signxml import XMLSigner, XMLVerifier
except Exception:  # pragma: no cover
    signxml = None
    XMLSigner = None
    XMLVerifier = None

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

SIFEN_NS = 'http://ekuatia.set.gov.py/sifen/xsd'
SOAP_NS = 'http://www.w3.org/2003/05/soap-envelope'
C14N_ALGORITHM = 'http://www.w3.org/2001/10/xml-exc-c14n#'

WS_EVENTOS_URLS = {
    'test': 'https://sifen-test.set.gov.py/de/ws/eventos/evento.wsdl',
    'produccion': 'https://sifen.set.gov.py/de/ws/eventos/evento.wsdl',
}

TIMEOUT_SEGUNDOS = 30


def _sub(parent, tag, value):
    if value is None or value == '':
        return None
    el = etree.SubElement(parent, '{%s}%s' % (SIFEN_NS, tag))
    el.text = str(value)
    return el


class FePyEvento(models.Model):
    _inherit = 'fe_py.evento'

    estado = fields.Selection(
        selection_add=[('error_comunicacion', 'Error de Comunicación')],
        ondelete={'error_comunicacion': 'set default'},
    )

    xml_generado = fields.Text(string='XML Generado', copy=False)
    xml_firmado = fields.Text(string='XML Firmado', copy=False)

    simular_resultado = fields.Selection(
        string='Resultado a Simular',
        selection=[
            ('aprobado', 'Aprobado'),
            ('rechazado', 'Rechazado'),
            ('error_comunicacion', 'Error de Comunicación'),
        ],
        default='aprobado',
        help='Solo tiene efecto con Ambiente = Simulado.',
    )
    simular_codigo_rechazo = fields.Char(string='Código a Simular (Rechazo)', default='4000')
    fe_py_ambiente = fields.Selection(related='company_id.fe_py_ambiente', string='Ambiente FE')
    simular_mensaje_rechazo = fields.Char(
        string='Mensaje a Simular (Rechazo)', default='Motivo del Evento inválido',
    )

    def action_enviar(self):
        for evento in self:
            if evento.estado not in ('borrador', 'error_comunicacion', 'rechazado'):
                raise exceptions.UserError(
                    'No se puede enviar: el Evento está en estado "%s". Solo '
                    'se puede enviar desde Borrador, o reintentar desde '
                    'Rechazado o Error de Comunicación.'
                    % dict(evento._fields['estado'].selection).get(evento.estado)
                )
            evento._fe_py_procesar_evento()
        return True

    def _fe_py_procesar_evento(self):
        self.ensure_one()
        if self.tipo_evento == 'cancelacion':
            self._fe_py_validar_cancelacion()
        else:
            self._fe_py_validar_inutilizacion()
            # Se reserva el rango en local_py ANTES de tocar SIFEN — así
            # ningún otro comprobante puede tomar esos números mientras el
            # evento está en trámite (no recién cuando SIFEN aprueba).
            self._fe_py_registrar_documentos_anulados()

        company = self.company_id
        xml_root = self._fe_py_construir_xml_evento()
        self.xml_generado = etree.tostring(
            xml_root, pretty_print=True, xml_declaration=True, encoding='UTF-8'
        ).decode('utf-8')

        signed_root = self._fe_py_firmar_evento(xml_root, company)
        self.xml_firmado = etree.tostring(
            signed_root, pretty_print=True, xml_declaration=True, encoding='UTF-8'
        ).decode('utf-8')

        soap_request = self._fe_py_construir_soap_evento(signed_root)
        self.write({'estado': 'enviado', 'fecha_envio': fields.Datetime.now()})

        ambiente = company.fe_py_ambiente
        simulado = ambiente == 'simulado'
        try:
            if simulado:
                resultado = self._fe_py_simular_respuesta_evento()
                response_payload = 'Respuesta simulada: %s' % resultado
            elif ambiente in ('test', 'produccion'):
                response_xml = self._fe_py_llamar_ws_eventos(soap_request, ambiente, company)
                resultado = self._fe_py_parsear_respuesta_evento(response_xml)
                response_payload = response_xml
            else:
                raise exceptions.UserError('Ambiente FE no configurado en la Compañía.')
        except exceptions.UserError:
            raise
        except Exception as ex:
            self.write({'estado': 'error_comunicacion'})
            self.env['fe_py.documento_electronico.log'].sudo().create({
                'evento_id': self.id,
                'tipo_operacion': (
                    'evento_cancelacion' if self.tipo_evento == 'cancelacion' else 'evento_inutilizacion'
                ),
                'resultado': 'error',
                'mensaje_resultado': 'Error de comunicación: %s' % ex,
                'request_payload': soap_request,
                'simulado': simulado,
            })
            return

        nuevo_estado = resultado.get('estado', 'rechazado')
        self.write({
            'estado': nuevo_estado,
            'codigo_respuesta': resultado.get('codigo_respuesta'),
            'mensaje_respuesta': resultado.get('mensaje_respuesta'),
            'fecha_respuesta': fields.Datetime.now(),
        })
        self.env['fe_py.documento_electronico.log'].sudo().create({
            'evento_id': self.id,
            'tipo_operacion': (
                'evento_cancelacion' if self.tipo_evento == 'cancelacion' else 'evento_inutilizacion'
            ),
            'resultado': 'exito' if nuevo_estado == 'aprobado' else 'error',
            'codigo_resultado': resultado.get('codigo_respuesta'),
            'mensaje_resultado': resultado.get('mensaje_respuesta'),
            'request_payload': soap_request,
            'response_payload': response_payload,
            'simulado': simulado,
        })

        if self.tipo_evento == 'cancelacion' and nuevo_estado == 'aprobado' and self.documento_id:
            self.documento_id.write({'estado': 'cancelado'})

        if self.tipo_evento == 'inutilizacion' and nuevo_estado == 'rechazado':
            # Error de Comunicación NO libera (no se sabe si SIFEN llegó a
            # procesarlo) — pero un Rechazo sí es una respuesta definitiva,
            # así que corresponde intentar liberar los números reservados.
            self._fe_py_liberar_documentos_anulados_si_corresponde()

    def _fe_py_validar_cancelacion(self):
        self.ensure_one()
        if not self.documento_id.cdc:
            raise exceptions.UserError(
                'El Documento Electrónico a cancelar todavía no tiene CDC asignado.'
            )
        if self.documento_id.estado != 'aprobado':
            raise exceptions.UserError(
                'Solo se puede Cancelar un Documento Electrónico que esté '
                'Aprobado (estado actual: %s).'
                % dict(self.documento_id._fields['estado'].selection).get(self.documento_id.estado)
            )

    def _fe_py_validar_inutilizacion(self):
        self.ensure_one()
        if not self.journal_id.local_py_tipo_fiscal_id.fe_py_es_electronico:
            raise exceptions.UserError(
                'El Diario "%s" no tiene un Tipo Fiscal electrónico — los '
                'Eventos SIFEN solo aplican a diarios electrónicos.'
                % self.journal_id.name
            )
        partes_desde = (self.nro_documento_desde or '').split('-')
        partes_hasta = (self.nro_documento_hasta or '').split('-')
        if len(partes_desde) != 3 or len(partes_hasta) != 3:
            raise exceptions.UserError(
                'Nro. Documento Desde/Hasta deben tener el formato 999-999-9999999.'
            )
        if partes_desde[0:2] != partes_hasta[0:2]:
            raise exceptions.UserError(
                'Establecimiento y Punto de Expedición deben coincidir entre '
                'Nro. Documento Desde y Hasta.'
            )
        if not (partes_desde[2].isdigit() and partes_hasta[2].isdigit()):
            raise exceptions.UserError('El correlativo de Nro. Documento debe ser numérico.')
        if int(partes_desde[2]) > int(partes_hasta[2]):
            raise exceptions.UserError('Nro. Documento Desde no puede ser mayor que Hasta.')
        if int(partes_hasta[2]) - int(partes_desde[2]) + 1 > 1000:
            raise exceptions.UserError(
                'El rango a inutilizar no puede superar 1000 números (límite de SIFEN).'
            )
        if not self.journal_id.l10n_py_timbrado:
            raise exceptions.UserError('El Diario no tiene Timbrado configurado.')
        if self.tipo_fiscal_id.name not in TIDE_POR_TIPO_FISCAL:
            raise exceptions.UserError(
                'El Tipo Fiscal "%s" no está soportado todavía para Inutilización.'
                % (self.tipo_fiscal_id.name or '(vacío)')
            )

    # ------------------------------------------------------------------
    # Integración con local_py.documento_anulado — reserva el rango antes
    # de tocar SIFEN, para que la numeración de Factura/NC/ND no vuelva a
    # ofrecer esos números mientras el evento está en trámite.
    # ------------------------------------------------------------------
    def _fe_py_generar_numeros_rango(self):
        """Lista de números completos (999-999-9999999) del rango Desde-
        Hasta — mismo criterio de armado que ya usa el wizard nativo de
        local_py (Registrar por Rango), para que el formato sea idéntico."""
        self.ensure_one()
        correlativo_desde = int(self.nro_documento_desde.split('-')[2])
        correlativo_hasta = int(self.nro_documento_hasta.split('-')[2])
        prefijo = self.nro_documento_desde[:8]
        return ['%s%07d' % (prefijo, c) for c in range(correlativo_desde, correlativo_hasta + 1)]

    def _fe_py_registrar_documentos_anulados(self):
        """Reserva cada número del rango en local_py.documento_anulado. Si
        algún número ya fue usado en una Factura/NC/ND real, local_py lo
        rechaza acá mismo (con su propio mensaje) — antes de gastar un
        envío real contra SIFEN. Si ya estaban registrados por un intento
        anterior de este mismo evento (reintento tras Error de
        Comunicación), no vuelve a crearlos ni falla por duplicado."""
        self.ensure_one()
        numeros = self._fe_py_generar_numeros_rango()
        ya_existentes = self.env['local_py.documento_anulado'].search([
            ('diario_id', '=', self.journal_id.id),
            ('numero', 'in', numeros),
        ])
        numeros_faltantes = set(numeros) - set(ya_existentes.mapped('numero'))
        if not numeros_faltantes:
            return
        vals_list = [{
            'diario_id': self.journal_id.id,
            'timbrado': self.journal_id.l10n_py_timbrado,
            'numero': numero,
            'tipo_fiscal_id': self.tipo_fiscal_id.id,
            'motivo': 'Inutilización SIFEN (Evento #%s) — %s' % (self.id, self.motivo),
            'fecha_registro': fields.Date.context_today(self),
            'fe_py_evento_id': self.id,
        } for numero in sorted(numeros_faltantes)]
        self.env['local_py.documento_anulado'].sudo().create(vals_list)

    def _fe_py_liberar_documentos_anulados_si_corresponde(self):
        """Tras un Rechazo de SIFEN, intenta liberar los números reservados
        por ESTE evento. local_py bloquea el unlink() de un Documento
        Anulado si la numeración real del Diario ya lo superó (liberarlo
        dejaría un hueco que no se puede volver a llenar) — en ese caso
        queda reservado tal cual, a la espera de corregir el motivo del
        rechazo y reenviar sobre este mismo rango."""
        self.ensure_one()
        registros = self.env['local_py.documento_anulado'].search([
            ('fe_py_evento_id', '=', self.id),
        ])
        retenidos = self.env['local_py.documento_anulado']
        for registro in registros:
            try:
                registro.unlink()
            except exceptions.UserError:
                retenidos |= registro
        if retenidos:
            self.env['fe_py.documento_electronico.log'].sudo().create({
                'evento_id': self.id,
                'tipo_operacion': 'evento_inutilizacion',
                'resultado': 'advertencia',
                'mensaje_resultado': (
                    'No se pudieron liberar %s número(s) reservados por este '
                    'evento (la numeración real ya los superó — liberarlos '
                    'dejaría un hueco). Quedan reservados en Documentos '
                    'Anulados, a la espera de corregir y reenviar sobre '
                    'este mismo rango: %s'
                    % (len(retenidos), ', '.join(sorted(retenidos.mapped('numero'))))
                ),
            })

    def _fe_py_construir_xml_evento(self):
        self.ensure_one()
        ahora = fields.Datetime.now()

        g_group = etree.Element('{%s}gGroupGesEve' % SIFEN_NS, nsmap={None: SIFEN_NS})
        r_ges_eve = etree.SubElement(g_group, '{%s}rGesEve' % SIFEN_NS)
        r_eve = etree.SubElement(r_ges_eve, '{%s}rEve' % SIFEN_NS)
        r_eve.set('Id', str(self.id))

        _sub(r_eve, 'dFecFirma', ahora.strftime('%Y-%m-%dT%H:%M:%S'))
        _sub(r_eve, 'dVerFor', '150')

        if self.tipo_evento == 'cancelacion':
            _sub(r_eve, 'dTiGDE', '1')
            g_tipo = etree.SubElement(r_eve, '{%s}gGroupTiEvt' % SIFEN_NS)
            r_can = etree.SubElement(g_tipo, '{%s}rGeVeCan' % SIFEN_NS)
            _sub(r_can, 'Id', self.documento_id.cdc)
            _sub(r_can, 'mOtEve', self.motivo)
        else:
            _sub(r_eve, 'dTiGDE', '2')
            g_tipo = etree.SubElement(r_eve, '{%s}gGroupTiEvt' % SIFEN_NS)
            r_inu = etree.SubElement(g_tipo, '{%s}rGeVeInu' % SIFEN_NS)
            partes_desde = self.nro_documento_desde.split('-')
            partes_hasta = self.nro_documento_hasta.split('-')
            i_tide, _desc = TIDE_POR_TIPO_FISCAL[self.tipo_fiscal_id.name]
            _sub(r_inu, 'dNumTim', '%08d' % self.journal_id.l10n_py_timbrado)
            _sub(r_inu, 'dEst', partes_desde[0].zfill(3))
            _sub(r_inu, 'dPunExp', partes_desde[1].zfill(3))
            _sub(r_inu, 'dNumIn', partes_desde[2].zfill(7))
            _sub(r_inu, 'dNumFin', partes_hasta[2].zfill(7))
            _sub(r_inu, 'iTiDE', i_tide)
            _sub(r_inu, 'mOtEve', self.motivo)

        return g_group

    def _fe_py_firmar_evento(self, g_group_root, company):
        if XMLSigner is None:
            raise exceptions.UserError(
                'Falta instalar la librería "signxml" en el servidor.'
            )
        if not (company.fe_py_cert_path and company.fe_py_private_key_path):
            raise exceptions.UserError(
                'La Compañía "%s" no tiene Certificado generado.' % company.name
            )
        try:
            with open(company.fe_py_cert_path, 'rb') as f:
                cert_pem = f.read()
            with open(company.fe_py_private_key_path, 'rb') as f:
                key_pem = f.read()
        except Exception as ex:
            raise exceptions.UserError('No se pudo leer el Certificado: %s' % ex)

        r_ges_eve = g_group_root.find('{%s}rGesEve' % SIFEN_NS)
        r_eve = r_ges_eve.find('{%s}rEve' % SIFEN_NS)
        evento_id_attr = r_eve.get('Id')

        signer = XMLSigner(
            method=signxml.SignatureConstructionMethod.enveloped,
            signature_algorithm='rsa-sha256',
            digest_algorithm='sha256',
            c14n_algorithm=C14N_ALGORITHM,
        )
        signer.namespaces = {None: signxml.namespaces.ds}
        try:
            signed_r_ges_eve = signer.sign(r_ges_eve, key=key_pem, cert=cert_pem, reference_uri=evento_id_attr)
        except Exception as ex:
            raise exceptions.UserError('Error al firmar el evento: %s' % ex)

        try:
            XMLVerifier().verify(signed_r_ges_eve, x509_cert=cert_pem)
        except Exception as ex:
            raise exceptions.UserError(
                'El evento se firmó pero no pasó la verificación inmediata: %s' % ex
            )

        # signxml puede devolver rGesEve desvinculado de su padre original
        # (g_group_root) — no alcanza con devolver g_group_root tal cual,
        # hay que reconstruirlo con el rGesEve YA FIRMADO como hijo (bug
        # real detectado y corregido antes de entregar esta fase: sin
        # esto, el sobre SOAP se armaba con el evento SIN firmar).
        nuevo_g_group = etree.Element('{%s}gGroupGesEve' % SIFEN_NS, nsmap={None: SIFEN_NS})
        nuevo_g_group.append(signed_r_ges_eve)
        return nuevo_g_group

    def _fe_py_construir_soap_evento(self, dEvReg_content):
        nsmap = {'soap': SOAP_NS, None: SIFEN_NS}
        envelope = etree.Element('{%s}Envelope' % SOAP_NS, nsmap=nsmap)
        etree.SubElement(envelope, '{%s}Header' % SOAP_NS)
        body = etree.SubElement(envelope, '{%s}Body' % SOAP_NS)
        r_envi_evento = etree.SubElement(body, '{%s}rEnviEventoDe' % SIFEN_NS)
        d_id_el = etree.SubElement(r_envi_evento, '{%s}dId' % SIFEN_NS)
        d_id_el.text = str(self.id)
        d_ev_reg = etree.SubElement(r_envi_evento, '{%s}dEvReg' % SIFEN_NS)
        d_ev_reg.append(dEvReg_content)

        return etree.tostring(envelope, xml_declaration=True, encoding='UTF-8').decode('utf-8')

    def _fe_py_llamar_ws_eventos(self, soap_xml, ambiente, company):
        if requests is None:
            raise exceptions.UserError('Falta la librería "requests" en el servidor.')
        url = WS_EVENTOS_URLS.get(ambiente)
        headers = {'Content-Type': 'application/soap+xml; charset=utf-8'}
        response = requests.post(
            url, data=soap_xml.encode('utf-8'), headers=headers,
            cert=(company.fe_py_cert_path, company.fe_py_private_key_path),
            timeout=TIMEOUT_SEGUNDOS,
        )
        response.raise_for_status()
        return response.text

    def _fe_py_parsear_respuesta_evento(self, response_xml):
        root = etree.fromstring(
            response_xml.encode('utf-8') if isinstance(response_xml, str) else response_xml
        )
        ns = {'s': SIFEN_NS}
        d_est_res = root.find('.//s:dEstRes', ns)
        d_cod_res = root.find('.//s:gResProc/s:dCodRes', ns)
        d_msg_res = root.find('.//s:gResProc/s:dMsgRes', ns)
        texto_estado = (d_est_res.text or '').strip() if d_est_res is not None else ''
        estado = 'aprobado' if texto_estado.lower().startswith('aprobado') else 'rechazado'
        return {
            'estado': estado,
            'codigo_respuesta': d_cod_res.text if d_cod_res is not None else False,
            'mensaje_respuesta': d_msg_res.text if d_msg_res is not None else texto_estado,
        }

    def _fe_py_simular_respuesta_evento(self):
        self.ensure_one()
        opcion = self.simular_resultado or 'aprobado'
        if opcion == 'aprobado':
            return {
                'estado': 'aprobado',
                'codigo_respuesta': '0600',
                'mensaje_respuesta': 'Evento aprobado (SIMULADO)',
            }
        if opcion == 'rechazado':
            return {
                'estado': 'rechazado',
                'codigo_respuesta': self.simular_codigo_rechazo or '4000',
                'mensaje_respuesta': (self.simular_mensaje_rechazo or 'Rechazado') + ' (SIMULADO)',
            }
        raise TimeoutError(
            'Sin respuesta del servidor SIFEN — tiempo de espera agotado (SIMULADO).'
        )
