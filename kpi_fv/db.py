"""Camada de persistencia: esquema SQLite e carga inicial."""

from __future__ import annotations

import sqlite3
import unicodedata
from pathlib import Path

CAMINHO_PADRAO = Path("dados/kpi.db")

ESQUEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS grupo (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    nome   TEXT NOT NULL UNIQUE,
    ordem  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS unidade (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nome            TEXT NOT NULL UNIQUE,
    grupo_id        INTEGER REFERENCES grupo(id),
    capacidade_kwp  REAL,
    area_m2         REAL,
    cor             TEXT,
    incluir_painel  INTEGER NOT NULL DEFAULT 1,
    ordem           INTEGER NOT NULL DEFAULT 0,
    observacao      TEXT
);

-- Resolve as variacoes de grafia encontradas nas planilhas e nos relatorios
-- antigos (PRODENA/PRODERNA, Mirate/Mirante) para uma unica unidade.
CREATE TABLE IF NOT EXISTS alias_unidade (
    chave      TEXT PRIMARY KEY,
    unidade_id INTEGER NOT NULL REFERENCES unidade(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS parametro_mensal (
    competencia             TEXT PRIMARY KEY,   -- 'AAAA-MM'
    tarifa_rs_kwh           REAL NOT NULL,
    fator_emissao_tco2_mwh  REAL NOT NULL,
    metodologia             TEXT
);

CREATE TABLE IF NOT EXISTS leitura (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    unidade_id  INTEGER NOT NULL REFERENCES unidade(id) ON DELETE CASCADE,
    competencia TEXT NOT NULL,
    tipo        TEXT NOT NULL CHECK (tipo IN ('gerada', 'perdida')),
    energia_kwh REAL NOT NULL DEFAULT 0,
    UNIQUE (unidade_id, competencia, tipo)
);

CREATE INDEX IF NOT EXISTS idx_leitura_comp ON leitura (competencia, tipo);

CREATE TABLE IF NOT EXISTS relatorio (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo      TEXT NOT NULL,
    subtitulo   TEXT,
    inicio      TEXT NOT NULL,      -- 'AAAA-MM'
    fim         TEXT NOT NULL,      -- 'AAAA-MM'
    equipe      TEXT,
    autor       TEXT,
    revisor     TEXT,
    criado_em   TEXT NOT NULL,
    atualizado_em TEXT
);

CREATE TABLE IF NOT EXISTS comentario (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    relatorio_id INTEGER NOT NULL REFERENCES relatorio(id) ON DELETE CASCADE,
    ordem        INTEGER NOT NULL DEFAULT 0,
    texto        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS foto (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    relatorio_id INTEGER NOT NULL REFERENCES relatorio(id) ON DELETE CASCADE,
    unidade_id   INTEGER REFERENCES unidade(id),
    secao        TEXT,
    legenda      TEXT,
    arquivo      TEXT NOT NULL,
    ordem        INTEGER NOT NULL DEFAULT 0
);
"""

# Grupos e unidades conforme os paineis de KPI do CEAMAZON. As unidades do
# CEAMAZON entram com incluir_painel = 0 porque, no painel atual, elas aparecem
# apenas no bloco de geracao perdida.
GRUPOS_PADRAO = [
    ("Prefeitura do Campus", 1),
    ("Projeto SIMA", 2),
    ("E-MOB", 3),
    ("CEAMAZON", 4),
]

UNIDADES_PADRAO = [
    # nome, grupo, capacidade_kwp, area_m2, cor, incluir_painel, aliases
    ("WEG - Mirante do Rio", "Projeto SIMA", 59.295, 319.19, "#1F4E79", 1,
     ["Mirate do Rio - SIMA", "Mirante do Rio - SIMA", "Mirante do Rio", "WEG Mirante do Rio"]),
    ("Abaetetuba", "Prefeitura do Campus", 50.0, 260.0, "#ED7D31", 1, []),
    ("ICB", "Prefeitura do Campus", 50.0, 260.0, "#4472C4", 1,
     ["Instituto de Ciencias Biologicas"]),
    ("PPGQ", "Prefeitura do Campus", 50.0, 260.0, "#70AD47", 1, ["Ensino Quimica"]),
    ("Mirante - Prefeitura", "Prefeitura do Campus", 50.0, 260.0, "#C00080", 1,
     ["Mirate - Prefeitura"]),
    ("PPGL", "Prefeitura do Campus", 50.0, 260.0, "#2E75B6", 1,
     ["PPGL - Letras", "Letras"]),
    ("PRODERNA", "Prefeitura do Campus", 50.0, 260.0, "#1B5E20", 1, ["PRODENA"]),
    ("Pier", "E-MOB", None, None, "#7F7F7F", 1, ["Pier - E-MOB", "E-MOB"]),
    ("Controlador de Carga", "CEAMAZON", 5.41, 31.14, "#264478", 0,
     ["Controlador de Carga  - Ceamazon", "Controlador de Carga - Ceamazon"]),
    ("Fronius", "CEAMAZON", 18.0, 31.0, "#A5A5A5", 0, ["Fronius - Ceamazon"]),
    ("SMA", "CEAMAZON", 55.0, 105.1, "#FFC000", 0, ["SMA - Ceamazon"]),
    ("Sistema de Armazenamento", "CEAMAZON", None, None, "#5B9BD5", 0,
     ["Armazenamento", "Sistema de Armazenamento - Ceamazon"]),
]


def normalizar(texto: str) -> str:
    """Chave de comparacao: sem acento, sem espaco duplo, em minusculas."""
    if texto is None:
        return ""
    sem_acento = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.lower().replace("_", " ").split())


def conectar(caminho: Path | str = CAMINHO_PADRAO) -> sqlite3.Connection:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False porque o Streamlit executa cada interacao em uma
    # thread nova, reaproveitando a mesma conexao em cache.
    conn = sqlite3.connect(caminho, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def criar_esquema(conn: sqlite3.Connection) -> None:
    conn.executescript(ESQUEMA)
    conn.commit()


def carregar_cadastro_padrao(conn: sqlite3.Connection) -> None:
    """Insere grupos e unidades padrao. Nao sobrescreve o que ja existe."""
    for nome, ordem in GRUPOS_PADRAO:
        conn.execute(
            "INSERT OR IGNORE INTO grupo (nome, ordem) VALUES (?, ?)", (nome, ordem)
        )

    for ordem, (nome, grupo, kwp, area, cor, painel, aliases) in enumerate(UNIDADES_PADRAO, start=1):
        grupo_id = conn.execute(
            "SELECT id FROM grupo WHERE nome = ?", (grupo,)
        ).fetchone()["id"]
        conn.execute(
            """INSERT OR IGNORE INTO unidade
               (nome, grupo_id, capacidade_kwp, area_m2, cor, incluir_painel, ordem)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (nome, grupo_id, kwp, area, cor, painel, ordem),
        )
        unidade_id = conn.execute(
            "SELECT id FROM unidade WHERE nome = ?", (nome,)
        ).fetchone()["id"]
        for apelido in [nome, *aliases]:
            conn.execute(
                "INSERT OR IGNORE INTO alias_unidade (chave, unidade_id) VALUES (?, ?)",
                (normalizar(apelido), unidade_id),
            )
    conn.commit()


def iniciar(caminho: Path | str = CAMINHO_PADRAO) -> sqlite3.Connection:
    conn = conectar(caminho)
    criar_esquema(conn)
    carregar_cadastro_padrao(conn)
    return conn


def resolver_unidade(conn: sqlite3.Connection, nome: str) -> int | None:
    """Devolve o id da unidade a partir do nome ou de um apelido conhecido."""
    linha = conn.execute(
        "SELECT unidade_id FROM alias_unidade WHERE chave = ?", (normalizar(nome),)
    ).fetchone()
    return linha["unidade_id"] if linha else None


def criar_unidade(
    conn: sqlite3.Connection,
    nome: str,
    grupo: str = "Outros",
    incluir_painel: int = 1,
    cor: str | None = None,
) -> int:
    conn.execute("INSERT OR IGNORE INTO grupo (nome, ordem) VALUES (?, 99)", (grupo,))
    grupo_id = conn.execute("SELECT id FROM grupo WHERE nome = ?", (grupo,)).fetchone()["id"]
    cur = conn.execute(
        """INSERT INTO unidade (nome, grupo_id, cor, incluir_painel, ordem)
           VALUES (?, ?, ?, ?, 99)""",
        (nome, grupo_id, cor or "#888888", incluir_painel),
    )
    unidade_id = cur.lastrowid
    conn.execute(
        "INSERT OR IGNORE INTO alias_unidade (chave, unidade_id) VALUES (?, ?)",
        (normalizar(nome), unidade_id),
    )
    conn.commit()
    return unidade_id
