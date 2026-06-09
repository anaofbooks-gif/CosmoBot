from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

# ==============================================================================
# SCHEMAS PYDANTIC PARA IA
# ==============================================================================

class MetaLC(BaseModel):
    """Schema para uma meta de leitura conjunta"""
    data: str = Field(..., pattern=r'^\d{2}/\d{2}/\d{4}$')
    texto: str = Field(..., min_length=1, max_length=500)

class RespostaMetas(BaseModel):
    """Schema para resposta do !meta e !editmeta"""
    metas: List[MetaLC] = Field(default_factory=list)
    nota: Optional[str] = Field(default="", max_length=500)

class LivroRecomendacao(BaseModel):
    """Schema para um livro recomendado"""
    titulo: str = Field(..., min_length=1, max_length=200)
    autor: str = Field(..., min_length=1, max_length=200)
    data_publicacao: str = Field(default="Desconhecida", max_length=50)
    genero: str = Field(default="N/D", max_length=100)
    subgenero: str = Field(default="N/D", max_length=100)
    porque_ler: str = Field(..., min_length=10, max_length=500)
    link_capa: str = Field(default="", max_length=500)

class RespostaRecomendacoes(BaseModel):
    """Schema para resposta do !recomendar"""
    livros: List[LivroRecomendacao] = Field(default_factory=list, max_items=5)

class RespostaSerie(BaseModel):
    """Schema para deteção de séries"""
    sequencias: List[str] = Field(default_factory=list, max_items=3)

# ==============================================================================
# DATACLASSES PARA ESTADO INTERNO
# ==============================================================================

@dataclass
class Livro:
    titulo: str
    autor: str
    estrelas: str = "Sem avaliação"
    nota: float = 0.0
    genero: str = "N/D"
    paginas: int = 0
    data_leitura: str = ""
    fonte_metadados: str = "IA"

@dataclass
class LembreteMeta:
    data: str
    livro: str
    meta: str
    canal_id: int
    thread_id: Optional[int] = None
    avisado: bool = False
    tipo: str = "lc"
    autor: Optional[str] = None

@dataclass
class ReviewAndamento:
    titulo: str
    desabafos: List[str] = field(default_factory=list)
    conversas: List[str] = field(default_factory=list)
    anexos: List[str] = field(default_factory=list)
    tipo: str = "desabafo"