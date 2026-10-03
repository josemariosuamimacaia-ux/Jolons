"""Base de dados (SQLite via SQLAlchemy): empresas, conversas e mensagens."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, String, Text,
                        UniqueConstraint, create_engine)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column, relationship,
                            sessionmaker)

from config import cfg

engine = create_engine(cfg.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def agora():
    return datetime.now(timezone.utc)


def fim_teste():
    """O teste grátis dura 2 dias a partir do registo."""
    return agora() + timedelta(days=2)


class Base(DeclarativeBase):
    pass


class Empresa(Base):
    """Um cliente da MacTech. Cada empresa tem o seu número de WhatsApp e o seu catálogo."""
    __tablename__ = "empresas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str | None] = mapped_column(String(60), unique=True, index=True, nullable=True)  # endereço do chat web
    # Opcionais: empresas que usam o número partilhado da MacTech não têm número próprio
    wa_phone_number_id: Mapped[str | None] = mapped_column(String(40), unique=True, index=True, nullable=True)
    wa_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)  # TODO: cifrar em produção
    system_prompt: Mapped[str] = mapped_column(Text)     # catálogo + regras do negócio
    humano_ativo: Mapped[bool] = mapped_column(Boolean, default=True)  # a empresa tem equipa para atender?
    no_hub: Mapped[bool] = mapped_column(Boolean, default=True)        # aparece na lista do número partilhado?
    estado: Mapped[str] = mapped_column(String(10), default="teste")   # 'teste', 'ativo' ou 'suspenso'
    teste_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=fim_teste)


class Conversa(Base):
    """Uma conversa entre um cliente (número) e uma empresa."""
    __tablename__ = "conversas"
    __table_args__ = (UniqueConstraint("phone_number_id", "cliente_numero"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone_number_id: Mapped[str] = mapped_column(String(40), index=True)  # número que recebeu a conversa
    empresa_id: Mapped[int | None] = mapped_column(ForeignKey("empresas.id"), index=True, nullable=True)  # vazio até o cliente escolher
    cliente_numero: Mapped[str] = mapped_column(String(32))
    inicio_historico_id: Mapped[int] = mapped_column(Integer, default=0)  # a IA só vê mensagens depois deste id
    humano_assumiu: Mapped[bool] = mapped_column(Boolean, default=False)  # True = a IA fica calada
    mensagens: Mapped[list["Mensagem"]] = relationship(back_populates="conversa")


class Mensagem(Base):
    __tablename__ = "mensagens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversa_id: Mapped[int] = mapped_column(ForeignKey("conversas.id"), index=True)
    remetente: Mapped[str] = mapped_column(String(10))  # 'user', 'assistant' ou 'human'
    conteudo: Mapped[str] = mapped_column(Text)
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    conversa: Mapped[Conversa] = relationship(back_populates="mensagens")


def init_db():
    """Cria as tabelas se ainda não existirem."""
    Base.metadata.create_all(engine)
