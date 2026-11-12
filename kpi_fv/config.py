"""Caminhos locais ou no volume persistente da hospedagem."""

import os
from pathlib import Path

RAIZ_DADOS = Path(os.environ.get("KPI_STORAGE_DIR", "."))
DIR_DADOS = RAIZ_DADOS / "dados"
BANCO = DIR_DADOS / "kpi.db"
DIR_FOTOS = DIR_DADOS / "fotos"
DIR_SAIDA = RAIZ_DADOS / "saida"
