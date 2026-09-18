from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional


class StatusJob(str, Enum):
    PENDENTE = "pendente"
    EXECUTANDO = "executando"
    CONCLUIDO = "concluido"
    ERRO = "erro"
    CANCELADO = "cancelado"


class StatusItem(str, Enum):
    AGUARDANDO = "aguardando"
    PROCESSANDO = "processando"
    OK = "ok"
    FALHA = "falha"
    CANCELADO = "cancelado"


@dataclass
class ItemJob:
    arquivo: str
    status: StatusItem = StatusItem.AGUARDANDO
    resultado_status: Optional[str] = None
    instituicao: Optional[str] = None
    duracao_s: float = 0.0
    erro: Optional[str] = None
    caminho_relativo: Optional[str] = None
    mensagem: str = ""

    def para_dict(self) -> dict[str, Any]:
        return {
            "arquivo": self.arquivo,
            "status": self.status.value,
            "resultado_status": self.resultado_status,
            "instituicao": self.instituicao,
            "duracao_s": self.duracao_s,
            "erro": self.erro,
            "caminho_relativo": self.caminho_relativo,
            "mensagem": self.mensagem,
        }


@dataclass
class Job:
    id: str
    tipo: str
    condicao: str
    itens: list[ItemJob] = field(default_factory=list)
    status: StatusJob = StatusJob.PENDENTE
    mensagem: str = "Aguardando início"
    arquivo_atual: Optional[str] = None
    indice_atual: int = 0
    iniciado_em: Optional[float] = None
    finalizado_em: Optional[float] = None
    cancelar: bool = False
    contagem: dict[str, int] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)
    etapa: Optional[str] = None
    sub_progresso: Optional[dict[str, Any]] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def total(self) -> int:
        return len(self.itens)

    @property
    def concluidos(self) -> int:
        return sum(
            1 for i in self.itens if i.status in (StatusItem.OK, StatusItem.FALHA)
        )

    def atualizar_progresso(
        self,
        *,
        etapa: Optional[str] = None,
        mensagem: Optional[str] = None,
        sub_progresso: Optional[dict[str, Any]] | object = ...,
    ) -> None:
        with self._lock:
            if etapa is not None:
                self.etapa = etapa
            if mensagem is not None:
                self.mensagem = mensagem
            if sub_progresso is not ...:
                self.sub_progresso = sub_progresso  # type: ignore[assignment]

    def limpar_sub_progresso(self) -> None:
        with self._lock:
            self.sub_progresso = None
            self.etapa = None

    @property
    def percentual(self) -> float:
        if self.total == 0:
            return 100.0
        parcial = 0.0
        if self.sub_progresso:
            total_sub = self.sub_progresso.get("total") or 0
            if total_sub > 0:
                parcial = self.sub_progresso.get("concluidas", 0) / total_sub
        return round(((self.concluidos + parcial) / self.total) * 100, 1)

    @property
    def percentual_sub(self) -> Optional[float]:
        if not self.sub_progresso:
            return None
        total = self.sub_progresso.get("total") or 0
        if total <= 0:
            return None
        concluidas = self.sub_progresso.get("concluidas", 0)
        return round((concluidas / total) * 100, 1)

    @property
    def duracao_s(self) -> float:
        if self.iniciado_em is None:
            return 0.0
        fim = self.finalizado_em or time.perf_counter()
        return round(fim - self.iniciado_em, 2)

    @property
    def eta_s(self) -> Optional[float]:
        if self.concluidos == 0 or self.iniciado_em is None:
            return None
        media = self.duracao_s / self.concluidos
        restantes = self.total - self.concluidos
        return round(media * restantes, 1)

    def adicionar_log(self, texto: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{ts}] {texto}")
        if len(self.logs) > 80:
            self.logs = self.logs[-80:]

    def para_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tipo": self.tipo,
            "condicao": self.condicao,
            "status": self.status.value,
            "mensagem": self.mensagem,
            "arquivo_atual": self.arquivo_atual,
            "indice_atual": self.indice_atual,
            "etapa": self.etapa,
            "sub_progresso": dict(self.sub_progresso) if self.sub_progresso else None,
            "percentual_sub": self.percentual_sub,
            "total": self.total,
            "concluidos": self.concluidos,
            "percentual": self.percentual,
            "duracao_s": self.duracao_s,
            "eta_s": self.eta_s,
            "contagem": dict(self.contagem),
            "itens": [i.para_dict() for i in self.itens],
            "logs": list(self.logs),
        }


class GerenciadorJobs:
    """Fila de jobs em memória (uso local)."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def criar_lote(self, condicao: str, arquivos: list[str]) -> Job:
        job_id = uuid.uuid4().hex[:12]
        job = Job(
            id=job_id,
            tipo="lote",
            condicao=condicao.upper(),
            itens=[ItemJob(arquivo=n) for n in arquivos],
            mensagem=f"{len(arquivos)} PDF(s) na fila",
        )
        with self._lock:
            self._jobs[job_id] = job
        return job

    def criar_unitario(self, arquivo: str, condicao: str) -> Job:
        job_id = uuid.uuid4().hex[:12]
        job = Job(
            id=job_id,
            tipo="unitario",
            condicao=condicao.upper(),
            itens=[ItemJob(arquivo=arquivo)],
            mensagem=f"Processando {arquivo}",
        )
        with self._lock:
            self._jobs[job_id] = job
        return job

    def obter(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def tem_job_ativo(self) -> bool:
        with self._lock:
            return any(
                j.status in (StatusJob.PENDENTE, StatusJob.EXECUTANDO)
                for j in self._jobs.values()
            )

    def cancelar(self, job_id: str) -> bool:
        job = self.obter(job_id)
        if not job or job.status != StatusJob.EXECUTANDO:
            return False
        job.cancelar = True
        job.mensagem = "Cancelamento solicitado - aguardando parada"
        job.adicionar_log("Cancelamento solicitado")
        return True

    def executar_em_thread(
        self,
        job: Job,
        worker: Callable[[Job], None],
    ) -> None:
        def _run() -> None:
            try:
                worker(job)
            except Exception as exc:  # noqa: BLE001
                job.status = StatusJob.ERRO
                job.mensagem = str(exc)
                job.adicionar_log(f"Erro fatal: {exc}")
            finally:
                job.finalizado_em = time.perf_counter()

        threading.Thread(target=_run, daemon=True).start()


gerenciador = GerenciadorJobs()
