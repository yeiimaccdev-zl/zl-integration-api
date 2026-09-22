""" Esquema inicial llaves de API y auditoría de solicitudes.  """
import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seguridad_llaves_api",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sistema", sa.String(length=100), nullable=False),
        sa.Column("id_usuario_responsable", sa.Integer(), nullable=True),
        sa.Column("nombre_usuario_responsable", sa.String(length=200), nullable=False),
        sa.Column("clave_hash", sa.String(length=255), nullable=False),
        sa.Column("alcance", sa.String(length=255), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("fecha_creacion", sa.DateTime(), nullable=False),
        sa.Column("fecha_expiracion", sa.DateTime(), nullable=False),
        sa.Column("fecha_ultima_actualizacion", sa.DateTime(), nullable=False),
        sa.Column("fecha_ultimo_uso", sa.DateTime(), nullable=True),
        sa.Column("fecha_contador_diario", sa.Date(), nullable=True),
        sa.Column("llamados_hoy", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_llamados", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_seguridad_llaves_api_sistema", "seguridad_llaves_api", ["sistema"])
    op.create_index(
        "ix_seguridad_llaves_api_clave_hash", "seguridad_llaves_api", ["clave_hash"], unique=True
    )

    op.create_table(
        "auditoria_solicitudes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("identificador_solicitud", sa.String(length=36), nullable=False),
        sa.Column("servicio", sa.String(length=80), nullable=False),
        sa.Column("metodo_http", sa.String(length=10), nullable=False),
        sa.Column("ruta", sa.String(length=255), nullable=False),
        sa.Column("parametros_consulta", sa.Text(), nullable=True),
        sa.Column("sistema_consumidor", sa.String(length=100), nullable=True),
        sa.Column("identificador_llave_api", sa.Integer(), nullable=True),
        sa.Column("responsable_llave_api", sa.String(length=200), nullable=True),
        sa.Column("prefijo_llave_intentada", sa.String(length=20), nullable=True),
        sa.Column("ip_origen", sa.String(length=45), nullable=True),
        sa.Column("ip_real_cliente", sa.String(length=255), nullable=True),
        sa.Column("agente_usuario", sa.String(length=255), nullable=True),
        sa.Column("codigo_respuesta", sa.Integer(), nullable=False),
        sa.Column("exitosa", sa.Boolean(), nullable=False),
        sa.Column("categoria_error", sa.String(length=50), nullable=True),
        sa.Column("mensaje_error", sa.Text(), nullable=True),
        sa.Column("tamano_respuesta_bytes", sa.Integer(), nullable=True),
        sa.Column("cantidad_registros", sa.Integer(), nullable=True),
        sa.Column("duracion_ms", sa.Float(), nullable=False),
        sa.Column("fecha_hora_inicio", sa.DateTime(), nullable=False),
        sa.Column("fecha_hora_fin", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_auditoria_solicitudes_identificador_solicitud",
        "auditoria_solicitudes",
        ["identificador_solicitud"],
    )
    op.create_index("ix_auditoria_solicitudes_servicio", "auditoria_solicitudes", ["servicio"])
    op.create_index(
        "ix_auditoria_solicitudes_sistema_consumidor", "auditoria_solicitudes", ["sistema_consumidor"]
    )
    op.create_index(
        "ix_auditoria_solicitudes_identificador_llave_api",
        "auditoria_solicitudes",
        ["identificador_llave_api"],
    )
    op.create_index(
        "ix_auditoria_solicitudes_fecha_hora_inicio", "auditoria_solicitudes", ["fecha_hora_inicio"]
    )


def downgrade() -> None:
    op.drop_table("auditoria_solicitudes")
    op.drop_table("seguridad_llaves_api")
