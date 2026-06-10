import discord
from typing import List, Optional
import logging
import unicodedata

import config
from storage import dados, guardar_dados, livros_tbr_flat
from utils import safe_custom_id, estrelas_para_texto, nota_valida, livro_ja_lido, hoje_str, parsear_livro
from ai import obter_info_livro, extrair_texto_da_imagem, validar_resposta_ia_pydantic, validar_resposta_ia, ai_json_com_retry
from models import RespostaSerie
from images import desenhar_calendario_leituras

logger = logging.getLogger('CosmoBot')


class BotaoSugestao(discord.ui.Button):
    def __init__(self, titulo_livro: str):
        super().__init__(label=f"➕ TBR: {titulo_livro[:55]}", style=discord.ButtonStyle.primary, custom_id=safe_custom_id(f"tbr_add::{titulo_livro[:80]}"))
        self.titulo_livro = titulo_livro
    async def callback(self, interaction: discord.Interaction):
        if self.titulo_livro.lower() in [l.lower() for l in livros_tbr_flat()]:
            await interaction.response.send_message(f"🤔 *{self.titulo_livro}* já está na tua TBR.", ephemeral=True)
            return
        dados["tbr_por_mes"]["Geral"].append(self.titulo_livro)
        guardar_dados()
        self.disabled = True
        self.style = discord.ButtonStyle.success
        self.label = "✅ Adicionado"
        await interaction.response.edit_message(view=self.view)
        await interaction.followup.send(f"📦 **{self.titulo_livro}** foi adicionado à lista **Geral**.", ephemeral=True)


class BotaoMarcarSugestoes(discord.ui.Button):
    def __init__(self, titulos: List[str]):
        super().__init__(label="✅ Já vi estas sugestões", style=discord.ButtonStyle.secondary, custom_id=safe_custom_id(f"sugestoes_vistas::{hash(tuple(titulos))}"))
        self.titulos = titulos
    async def callback(self, interaction: discord.Interaction):
        vistos = {v.lower().strip() for v in dados.setdefault("sugestoes_vistas", [])}
        novos = 0
        for titulo in self.titulos:
            chave = titulo.lower().strip()
            if chave not in vistos:
                dados["sugestoes_vistas"].append(titulo)
                vistos.add(chave)
                novos += 1
        guardar_dados()
        self.disabled = True
        self.label = "✅ Sugestões arquivadas"
        await interaction.response.edit_message(view=self.view)
        await interaction.followup.send(f"📚 Arquivou **{novos}** sugestão(ões). Não voltarão a ser recomendadas.", ephemeral=True)


class ViewMarcarSugestoes(discord.ui.View):
    def __init__(self, titulos: List[str]):
        super().__init__(timeout=None)
        if titulos:
            self.add_item(BotaoMarcarSugestoes(titulos))


class ViewSugestoes(discord.ui.View):
    def __init__(self, livros_sugeridos: List[str], titulos_arquivo: Optional[List[str]] = None):
        super().__init__(timeout=None)
        for livro in livros_sugeridos:
            self.add_item(BotaoSugestao(livro))
        if titulos_arquivo:
            self.add_item(BotaoMarcarSugestoes(titulos_arquivo))


class SelectAvaliacao(discord.ui.Select):
    def __init__(self, titulo_livro: str, autor_id: int):
        options = [discord.SelectOption(label=f"{n}g estrelas", value=str(n)) for n in config.NOTAS_DISPONIVEIS]
        super().__init__(placeholder="Escolhe a avaliação (0.25 a 5)", min_values=1, max_values=1, options=options, custom_id=safe_custom_id(f"avaliar::{titulo_livro[:60]}::{autor_id}"))
        self.titulo_livro = titulo_livro
        self.autor_id = autor_id
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("❌ Só quem registou este livro pode avaliá-lo por aqui.", ephemeral=True)
            return
        nota = float(self.values[0])
        for livro in dados["livros_lidos"]:
            if livro.get("titulo", "").lower().strip() == self.titulo_livro.lower().strip():
                livro["nota"] = nota
                livro["estrelas"] = estrelas_para_texto(nota)
                guardar_dados()
                break
        for item in self.view.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"🎨 Avaliação guardada para **{self.titulo_livro}**: {estrelas_para_texto(nota)}", view=self.view)


