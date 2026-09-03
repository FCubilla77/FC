# -*- coding: utf-8 -*-
"""Envío del DE firmado al WS Sincrónico de SIFEN (siRecepDE), con dos
implementaciones intercambiables según Compañía.fe_py_ambiente:

  - Simulado: no sale ninguna conexión a la red. Genera una respuesta
    sintética según lo que el usuario haya elegido en
    documento.simular_resultado, para poder probar el circuito completo
    (Aprobado / Aprobado con Observación / Rechazado / Error de
    Comunicación) sin acceso real a la DNIT.
  - Test / Producción: arma el sobre SOAP a mano (sin WSDL dinámico, para
    no depender de tener acceso al WSDL real antes de tenerlo probado) y
    hace la llamada HTTPS con autenticación mutua TLS usando el
    certificado propio de la Compañía.

ALCANCE / LIMITACIONES DE ESTA FASE:
  - La detección de "Aprobado con Observación" en una respuesta REAL de
    SIFEN no está confirmada contra un ejemplo real de respuesta de este
    WS puntual (siRecepDE) — hoy cualquier dCodRes != '0260' se trata como
    Rechazado. Si en la práctica SIFEN devuelve observaciones dentro de la
    misma respuesta de Aprobado, hay que revisar esto contra un caso real.
  - No hay reintento automático todavía (eso queda para un cron, ítem ya
    aprobado como mejora en el análisis inicial).
  - Solo cubre envío INDIVIDUAL (WS Sincrónico) — lotes (WS Asincrónico)
    quedan para una fase posterior, según lo definido.
"""
import logging
import random

from lxml import etree

from odoo import exceptions, fields, models

_logger = logging.getLogger(__name__)

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

SIFEN_NS = 'http://ekuatia.set.gov.py/sifen/xsd'
SOAP_NS = 'http://www.w3.org/2003/05/soap-envelope'

WS_SINCRONICO_URLS = {
    # NOTA: el Manual Técnico v150 (cap. 7.10) muestra la URL de Test como
    # ".../recibe.wsd?wsdl" (sin la "l" final de "wsdl"), a diferencia de
    # Producción (".../recibe.wsdl?wsdl"). Parece una errata del propio
    # manual - se deja acá la forma consistente con el resto de los
    # servicios (todos terminan en ".wsdl"), pero HAY QUE VERIFICARLO
    # contra el WSDL real apenas haya acceso al Ambiente de Test.
    'test': 'https://sifen-test.set.gov.py/de/ws/sync/recibe.wsdl',
    'produccion': 'https://sifen.set.gov.py/de/ws/sync/recibe.wsdl',
}

TIMEOUT_SEGUNDOS = 30


