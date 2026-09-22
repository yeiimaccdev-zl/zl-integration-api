"""Saneamiento de valores de origen no confiable antes de persistirlos en
auditoría.

Varios campos del registro de auditoría provienen directamente de
encabezados HTTP controlados por quien hace la solicitud (API Key, agente
de usuario, parámetros de consulta). Un atacante puede enviar ahí caracteres
de control, saltos de línea o cadenas arbitrariamente largas, buscando
inyectar contenido en los logs (log injection) o desbordar las columnas de
la base de datos. Estas funciones normalizan esa entrada antes de que
llegue a la capa de persistencia.
"""
import re

_CARACTERES_DE_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_CARACTERES_NO_ALFANUMERICOS = re.compile(r"[^A-Za-z0-9_-]")


def sanear_texto_auditoria(valor: str | None, longitud_maxima: int) -> str | None:
    """Elimina caracteres de control y trunca un texto libre antes de auditarlo.

    Se usa para campos como el agente de usuario o los parámetros de
    consulta, que deben conservar su contenido legible pero no pueden
    contener caracteres de control ni exceder el tamaño de su columna.
    """
    if not valor:
        return None

    limpio = _CARACTERES_DE_CONTROL.sub("", valor).strip()
    if not limpio:
        return None

    if len(limpio) > longitud_maxima:
        return limpio[: longitud_maxima - 3] + "..."
    return limpio


def enmascarar_llave_intentada(clave_intentada: str | None, longitud_maxima: int) -> str | None:
    """Reduce una API Key (válida o no) a un prefijo seguro para auditoría.

    Conserva únicamente caracteres alfanuméricos, guiones y guiones bajos —
    el mismo alfabeto con el que se generan las llaves reales—, de modo que
    cualquier intento de inyección quede descartado y nunca se guarde el
    secreto completo, solo lo suficiente para identificar qué llave (o qué
    patrón de ataque) se intentó usar.
    """
    if not clave_intentada:
        return None

    saneada = _CARACTERES_NO_ALFANUMERICOS.sub("", clave_intentada)
    if not saneada:
        return None

    if len(saneada) > longitud_maxima:
        return saneada[: longitud_maxima - 3] + "..."
    return saneada
