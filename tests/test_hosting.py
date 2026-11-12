"""Verificações de persistência e bloqueio de acesso da publicação."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class HostingTests(unittest.TestCase):
    def run_python(self, script, **extra_env):
        env = {**os.environ, **extra_env}
        result = subprocess.run(
            [sys.executable, "-c", script], env=env,
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_database_survives_process_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_python(
                "from kpi_fv import db; c=db.iniciar(); "
                "c.execute(\"INSERT INTO grupo(nome, ordem) VALUES ('Persistencia', 99)\"); "
                "c.commit(); c.close()",
                KPI_STORAGE_DIR=directory,
            )
            self.assertTrue((Path(directory) / "dados/kpi.db").exists())
            self.run_python(
                "from kpi_fv import db; c=db.iniciar(); "
                "assert c.execute(\"SELECT 1 FROM grupo WHERE nome='Persistencia'\").fetchone(); "
                "c.close()",
                KPI_STORAGE_DIR=directory,
            )

    def test_missing_password_blocks_database_access(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_python(
                "from streamlit.testing.v1 import AppTest; "
                "a=AppTest.from_file('app.py', default_timeout=30).run(); "
                "assert not a.exception; assert len(a.error)==1; "
                "assert len(a.get('file_uploader'))==0",
                KPI_STORAGE_DIR=directory, KPI_REQUIRE_AUTH="1", KPI_ACCESS_PASSWORD="",
            )
            self.assertFalse((Path(directory) / "dados/kpi.db").exists())

    def test_login_and_logout(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_python(
                "from streamlit.testing.v1 import AppTest\n"
                "a=AppTest.from_file('app.py', default_timeout=30).run()\n"
                "assert not a.exception\n"
                "a.text_input[0].set_value('incorreta'); a.button[0].click().run()\n"
                "assert len(a.error)==1\n"
                "a.text_input[0].set_value('teste-senha'); a.button[0].click().run()\n"
                "assert not a.exception; assert a.session_state['autenticado']\n"
                "assert len(a.tabs)==0  # banco vazio: tela de importação\n"
                "next(b for b in a.button if b.label=='Sair').click().run()\n"
                "assert not a.exception; assert len(a.text_input)==1\n"
                "assert 'autenticado' not in a.session_state\n",
                KPI_STORAGE_DIR=directory, KPI_REQUIRE_AUTH="1",
                KPI_ACCESS_PASSWORD="teste-senha",
            )

    def test_import_and_dashboard_on_persistent_volume(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_python(
                "from kpi_fv import db, importador, calculo\n"
                "c=db.iniciar()\n"
                "arquivo='dados/kpis_energia_por_unidade.xlsx'\n"
                "importador.importar_planilha(c, arquivo)\n"
                "importador.importar_cadastro_sistemas(c, arquivo)\n"
                "assert all(calculo.intervalo_disponivel(c)); c.close()\n"
                "from streamlit.testing.v1 import AppTest\n"
                "a=AppTest.from_file('app.py', default_timeout=30).run()\n"
                "assert not a.exception, str(a.exception)\n"
                "assert len(a.tabs)==4\n",
                KPI_STORAGE_DIR=directory, KPI_REQUIRE_AUTH="0", KPI_ACCESS_PASSWORD="",
            )


if __name__ == "__main__":
    unittest.main()
