from pydantic import BaseModel, Field
from typing import List, Optional

class MetaLC(BaseModel):
    data: str = Field(..., pattern=r'^\d{2}/\d{2}/\d{4}$')
    texto: str = Field(..., min_length=1, max_length=500)

class RespostaMetas(BaseModel):
    metas: List[MetaLC] = Field(default_factory=list)
    nota: Optional[str] = Field(default="", max_length=500)

class LivroRecomendacao(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=200)
    autor: str = Field(..., min_length=1, max_length=200)
    data_publicacao: str = Field(default="Desconhecida", max_length=50)
    genero: str = Field(default="N/D", max_length=100)
    subgenero: str = Field(default="N/D", max_length=100)
    porque_ler: str = Field(..., min_length=10, max_length=500)
    link_capa: str = Field(default="", max_length=500)

class RespostaRecomendacoes(BaseModel):
    livros: List[LivroRecomendacao] = Field(default_factory=list, max_items=5)

class RespostaSerie(BaseModel):
    sequencias: List[str] = Field(default_factory=list, max_items=3)