class FePyDocumentoElectronico(models.Model):
    _inherit = 'fe_py.documento_electronico'

    def action_enviar(self):
        """Envía el DE firmado a SIFEN (real o Simulado, según Ambiente).
        Requiere estado 'firmado'. Al terminar queda en 'aprobado',
        'aprobado_observacion', 'rechazado' o 'error_comunicacion'."""
        for doc in self:
            if doc.estado != 'firmado':
                raise exceptions.UserError(
                    'No se puede enviar: el Documento Electrónico de %s está '
                    'en estado "%s". Primero hay que Generar el XML y Firmarlo.'
                    % (doc.move_id.display_name, dict(doc._fields['estado'].selection).get(doc.estado))
                )
            doc._fe_py_enviar_de_sincrono()
        return True

    def _fe_py_enviar_de_sincrono(self):
        self.ensure_one()
        if not self.xml_firmado:
            raise exceptions.UserError('No hay XML firmado para enviar.')

        company = self.move_id.company_id
        ambiente = company.fe_py_ambiente
        d_id = self.env['ir.sequence'].sudo().next_by_code('fe_py.envio.did') or str(self.id)
        soap_request = self._fe_py_construir_soap_envio(d_id)

        self.write({'intentos': self.intentos + 1, 'fecha_envio': fields.Datetime.now()})

        simulado = ambiente == 'simulado'
        try:
            if simulado:
                resultado = self._fe_py_simular_respuesta_sifen()
                response_payload = 'Respuesta simulada: %s' % resultado
            elif ambiente in ('test', 'produccion'):
                response_xml = self._fe_py_llamar_ws_sincrono(soap_request, ambiente, company)
                resultado = self._fe_py_parsear_respuesta_envio(response_xml)
                response_payload = response_xml
            else:
                raise exceptions.UserError('Ambiente FE no configurado en la Compañía.')
        except exceptions.UserError:
            raise
        except Exception as ex:
            self.write({'estado': 'error_comunicacion', 'simulado': simulado})
            self.env['fe_py.documento_electronico.log'].sudo().create({
                'documento_id': self.id,
                'tipo_operacion': 'envio_individual',
                'resultado': 'error',
                'mensaje_resultado': 'Error de comunicación: %s' % ex,
                'request_payload': soap_request,
                'simulado': simulado,
            })
            return

        codigo = resultado.get('codigo_respuesta')
        mensaje = resultado.get('mensaje_respuesta')
        if codigo == '0260':
            nuevo_estado = resultado.get('estado') or 'aprobado'
        else:
            nuevo_estado = 'rechazado'

        self.write({
            'estado': nuevo_estado,
            'codigo_respuesta': codigo,
            'mensaje_respuesta': mensaje,
            'fecha_respuesta': fields.Datetime.now(),
            'simulado': simulado,
            'protocolo_autorizacion': resultado.get('protocolo') or False,
            'respuesta_sifen_raw': response_payload,
        })
        self.env['fe_py.documento_electronico.log'].sudo().create({
            'documento_id': self.id,
            'tipo_operacion': 'envio_individual',
            'resultado': 'exito' if nuevo_estado in ('aprobado', 'aprobado_observacion') else 'error',
            'codigo_resultado': codigo,
            'mensaje_resultado': mensaje,
            'request_payload': soap_request,
            'response_payload': response_payload,
            'simulado': simulado,
        })

        # Documento fiscal definitivo: el XML firmado + QR + protocolo.
        # Se arma acá porque el protocolo recién existe después de que
        # SIFEN aprueba. Un fallo armándolo no debe tumbar el envío ya
        # aprobado — queda registrado como advertencia.
        if nuevo_estado in ('aprobado', 'aprobado_observacion'):
            try:
                self._fe_py_generar_xml_final()
            except Exception as ex:
                _logger.warning(
                    "FE_Py: no se pudo armar el XML final de %s: %s",
                    self.move_id.display_name, ex, exc_info=True,
                )
                self.env['fe_py.documento_electronico.log'].sudo().create({
                    'documento_id': self.id,
                    'tipo_operacion': 'envio_individual',
                    'resultado': 'advertencia',
                    'mensaje_resultado':
                        'El documento fue aprobado por SIFEN, pero no se pudo '
                        'armar el XML final (firmado + QR + protocolo): %s' % ex,
                    'simulado': simulado,
                })

    def _fe_py_construir_soap_envio(self, d_id):
        self.ensure_one()
        de_firmado_root = etree.fromstring(self.xml_firmado.encode('utf-8'))

        # IMPORTANTE: SIFEN_NS va SIN prefijo (namespace por defecto), igual
        # que ya lo trae el <rDE> firmado. Si acá se usara un prefijo
        # distinto (ej. "xsd:"), lxml reescribe el prefijo de TODO el
        # sub-árbol ya firmado al insertarlo (para no duplicar la
        # declaración del namespace) — eso cambia los bytes exactos que
        # entraron en la canonicalización original y **invalida la firma**
        # (detectado y confirmado con una verificación real antes de
        # entregar esta fase).
        nsmap = {'soap': SOAP_NS, None: SIFEN_NS}
        envelope = etree.Element('{%s}Envelope' % SOAP_NS, nsmap=nsmap)
        etree.SubElement(envelope, '{%s}Header' % SOAP_NS)
        body = etree.SubElement(envelope, '{%s}Body' % SOAP_NS)
        r_envi_de = etree.SubElement(body, '{%s}rEnviDe' % SIFEN_NS)
        d_id_el = etree.SubElement(r_envi_de, '{%s}dId' % SIFEN_NS)
        d_id_el.text = str(d_id)
        x_de = etree.SubElement(r_envi_de, '{%s}xDe' % SIFEN_NS)
        x_de.append(de_firmado_root)

        return etree.tostring(envelope, xml_declaration=True, encoding='UTF-8').decode('utf-8')

    def _fe_py_llamar_ws_sincrono(self, soap_xml, ambiente, company):
        if requests is None:
            raise exceptions.UserError(
                'Falta la librería "requests" en el servidor (normalmente '
                'viene con Odoo — revisar la instalación de Python).'
            )
        url = WS_SINCRONICO_URLS.get(ambiente)
        if not (company.fe_py_cert_path and company.fe_py_private_key_path):
            raise exceptions.UserError(
                'Falta el Certificado de la Compañía (necesario para la '
                'autenticación mutua TLS con SIFEN) — generarlo desde '
                'Ajustes > Empresas.'
            )
        headers = {'Content-Type': 'application/soap+xml; charset=utf-8'}
        response = requests.post(
            url,
            data=soap_xml.encode('utf-8'),
            headers=headers,
            cert=(company.fe_py_cert_path, company.fe_py_private_key_path),
            timeout=TIMEOUT_SEGUNDOS,
        )
        response.raise_for_status()
        return response.text

    def _fe_py_parsear_respuesta_envio(self, response_xml):
        root = etree.fromstring(
            response_xml.encode('utf-8') if isinstance(response_xml, str) else response_xml
        )
        ns = {'s': SIFEN_NS}
        cod_res = root.find('.//s:dCodRes', ns)
        msg_res = root.find('.//s:dMsgRes', ns)
        prot_aut = root.find('.//s:dProtAut', ns)
        return {
            'codigo_respuesta': cod_res.text if cod_res is not None else False,
            'mensaje_respuesta': msg_res.text if msg_res is not None else False,
            'protocolo': prot_aut.text if prot_aut is not None else False,
        }

    def _fe_py_protocolo_simulado(self):
        """Número de protocolo sintético (10 dígitos, como los reales) para
        que el XML final se pueda armar y probar completo en Simulado."""
        return '%010d' % random.randint(0, 9999999999)

    def _fe_py_simular_respuesta_sifen(self):
        """No sale a la red. Devuelve una respuesta sintética según
        self.simular_resultado, con la misma forma que
        _fe_py_parsear_respuesta_envio (para que el resto del flujo sea
        idéntico, real o simulado)."""
        self.ensure_one()
        opcion = self.simular_resultado or 'aprobado'

        if opcion == 'aprobado':
            return {
                'codigo_respuesta': '0260',
                'mensaje_respuesta': 'Autorización del DE satisfactoria (SIMULADO)',
                'estado': 'aprobado',
                'protocolo': self._fe_py_protocolo_simulado(),
            }
        if opcion == 'aprobado_observacion':
            return {
                'codigo_respuesta': '0260',
                'mensaje_respuesta': 'Autorización del DE con observaciones (SIMULADO)',
                'estado': 'aprobado_observacion',
                'protocolo': self._fe_py_protocolo_simulado(),
            }
        if opcion == 'rechazado':
            return {
                'codigo_respuesta': self.simular_codigo_rechazo or '0160',
                'mensaje_respuesta': (self.simular_mensaje_rechazo or 'Rechazado') + ' (SIMULADO)',
            }
        raise TimeoutError(
            'Sin respuesta del servidor SIFEN — tiempo de espera agotado (SIMULADO).'
        )
