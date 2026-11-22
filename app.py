import io
import os
import sys
import datetime
from pathlib import Path
from contextlib import redirect_stdout

import streamlit as st

import config
from extrator import YouTubeExtractor, extrair_id_youtube
from analyzer import VideoAnalyzer, _resolver_caminhos_canonicalizacao
from vault_writer import ObsidianVaultWriter
from main import processar_um_video, carregar_historico, _resolver_caminho_historico

st.set_page_config(
    page_title="YouTube → Obsidian PKM",
    page_icon="🧠",
    layout="wide",
)


class StreamlitLogStream(io.TextIOBase):
    """Captura os prints do pipeline (Scout, Map-Reduce, Retry) e atualiza o painel em tempo real."""

    def __init__(self, placeholder):
        self.placeholder = placeholder
        self.buffer = ""

    def write(self, text: str) -> int:
        if text:
            self.buffer += text
            # Mantém as últimas 60 linhas visíveis para fluidez
            linhas = self.buffer.splitlines()[-60:]
            self.placeholder.code("\n".join(linhas), language="text")
        return len(text)

    def flush(self):
        pass


# ==============================================================================
# BARRA LATERAL: CONFIGURAÇÃO DO COFRE & OPÇÕES
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Configuração")

    vault_path = st.text_input(
        "Caminho do Vault Obsidian",
        value=str(config.DEFAULT_VAULT_PATH),
    )

    data_leitura = st.date_input(
        "Data de Leitura (Diário)",
        value=datetime.date.today(),
    )

    modo_conf_label = st.selectbox(
        "Modo de Processamento",
        options=[
            "Automático (Scout em vídeos longos)",
            "Forçar Conferência (--split)",
            "Nota Única Consolidada (--unico)",
        ],
        index=0,
    )
    mapa_modo = {
        "Automático (Scout em vídeos longos)": None,
        "Forçar Conferência (--split)": "split",
        "Nota Única Consolidada (--unico)": "unico",
    }
    modo_conferencia = mapa_modo[modo_conf_label]

    forcar = st.checkbox(
        "Forçar reprocessamento (--forcar)",
        value=False,
        help="Ignora o histórico e reanalisa vídeos já integrados no Obsidian.",
    )

    validar_links = st.checkbox(
        "Validar links externos ativos",
        value=True,
        help="Verifica em paralelo se os URLs extraídos respondem antes de gravar a nota.",
    )

    st.divider()
    st.caption(f"Modelo principal: `{config.MODELO_GEMINI}`")
    st.caption(f"Fallback: `{config.FALLBACK_MODEL}`")


# ==============================================================================
# ÁREA PRINCIPAL: ABAS DE TRABALHO
# ==============================================================================
st.title("🧠 YouTube to Obsidian Knowledge Graph")

tab_processar, tab_revisao, tab_historico = st.tabs(
    ["▶️ Processar Vídeos", "🔍 Revisão de Canonicalização", "📚 Histórico"]
)

# ------------------------------------------------------------------------------
# ABA 1: PROCESSAR URLs
# ------------------------------------------------------------------------------
with tab_processar:
    urls_texto = st.text_area(
        "Cole um ou vários URLs do YouTube (um por linha):",
        height=140,
        placeholder="https://www.youtube.com/watch?v=...\nhttps://youtu.be/...",
    )
  
    col_btn, _ = st.columns([1, 3])
    with col_btn:
        iniciar = st.button("🚀 Iniciar Extração", type="primary", use_container_width=True)

    if iniciar:
        linhas_raw = []
        for l in urls_texto.splitlines():
            l_limpa = l.strip()
            if l_limpa and not l_limpa.startswith("#"):
                # Divide por espaços e pega apenas no primeiro item (o URL limpo),
                # ignorando flags coladas à frente como --forcar ou --unico
                url_puro = l_limpa.split()[0]
                linhas_raw.append(url_puro)

# ----    
        if not linhas_raw:
            st.warning("Introduza pelo menos um URL do YouTube válido.")
        else:
            urls_validos = []
            for u in linhas_raw:
                vid = extrair_id_youtube(u)
                if vid and len(vid) == 11:
                    urls_validos.append(u)
                else:
                    st.error(f"URL inválido ignorado: `{u}`")

            if urls_validos:
                barra = st.progress(0, text="A inicializar pipeline...")
                status_box = st.empty()
                st.subheader("📡 Progresso em Tempo Real (Scout / Map-Reduce / Vault)")
                log_area = st.empty()

                extrator = YouTubeExtractor()
                analyzer = VideoAnalyzer()
                writer = ObsidianVaultWriter(vault_path, validar_links=validar_links)

                stream_logs = StreamlitLogStream(log_area)
                sucessos = 0
                with redirect_stdout(stream_logs):     # ← NOVO (substitui try/finally + sys.stdout)
                    total = len(urls_validos)
                    for idx, url in enumerate(urls_validos, 1):
                        status_box.info(f"A processar [{idx}/{total}]: `{url}`")
                        ok = processar_um_video(
                            url=url,
                            extrator=extrator,
                            analyzer=analyzer,
                            writer=writer,
                            forcar=forcar,
                            data_leitura=data_leitura.isoformat(),
                            modo_conferencia=modo_conferencia,
                            vault_path=vault_path,
                        )
                        if ok:
                            sucessos += 1
                        barra.progress(idx / total, text=f"Concluído {idx}/{total} vídeos")

                
                if sucessos == len(urls_validos):
                    status_box.success(f"🎉 Concluído! {sucessos}/{len(urls_validos)} vídeos integrados no Obsidian.")
                else:
                    status_box.warning(f"⚠️ Terminado com avisos: {sucessos}/{len(urls_validos)} vídeos processados.")


# ------------------------------------------------------------------------------
# ABA 2: REVISÃO DE CANONICALIZAÇÃO (revisao.md)
# ------------------------------------------------------------------------------
with tab_revisao:
    _, _, revisao_path = _resolver_caminhos_canonicalizacao(vault_path)
    caminho_rev = Path(revisao_path)
    st.caption(f"Ficheiro monitorizado: `{caminho_rev.resolve()}`")

    if st.button("🔄 Atualizar lista de revisão"):
        st.rerun()

    if caminho_rev.exists():
        conteudo_rev = caminho_rev.read_text(encoding="utf-8").strip()
        if conteudo_rev:
            st.markdown(conteudo_rev)
        else:
            st.success("✓ `revisao.md` está vazio — não existem pares ambíguos pendentes.")
    else:
        st.info("ℹ️ O ficheiro `revisao.md` ainda não foi criado (nenhum par ambíguo detetado até agora).")


# ------------------------------------------------------------------------------
# ABA 3: HISTÓRICO DE VÍDEOS PROCESSADOS
# ------------------------------------------------------------------------------
with tab_historico:
    caminho_hist = _resolver_caminho_historico(vault_path)
    historico = carregar_historico(caminho_hist)
    if not historico:
        st.info(f"Ainda não existem vídeos registados em `{caminho_hist.name}`.")
    else:
        st.metric("Total de Vídeos/Conferências Integrados", len(historico))
        registos = [
            {
                "ID": vid,
                "Título": info.get("titulo", "-"),
                "Canal": info.get("canal", "-"),
                "Data Leitura": info.get("data_leitura", "-"),
                "Tipo": info.get("tipo", "video"),
                "Nota": info.get("nota", "-"),
            }
            for vid, info in reversed(list(historico.items()))
        ]
        st.dataframe(registos, use_container_width=True, hide_index=True)