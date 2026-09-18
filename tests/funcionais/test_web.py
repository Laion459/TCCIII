from fastapi.testclient import TestClient

from extrato_pdf.web.app import app


def test_painel_ok():
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Painel" in resp.text


def test_menu_rotas_basicas():
    client = TestClient(app)
    for path in ("/pdfs", "/processar", "/lote", "/resultados", "/config", "/ajuda", "/validacao"):
        resp = client.get(path)
        assert resp.status_code == 200, path


def test_api_iniciar_lote_vazio():
    client = TestClient(app)
    resp = client.post("/api/lote/iniciar", json={"condicao": "A", "pdfs": []})
    assert resp.status_code == 400


def test_api_job_nao_encontrado():
    client = TestClient(app)
    resp = client.get("/api/jobs/inexistente")
    assert resp.status_code == 404


def test_lote_page_tem_progresso():
    client = TestClient(app)
    resp = client.get("/lote")
    assert "progress-panel" in resp.text
    assert "progress.js" in resp.text
    assert "pipeline-stepper" in resp.text
    assert "prog-sub-bar" in resp.text


def test_painel_resumo():
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Painel" in resp.text
    assert "Consistência por condição" in resp.text
    assert "Condição A" in resp.text
    assert "Condição B" in resp.text
    assert "Condição C" in resp.text


def test_resultados_filtro_condicao():
    client = TestClient(app)
    resp = client.get("/resultados?condicao=A")
    assert resp.status_code == 200
    assert "Condição A" in resp.text
    assert "filter-tab" in resp.text


def test_metricas_pagina():
    client = TestClient(app)
    resp = client.get("/metricas")
    assert resp.status_code == 200
    assert "Métricas experimentais" in resp.text
    assert "chart-taxa" in resp.text
    assert "charts.js" in resp.text
    assert "Hipótese do TCC" in resp.text


def test_config_pagina_tem_formulario():
    client = TestClient(app)
    resp = client.get("/config")
    assert resp.status_code == 200
    assert "tolerancia_monetaria" in resp.text
    assert "Salvar configuração" in resp.text
    assert "Instituições" in resp.text