class ViewAvaliacao(discord.ui.View):
    def __init__(self, titulo_livro: str, autor_id: int):
        super().__init__(timeout=86400)
        self.add_item(SelectAvaliacao(titulo_livro, autor_id))


class ViewConfirmarDuplicado(discord.ui.View):
    def __init__(self, livro_novo: str, livro_existente: str, categoria: str, user_id: int):
        super().__init__(timeout=60)
        self.livro_novo = livro_novo
        self.livro_existente = livro_existente
        self.categoria = categoria
        self.user_id = user_id
    @discord.ui.button(label="✅ Sim, adicionar mesmo assim", style=discord.ButtonStyle.danger)
    async def confirmar_adicao(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Este menu não é para ti!", ephemeral=True)
            return
        dados["tbr_por_mes"][self.categoria].append(self.livro_novo)
        guardar_dados()
        self.disable_all_buttons()
        await interaction.response.edit_message(content=f"📅 **{self.livro_novo}** foi adicionado a **{self.categoria}** mesmo sendo similar a **{self.livro_existente}**.", view=self)
    @discord.ui.button(label="❌ Não, cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar_adicao(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Este menu não é para ti!", ephemeral=True)
            return
        self.disable_all_buttons()
        await interaction.response.edit_message(content=f"❌ Adição de **{self.livro_novo}** cancelada.", view=self)
    def disable_all_buttons(self):
        for child in self.children:
            child.disabled = True


class ViewManterSerie(discord.ui.View):
    def __init__(self, livro_atual: str, livros_serie: List[str], meses_agendados: List[str], canal_id: int):
        super().__init__(timeout=86400)
        self.livro_atual = livro_atual
        self.livros_serie = livros_serie
        self.meses_agendados = meses_agendados
    @discord.ui.button(label="✅ Sim, manter os próximos livros", style=discord.ButtonStyle.success)
    async def manter_serie(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"📚 OK! Os próximos livros da série **{self.livro_atual}** permanecem na TBR:\n" + "\n".join(f"• {livro} ({mes})" for livro, mes in zip(self.livros_serie, self.meses_agendados)), ephemeral=False)
        self.disable_all_buttons()
        await interaction.edit_original_response(view=self)
    @discord.ui.button(label="❌ Não, remover os próximos livros", style=discord.ButtonStyle.danger)
    async def remover_serie(self, interaction: discord.Interaction, button: discord.ui.Button):
        removidos = []
        for livro, mes in zip(self.livros_serie, self.meses_agendados):
            if livro in dados["tbr_por_mes"][mes]:
                dados["tbr_por_mes"][mes].remove(livro)
                removidos.append(f"• {livro} ({mes})")
        guardar_dados()
        await interaction.response.send_message(f"🗑️ Livros seguintes da série **{self.livro_atual}** foram removidos da TBR:\n" + "\n".join(removidos), ephemeral=False)
        self.disable_all_buttons()
        await interaction.edit_original_response(view=self)
    def disable_all_buttons(self):
        for child in self.children:
            child.disabled = True


class ViewConfirmarLido(discord.ui.View):
    def __init__(self, livro: str, autor: str, canal_id: int):
        super().__init__(timeout=86400)
        self.livro = livro
        self.autor = autor
        self.canal_id = canal_id
        self.livros_serie = []
        self.meses_agendados = []
    async def detetar_serie_pos_lido(self):
        prompt = f'O utilizador acabou de ler o livro "{self.livro}". Se este livro fizer parte de uma série literária conhecida, identifica os PRÓXIMOS livros da série (máximo 3) que ainda não foram lidos. Responde apenas em JSON: {{"sequencias": ["Nome do Livro 2 - Autor", ...]}}'
        resposta = await ai_json_com_retry(prompt)
        validada = validar_resposta_ia_pydantic(resposta, RespostaSerie) or validar_resposta_ia(resposta, ["sequencias"])
        sequencias = validada.get("sequencias", []) if isinstance(validada, dict) else getattr(validada, "sequencias", [])
        if not sequencias:
            return []
        livros_nao_lidos = [seq for seq in sequencias if not livro_ja_lido(seq, dados)]
        if not livros_nao_lidos:
            return []
        mes_atual = config.MESES_ORDEM[datetime.now().month - 1]
        idx_mes_atual = config.MESES_ORDEM.index(mes_atual)
        mensagens = []
        for i, prox in enumerate(livros_nao_lidos[:3]):
            mes_destino = config.MESES_ORDEM[(idx_mes_atual + 1 + i) % 12]
            if not any(prox.lower().strip() == x.lower().strip() for x in livros_tbr_flat()):
                dados["tbr_por_mes"][mes_destino].append(prox)
                self.livros_serie.append(prox)
                self.meses_agendados.append(mes_destino)
                mensagens.append(f"• **{prox}** agendado para **{mes_destino}**")
        guardar_dados()
        return mensagens
    @discord.ui.button(label="✅ Sim, marcar como lido", style=discord.ButtonStyle.success)
    async def confirmar_lido(self, interaction: discord.Interaction, button: discord.ui.Button):
        if livro_ja_lido(self.livro, dados):
            await interaction.response.send_message(f"📚 **{self.livro}** já estava registado como lido!", ephemeral=True)
            self.disable_all_buttons()
            await interaction.edit_original_response(view=self)
            return
        info = await obter_info_livro(self.livro)
        try:
            titulo_curto, autor = parsear_livro(self.livro)
        except ValueError:
            titulo_curto = self.livro
            autor = self.autor
        novo_livro = {"titulo": self.livro, "autor": autor, "estrelas": "Sem avaliação", "nota": 0.0, "genero": info.get("genero", "N/D"), "paginas": int(info.get("paginas", 0) or 0), "data_leitura": hoje_str(), "fonte_metadados": info.get("fonte", "IA"), "lc_automatico": True}
        dados["livros_lidos"].append(novo_livro)
        for lista in dados["tbr_por_mes"].values():
            for item in lista[:]:
                if item.lower().strip() == self.livro.lower().strip():
                    lista.remove(item)
                    break
                item_norm = unicodedata.normalize('NFKD', item.lower()).encode('ASCII', 'ignore').decode()
                livro_norm = unicodedata.normalize('NFKD', self.livro.lower()).encode('ASCII', 'ignore').decode()
                if item_norm == livro_norm:
                    lista.remove(item)
                    break
        from images import analisar_titulo_alfabeto
        resultado = analisar_titulo_alfabeto(titulo_curto)
        aviso_alfabeto = ""
        if resultado["status"] == "OK":
            letra = resultado["letra"]
            if dados["desafio_alfabeto"].get(letra) == config.VAZIO_ALFABETO:
                dados["desafio_alfabeto"][letra] = self.livro
                aviso_alfabeto = f"\n🔤 Letra **{letra}** conquistada no A-Z!"
        mensagens_serie = await self.detetar_serie_pos_lido()
        guardar_dados()
        resposta_msg = f"✅ **{self.livro}** foi adicionado aos lidos!{aviso_alfabeto}\n📊 Progresso anual: {len(dados['livros_lidos'])}/{config.META_ANUAL} livros.\n\n"
        if mensagens_serie:
            resposta_msg += f"🧬 **Série detetada!** Queres manter os próximos livros na TBR?\n" + "\n".join(mensagens_serie)
            await interaction.response.send_message(resposta_msg, view=ViewManterSerie(self.livro, self.livros_serie, self.meses_agendados, self.canal_id), ephemeral=False)
        else:
            resposta_msg += f"⭐ Não te esqueças de avaliar o livro com `!avaliar` ou `!reavaliar`!"
            await interaction.response.send_message(resposta_msg, ephemeral=False)
        self.disable_all_buttons()
        await interaction.edit_original_response(view=self)
    @discord.ui.button(label="❌ Não, marcar depois", style=discord.ButtonStyle.secondary)
    async def adiar_lido(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"📝 OK! Podes marcar **{self.livro}** como lido mais tarde com `!lido \"{self.livro}\"`.", ephemeral=True)
        self.disable_all_buttons()
        await interaction.edit_original_response(view=self)
    def disable_all_buttons(self):
        for child in self.children:
            child.disabled = True
