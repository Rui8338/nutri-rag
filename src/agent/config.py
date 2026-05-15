"""
Configuração de uma execução do agente.

Existe para tornar a experiência um parâmetro explícito em vez de uma
edição de código. Antes: o modelo era uma constante de módulo (duplicada)
no loop.py e outra no router.py — três fontes de verdade. Agora: um objecto
passado a run_agent, serializável para o config.json do eval.

O default reproduz exactamente o comportamento pré-refactor:
3B em todas as chamadas, pre-router ligado.
"""

from dataclasses import dataclass, asdict


# Modelo validado no Dia 1 (gate de tool calling: Qwen 2.5 3B > Llama 3.2 3B)
DEFAULT_MODEL = "qwen2.5:3b-instruct"


@dataclass
class AgentConfig:
    """
    Configuração de uma execução do agente.

    Campos:
        model: modelo Ollama para as chamadas do loop (decisão + geração).
        rewriter_model: modelo Ollama para o query rewriter do RAG.
            Separado de `model` de propósito — a Semana 3 pode querer o
            7B na decisão mas manter o rewriter no 3B por latência.
        pre_router_enabled: se False, desliga o pre-router rule-based e
            o LLM decide sozinho entre as 4 tools. Knob de ablation.
    """
    model: str = DEFAULT_MODEL
    rewriter_model: str = DEFAULT_MODEL
    pre_router_enabled: bool = True

    def to_dict(self) -> dict:
        """Serializa para gravar no config.json do eval — registo fiel da execução."""
        return asdict(self)


# Instância default reutilizável — para run_agent(query) sem config explícito.
DEFAULT_CONFIG = AgentConfig()