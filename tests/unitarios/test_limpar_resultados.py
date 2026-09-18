from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from extrato_pdf.web import servicos
from extrato_pdf.web.app import app
from extrato_pdf.web.jobs import gerenciador


def test_limpar_resultados_remove_saidas_e_preserva_readme(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    resultados = tmp_path / "resultados"
    (resultados / "experimentos" / "condicao_c" / "doc1").mkdir(parents=True)
    (resultados / "experimentos" / "condicao_c" / "doc1" / "resultado.json").write_text(
        "{}", encoding="utf-8"
    )
    (resultados / "metricas").mkdir(parents=True)
    (resultados / "metricas" / "metricas.json").write_text("[]", encoding="utf-8")
    (resultados / "README.md").write_text("# resultados\n", encoding="utf-8")

    monkeypatch.setattr(servicos, "pasta_resultados", lambda: resultados)
    monkeypatch.setattr(gerenciador, "tem_job_ativo", lambda: False)

    info = servicos.limpar_resultados()

    assert info["itens_removidos"] >= 1
    assert (resultados / "README.md").exists()
    assert not (resultados / "experimentos" / "condicao_c" / "doc1").exists()
    assert (resultados / "experimentos" / "condicao_a").is_dir()
    assert (resultados / "experimentos" / "condicao_b").is_dir()
    assert (resultados / "experimentos" / "condicao_c").is_dir()
    assert (resultados / "metricas").is_dir()
    assert not (resultados / "metricas" / "metricas.json").exists()


def test_limpar_resultados_bloqueia_com_job_ativo(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(gerenciador, "tem_job_ativo", lambda: True)
    with pytest.raises(RuntimeError, match="em andamento"):
        servicos.limpar_resultados()


def test_painel_tem_botao_limpar():
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Limpar resultados" in resp.text
    assert "/painel/limpar-resultados" in resp.text


def test_endpoint_limpar_redireciona(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    resultados = tmp_path / "resultados"
    resultados.mkdir()
    (resultados / "README.md").write_text("# ok\n", encoding="utf-8")
    monkeypatch.setattr(servicos, "pasta_resultados", lambda: resultados)
    monkeypatch.setattr(gerenciador, "tem_job_ativo", lambda: False)

    client = TestClient(app)
    resp = client.post("/painel/limpar-resultados", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/?ok=limpo"
