"""Base de dados (SQLite ou PostgreSQL via SQLAlchemy): empresas, conversas e mensagens."""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
                        create_engine, event, inspect, text)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker)

from config import cfg

log = logging.getLogger("mactech.db")

_sqlite = cfg.database_url.startswith("sqlite")
engine = create_engine(cfg.database_url, pool_pre_ping=True,
                       **({"connect_args": {"timeout": 30}} if _sqlite else {}))

if _sqlite:
    @event.listens_for(engine, "connect")
    def _pragmas(con, _):
        """WAL permite ler e escrever ao mesmo tempo sem 'database is locked'."""
        cur = con.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def agora():
    return datetime.now(timezone.utc)


def fim_teste():
    """O teste grátis dura 2 dias a partir do registo."""
    return agora() + timedelta(days=2)


class Base(DeclarativeBase):
    pass


class Empresa(Base):
    """Um cliente da MacTech. Cada empresa tem o seu catálogo e, opcionalmente, o seu número de WhatsApp."""
    __tablename__ = "empresas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str | None] = mapped_column(String(60), unique=True, index=True, nullable=True)  # endereço do chat web
    wa_phone_number_id: Mapped[str | None] = mapped_column(String(40), unique=True, index=True, nullable=True)
    wa_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)  # TODO: cifrar em produção
    system_prompt: Mapped[str] = mapped_column(Text)     # catálogo + regras do negócio
    humano_ativo: Mapped[bool] = mapped_column(Boolean, default=True)  # a empresa tem equipa para atender?
    no_hub: Mapped[bool] = mapped_column(Boolean, default=True)        # aparece na lista do número partilhado?
    estado: Mapped[str] = mapped_column(String(10), default="teste")   # 'teste', 'ativo' ou 'suspenso'
    teste_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=fim_teste)
    # Nível 4: ferramentas que a IA pode usar ("stock,encomendas,fatura,departamentos") e ligação ao sistema da empresa
    ferramentas: Mapped[str | None] = mapped_column(Text, nullable=True)
    integracao_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    integracao_segredo: Mapped[str | None] = mapped_column(Text, nullable=True)


class Conversa(Base):
    """Uma conversa entre um cliente (número ou sessão web) e uma empresa."""
    __tablename__ = "conversas"
    __table_args__ = (UniqueConstraint("phone_number_id", "cliente_numero"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone_number_id: Mapped[str] = mapped_column(String(40), index=True)  # número que recebeu a conversa ('web' no chat web)
    empresa_id: Mapped[int | None] = mapped_column(ForeignKey("empresas.id"), index=True, nullable=True)
    cliente_numero: Mapped[str] = mapped_column(String(64))
    humano_assumiu: Mapped[bool] = mapped_column(Boolean, default=False)  # True = a IA fica calada
    inicio_historico_id: Mapped[int] = mapped_column(Integer, default=0)  # a IA só vê mensagens depois deste id
    contacto: Mapped[str | None] = mapped_column(String(120), nullable=True)  # telefone/email do cliente
    departamento_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # para onde a IA a encaminhou
    agente_id: Mapped[int | None] = mapped_column(Integer, nullable=True)        # atendente humano que a assumiu
    mensagens: Mapped[list["Mensagem"]] = relationship(back_populates="conversa")


class Mensagem(Base):
    __tablename__ = "mensagens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversa_id: Mapped[int] = mapped_column(ForeignKey("conversas.id"), index=True)
    remetente: Mapped[str] = mapped_column(String(10))  # 'user', 'assistant' ou 'human'
    conteudo: Mapped[str] = mapped_column(Text)
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    wa_id: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)  # id da mensagem no WhatsApp (evita duplicados)
    sem_resposta: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)  # pergunta que o bot não soube responder
    conversa: Mapped[Conversa] = relationship(back_populates="mensagens")


class Departamento(Base):
    """Vendas, Suporte, Financeiro... A IA encaminha o cliente para o departamento certo."""
    __tablename__ = "departamentos"
    __table_args__ = (UniqueConstraint("empresa_id", "nome"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True)
    nome: Mapped[str] = mapped_column(String(60))
    descricao: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Agente(Base):
    """Atendente humano. Entra em /agente com a sua chave (guardada só em hash)."""
    __tablename__ = "agentes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True)
    nome: Mapped[str] = mapped_column(String(80))
    chave_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    departamento_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # vazio = vê todos
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Produto(Base):
    """Catálogo com preço e stock (a alternativa a ligar um ERP)."""
    __tablename__ = "produtos"
    __table_args__ = (UniqueConstraint("empresa_id", "sku"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True)
    sku: Mapped[str] = mapped_column(String(40))
    nome: Mapped[str] = mapped_column(String(160))
    preco: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock: Mapped[int] = mapped_column(Integer, default=0)


class Encomenda(Base):
    __tablename__ = "encomendas"
    __table_args__ = (UniqueConstraint("empresa_id", "codigo"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(40))
    contacto: Mapped[str] = mapped_column(String(120))   # telefone ou email do dono da encomenda
    estado: Mapped[str] = mapped_column(String(60))
    itens: Mapped[str | None] = mapped_column(Text, nullable=True)
    total: Mapped[float | None] = mapped_column(Float, nullable=True)
    atualizado: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class Ticket(Base):
    """Pedido registado para a equipa (reclamação, pedido de fatura, transferência)."""
    __tablename__ = "tickets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True)
    conversa_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    departamento: Mapped[str | None] = mapped_column(String(60), nullable=True)
    tipo: Mapped[str] = mapped_column(String(20), default="geral")
    assunto: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(10), default="aberto", index=True)  # 'aberto' ou 'fechado'
    criado: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


def migrar():
    """Acrescenta colunas novas a bases de dados de versões antigas, para evitar 'no such column'.
    Nunca bloqueia o arranque: se algo falhar, só regista no log."""
    try:
        insp = inspect(engine)
        for tabela in Base.metadata.sorted_tables:
            if not insp.has_table(tabela.name):
                continue
            existentes = {c["name"] for c in insp.get_columns(tabela.name)}
            for col in tabela.columns:
                if col.name in existentes:
                    continue
                tipo = col.type.compile(dialect=engine.dialect)
                try:
                    with engine.begin() as con:
                        con.execute(text(f'ALTER TABLE "{tabela.name}" ADD COLUMN "{col.name}" {tipo}'))
                    log.warning("Migração: coluna %s.%s acrescentada", tabela.name, col.name)
                except Exception:
                    log.exception("Migração: não foi possível acrescentar %s.%s", tabela.name, col.name)
        # Conversas antigas não tinham phone_number_id: copia o número da empresa
        with engine.begin() as con:
            con.execute(text(
                "UPDATE conversas SET phone_number_id = (SELECT wa_phone_number_id FROM empresas "
                "WHERE empresas.id = conversas.empresa_id) WHERE phone_number_id IS NULL"))
    except Exception:
        log.exception("Migração automática falhou (o servidor continua a arrancar)")


def init_db():
    """Cria as tabelas que faltam e atualiza as antigas."""
    Base.metadata.create_all(engine)
    migrar()
