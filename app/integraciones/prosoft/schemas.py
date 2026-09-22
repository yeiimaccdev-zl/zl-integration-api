"""Esquemas de respuesta del endpoint de colaboradores.

La informacion de costos (datos basicos + salario y auxilio de transporte) se modela en un
esquema separado, para que nunca viaje junto con los datos básicos salvo que
el sistema consumidor tenga el alcance correspondiente.
"""
from pydantic import BaseModel


class ColaboradorBasico(BaseModel):
    cedula: str
    nombre_completo: str
    correos: str = ""
    cargo: str = ""
    telefono: str = ""
    celular: str = ""
    fecha_ingreso: str = ""
    fecha_retiro: str = ""
    estado: str
    gerencia: str = ""
    sede: str = ""
    division: str = ""
    area_departamento: str = ""


class ColaboradorCostos(ColaboradorBasico):
    salario: str = ""
    auxilio_transporte: str = ""
