"""
AutoClickPersonal — app de mouse automático com interface gráfica.

Funciona em cima de QUALQUER aplicativo, porque simula o clique em nível de
sistema operacional (biblioteca pynput), não dentro de uma janela específica.

Recursos:
- Velocidade do clique (intervalo entre cliques, em milissegundos)
- Quantidade de cliques (um número fixo, ou infinito até você mandar parar)
- Tempo total de execução (roda por X segundos e para sozinho)
- Botão do mouse: esquerdo, direito ou meio
- Posição do clique: onde o cursor estiver, ou uma posição fixa capturada
- Atalho de teclado GLOBAL pra iniciar/parar (F6) e capturar posição (F7)
- Tema Dark Purple (fundo roxo escuro, botões laranja neon) e tema Light
  (fundo cinza, botões roxo escuro), alternável por um switch
- Interface responsiva: a janela pode ser redimensionada, e o conteúdo
  rola (scroll) se ficar menor que o necessário, em vez de cortar botões

Como instalar as dependências (uma vez só):
    pip install customtkinter pynput pillow

Como rodar:
    python autoclickpersonal.py

Observação (macOS): o sistema pode pedir permissão de "Acessibilidade"
pra esse script controlar o mouse/teclado. Vá em Ajustes do Sistema >
Privacidade e Segurança > Acessibilidade, e libere o Terminal (ou o app
que você usar pra rodar o Python).
"""

import threading
import time

import customtkinter as ctk
from pynput import keyboard
from pynput.mouse import Button, Controller as MouseController


# ---------------------------------------------------------------------------
# Paleta de cores dos dois temas
# ---------------------------------------------------------------------------

THEMES = {
    "dark": {
        "bg": "#170826",           # roxo bem escuro, fundo da janela
        "panel": "#241238",        # roxo um pouco mais claro, fundo dos cartões
        "entry_bg": "#2f1a4a",     # fundo dos campos de entrada
        "text": "#f5ecff",         # texto principal, quase branco
        "subtext": "#c6a9f2",      # texto secundário, roxo claro
        "accent": "#ff7a1a",       # laranja neon — botões principais
        "accent_hover": "#ff9a4d", # laranja neon mais claro, ao passar o mouse
        "accent_text": "#170826",  # texto em cima dos botões laranja (escuro, contraste)
        "border": "#ff7a1a",       # borda neon dos cartões
        "stop": "#ff3b3b",         # vermelho pro botão de parar
        "stop_hover": "#ff6b6b",
    },
    "light": {
        "bg": "#dcdcdc",           # cinza claro, fundo da janela
        "panel": "#c9c9c9",        # cinza um pouco mais escuro, fundo dos cartões
        "entry_bg": "#f0f0f0",     # fundo dos campos de entrada
        "text": "#1c1c1c",         # texto principal, quase preto
        "subtext": "#4a4a4a",      # texto secundário, cinza escuro
        "accent": "#4b0f82",       # roxo escuro — botões principais
        "accent_hover": "#6a1fae",
        "accent_text": "#ffffff",  # texto em cima dos botões roxos (branco, contraste)
        "border": "#4b0f82",
        "stop": "#8c1a1a",
        "stop_hover": "#b23333",
    },
}


# ---------------------------------------------------------------------------
# Constantes de espaçamento — todas as "distâncias" da interface ficam
# centralizadas aqui, pra você conseguir ajustar em UM lugar só, sem caçar
# número espalhado pelo código. Cada uma diz exatamente qual respiro controla.
# ---------------------------------------------------------------------------

ESPACO_PADRAO_CARTAO = 8    # distância vertical ENTRE cada cartão (Velocidade, Quantidade, Tempo, Extras)
ESPACO_TOPO_ATALHO = 6      # distância entre os botões Iniciar/Parar e o texto do atalho (F6)
ESPACO_BASE_BOTOES = 20     # distância entre o texto de Status (última linha) e a borda de baixo da janela


# ---------------------------------------------------------------------------
# O "motor" do auto clicker: roda numa thread separada, pra não travar a
# interface gráfica enquanto está clicando.
# ---------------------------------------------------------------------------

class MotorDeClique:
    def __init__(self, ao_atualizar_status, ao_parar):
        self.mouse = MouseController()
        self.rodando = False
        self._thread = None
        self._evento_parar = threading.Event()
        self.ao_atualizar_status = ao_atualizar_status  # callback(cliques_feitos)
        self.ao_parar = ao_parar                        # callback() chamado quando termina sozinho

    def iniciar(self, intervalo_segundos, botao, limite_cliques, limite_tempo,
                usar_posicao_fixa, posicao_fixa):
        if self.rodando:
            return

        self.rodando = True
        self._evento_parar.clear()
        self._thread = threading.Thread(
            target=self._loop_de_clique,
            args=(intervalo_segundos, botao, limite_cliques, limite_tempo,
                  usar_posicao_fixa, posicao_fixa),
            daemon=True,  # a thread morre sozinha se o programa fechar
        )
        self._thread.start()

    def parar(self):
        self.rodando = False
        self._evento_parar.set()

    def _loop_de_clique(self, intervalo_segundos, botao, limite_cliques, limite_tempo,
                         usar_posicao_fixa, posicao_fixa):
        cliques_feitos = 0
        hora_inicio = time.monotonic()

        if usar_posicao_fixa:
            self.mouse.position = posicao_fixa

        while not self._evento_parar.is_set():
            # Verifica se atingiu o limite de tempo de execução
            if limite_tempo is not None and (time.monotonic() - hora_inicio) >= limite_tempo:
                break

            # Verifica se atingiu o número máximo de cliques
            if limite_cliques is not None and cliques_feitos >= limite_cliques:
                break

            self.mouse.click(botao)
            cliques_feitos += 1
            self.ao_atualizar_status(cliques_feitos)

            # Espera o intervalo entre cliques, mas checando a cada pedacinho
            # se mandaram parar — assim o "Parar" responde na hora, mesmo
            # com intervalos longos, em vez de esperar o intervalo inteiro.
            self._evento_parar.wait(timeout=intervalo_segundos)

        self.rodando = False
        self.ao_parar(cliques_feitos)


# ---------------------------------------------------------------------------
# A janela principal
# ---------------------------------------------------------------------------

class AutoClickerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.tema_atual = "dark"
        self.widgets_com_tema = []  # lista de (widget, tipo) pra recolorir ao trocar de tema

        self.motor = MotorDeClique(
            ao_atualizar_status=self._atualizar_status_thread_segura,
            ao_parar=self._quando_parar_sozinho_thread_segura,
        )

        self.posicao_fixa_capturada = None  # (x, y) ou None

        self.title("AutoClickPersonal")
        self.geometry("440x740")
        self.minsize(380, 400)   # abaixo disso, o conteúdo passa a rolar em vez de cortar
        self.resizable(True, True)

        # Ícone da janela — gere "icone.ico" com o script gerar_icone.py (mesma pasta)
        # antes de rodar, ou o app abre normalmente sem ícone customizado.
        try:
            self.iconbitmap("Icone.ico")
        except Exception:
            pass

        self._montar_interface()
        self._aplicar_tema(self.tema_atual)
        self._configurar_atalho_global()

        # Garante que a thread de clique e o listener de teclado são
        # encerrados corretamente ao fechar a janela.
        self.protocol("WM_DELETE_WINDOW", self._ao_fechar)

    # ------------------------------------------------------------------
    # Montagem da interface
    # ------------------------------------------------------------------

    def _montar_interface(self):
        # CTkScrollableFrame em vez de um CTkFrame comum: assim, se a janela
        # for redimensionada pra um tamanho menor que o conteúdo, aparece uma
        # barra de rolagem em vez de cortar os botões fora da área visível.
        self.container = ctk.CTkScrollableFrame(self, corner_radius=0)
        self.container.pack(fill="both", expand=True)
        self.widgets_com_tema.append((self.container, "bg"))

        # --- Cabeçalho: título + switch de tema ---
        cabecalho = ctk.CTkFrame(self.container, fg_color="transparent")
        cabecalho.pack(fill="x", padx=20, pady=(20, 10))

        self.label_titulo = ctk.CTkLabel(
            cabecalho, text="AUTOCLICKPERSONAL", font=ctk.CTkFont(size=20, weight="bold")
        )
        self.label_titulo.pack(side="left")
        self.widgets_com_tema.append((self.label_titulo, "text"))

        self.switch_tema = ctk.CTkSwitch(
            # O texto ao lado do switch mostra o NOME DO MODO CONTRÁRIO ao atual
            # (ex: se está no escuro, o texto convida pro "Tema claro", e vice-versa)
            # — ver _atualizar_texto_switch(), chamada logo abaixo e sempre que o
            # switch muda de estado.
            cabecalho, text="", command=self._alternar_tema, onvalue=1, offvalue=0
        )
        self.switch_tema.select()  # começa no tema escuro
        self.switch_tema.pack(side="right")
        self.widgets_com_tema.append((self.switch_tema, "switch"))
        self._atualizar_texto_switch()  # define o texto inicial ("Tema claro", já que começa no escuro)

        # --- Cartão: Velocidade do clique ---
        cartao_velocidade = self._criar_cartao("Velocidade do clique")
        self.entry_intervalo_ms = self._criar_campo_numerico(
            cartao_velocidade, "Intervalo entre cliques (ms)", valor_padrao="100"
        )
        self.label_cps = ctk.CTkLabel(cartao_velocidade, text="≈ 10.0 cliques por segundo",
                                       font=ctk.CTkFont(size=12))
        self.label_cps.pack(anchor="w", padx=15, pady=(0, 10))
        self.widgets_com_tema.append((self.label_cps, "subtext"))
        self.entry_intervalo_ms.bind("<KeyRelease>", lambda e: self._recalcular_cps())

        # --- Cartão: Quantidade de cliques ---
        cartao_quantidade = self._criar_cartao("Quantidade de cliques")
        self.var_modo_quantidade = ctk.StringVar(value="infinito")

        linha_infinito = ctk.CTkFrame(cartao_quantidade, fg_color="transparent")
        linha_infinito.pack(fill="x", padx=15, pady=(5, 2))
        self.radio_infinito = ctk.CTkRadioButton(
            linha_infinito, text="Sem limite (clica até você mandar parar)",
            variable=self.var_modo_quantidade, value="infinito",
            command=self._atualizar_estado_campo_quantidade,
        )
        self.radio_infinito.pack(anchor="w")
        self.widgets_com_tema.append((self.radio_infinito, "radio"))

        linha_fixo = ctk.CTkFrame(cartao_quantidade, fg_color="transparent")
        linha_fixo.pack(fill="x", padx=15, pady=(2, 10))
        self.radio_quantidade_fixa = ctk.CTkRadioButton(
            linha_fixo, text="Parar após:", variable=self.var_modo_quantidade,
            value="fixo", command=self._atualizar_estado_campo_quantidade,
        )
        self.radio_quantidade_fixa.pack(side="left")
        self.widgets_com_tema.append((self.radio_quantidade_fixa, "radio"))

        self.entry_quantidade = ctk.CTkEntry(linha_fixo, width=80, placeholder_text="100")
        self.entry_quantidade.pack(side="left", padx=(10, 5))
        self.widgets_com_tema.append((self.entry_quantidade, "entry"))
        label_unidade_cliques = ctk.CTkLabel(linha_fixo, text="cliques")
        label_unidade_cliques.pack(side="left")
        self.widgets_com_tema.append((label_unidade_cliques, "text"))

        self._atualizar_estado_campo_quantidade()

        # --- Cartão: Tempo de execução ---
        cartao_tempo = self._criar_cartao("Tempo de execução")
        self.var_modo_tempo = ctk.StringVar(value="ilimitado")

        linha_tempo_livre = ctk.CTkFrame(cartao_tempo, fg_color="transparent")
        linha_tempo_livre.pack(fill="x", padx=15, pady=(5, 2))
        self.radio_tempo_ilimitado = ctk.CTkRadioButton(
            linha_tempo_livre, text="Sem limite de tempo",
            variable=self.var_modo_tempo, value="ilimitado",
            command=self._atualizar_estado_campo_tempo,
        )
        self.radio_tempo_ilimitado.pack(anchor="w")
        self.widgets_com_tema.append((self.radio_tempo_ilimitado, "radio"))

        linha_tempo_fixo = ctk.CTkFrame(cartao_tempo, fg_color="transparent")
        linha_tempo_fixo.pack(fill="x", padx=15, pady=(2, 10))
        self.radio_tempo_fixo = ctk.CTkRadioButton(
            linha_tempo_fixo, text="Rodar por:", variable=self.var_modo_tempo,
            value="fixo", command=self._atualizar_estado_campo_tempo,
        )
        self.radio_tempo_fixo.pack(side="left")
        self.widgets_com_tema.append((self.radio_tempo_fixo, "radio"))

        self.entry_tempo_segundos = ctk.CTkEntry(linha_tempo_fixo, width=80, placeholder_text="30")
        self.entry_tempo_segundos.pack(side="left", padx=(10, 5))
        self.widgets_com_tema.append((self.entry_tempo_segundos, "entry"))
        label_unidade_segundos = ctk.CTkLabel(linha_tempo_fixo, text="segundos")
        label_unidade_segundos.pack(side="left")
        self.widgets_com_tema.append((label_unidade_segundos, "text"))

        self._atualizar_estado_campo_tempo()

        # --- Cartão: Botão do mouse + posição ---
        cartao_extra = self._criar_cartao("Configurações extras")

        linha_botao_mouse = ctk.CTkFrame(cartao_extra, fg_color="transparent")
        linha_botao_mouse.pack(fill="x", padx=15, pady=(5, 8))
        label_botao_mouse = ctk.CTkLabel(linha_botao_mouse, text="Botão do mouse:")
        label_botao_mouse.pack(side="left")
        self.widgets_com_tema.append((label_botao_mouse, "text"))
        self.combo_botao_mouse = ctk.CTkOptionMenu(
            linha_botao_mouse, values=["Esquerdo", "Direito", "Meio"]
        )
        self.combo_botao_mouse.pack(side="left", padx=10)
        self.widgets_com_tema.append((self.combo_botao_mouse, "option"))

        self.var_posicao = ctk.StringVar(value="atual")
        self.radio_posicao_atual = ctk.CTkRadioButton(
            cartao_extra, text="Clicar onde o cursor estiver",
            variable=self.var_posicao, value="atual",
        )
        self.radio_posicao_atual.pack(anchor="w", padx=15, pady=(2, 2))
        self.widgets_com_tema.append((self.radio_posicao_atual, "radio"))

        linha_posicao_fixa = ctk.CTkFrame(cartao_extra, fg_color="transparent")
        linha_posicao_fixa.pack(fill="x", padx=15, pady=(2, 12))
        self.radio_posicao_fixa = ctk.CTkRadioButton(
            linha_posicao_fixa, text="Posição fixa:", variable=self.var_posicao, value="fixa",
        )
        self.radio_posicao_fixa.pack(side="left")
        self.widgets_com_tema.append((self.radio_posicao_fixa, "radio"))

        self.label_posicao_capturada = ctk.CTkLabel(linha_posicao_fixa, text="(nenhuma)")
        self.label_posicao_capturada.pack(side="left", padx=10)
        self.widgets_com_tema.append((self.label_posicao_capturada, "subtext"))

        self.botao_capturar_posicao = ctk.CTkButton(
            linha_posicao_fixa, text="Capturar (F7)", width=110,
            command=self._capturar_posicao_fixa,
        )
        self.botao_capturar_posicao.pack(side="left")
        self.widgets_com_tema.append((self.botao_capturar_posicao, "accent_button"))
        # ^ FIM do cartão "Configurações extras".

        # =====================================================================
        # >>> Ordem do rodapé (de cima pra baixo): Botões Iniciar/Parar,
        # >>> depois o texto do atalho global, depois o Status.
        # >>> A distância até aqui é só ESPACO_PADRAO_CARTAO (mesma distância
        # >>> usada entre os cartões) — sem espaçador elástico, então o rodapé
        # >>> fica sempre colado nos cartões, não importa o tamanho da janela.
        # =====================================================================

        # --- Botões Iniciar / Parar (logo abaixo dos cartões) ---
        linha_botoes = ctk.CTkFrame(self.container, fg_color="transparent")
        linha_botoes.pack(pady=(ESPACO_PADRAO_CARTAO, 12))

        self.botao_iniciar = ctk.CTkButton(
            linha_botoes, text="▶  INICIAR", width=160, height=44, corner_radius=10,
            font=ctk.CTkFont(size=15, weight="bold"), command=self._iniciar_clique,
        )
        self.botao_iniciar.pack(side="left", padx=8)
        self.widgets_com_tema.append((self.botao_iniciar, "accent_button"))

        self.botao_parar = ctk.CTkButton(
            linha_botoes, text="■  PARAR", width=160, height=44, corner_radius=10,
            font=ctk.CTkFont(size=15, weight="bold"), command=self._parar_clique,
            state="disabled",
        )
        self.botao_parar.pack(side="left", padx=8)
        self.widgets_com_tema.append((self.botao_parar, "stop_button"))

        # --- Atalho global + status (agora abaixo dos botões) ---
        self.label_atalho = ctk.CTkLabel(
            self.container, text="Atalho global pra Iniciar/Parar:  F6",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.label_atalho.pack(pady=(ESPACO_TOPO_ATALHO, 0))
        self.widgets_com_tema.append((self.label_atalho, "subtext"))

        self.label_dica_atalho = ctk.CTkLabel(
            self.container,
            text="(funciona mesmo com essa janela sem foco — foque no outro app e aperte F6)",
            font=ctk.CTkFont(size=11),
        )
        self.label_dica_atalho.pack(pady=(0, 8))
        self.widgets_com_tema.append((self.label_dica_atalho, "subtext"))

        self.label_status = ctk.CTkLabel(
            self.container, text="Status: parado", font=ctk.CTkFont(size=14, weight="bold")
        )
        self.label_status.pack(pady=(0, ESPACO_BASE_BOTOES))
        self.widgets_com_tema.append((self.label_status, "text"))

        self._recalcular_cps()

    def _criar_cartao(self, titulo):
        cartao = ctk.CTkFrame(self.container, corner_radius=12, border_width=1)
        cartao.pack(fill="x", padx=20, pady=ESPACO_PADRAO_CARTAO)
        self.widgets_com_tema.append((cartao, "panel"))

        label = ctk.CTkLabel(cartao, text=titulo, font=ctk.CTkFont(size=14, weight="bold"))
        label.pack(anchor="w", padx=15, pady=(10, 5))
        self.widgets_com_tema.append((label, "text"))

        return cartao

    def _criar_campo_numerico(self, cartao, rotulo, valor_padrao):
        linha = ctk.CTkFrame(cartao, fg_color="transparent")
        linha.pack(fill="x", padx=15, pady=(0, 5))

        label = ctk.CTkLabel(linha, text=rotulo)
        label.pack(side="left")
        self.widgets_com_tema.append((label, "subtext"))

        entry = ctk.CTkEntry(linha, width=100, corner_radius=8)
        entry.insert(0, valor_padrao)
        entry.pack(side="right")
        self.widgets_com_tema.append((entry, "entry"))

        return entry

    # ------------------------------------------------------------------
    # Tema (dark purple / light)
    # ------------------------------------------------------------------

    def _alternar_tema(self):
        self.tema_atual = "dark" if self.switch_tema.get() == 1 else "light"
        self._atualizar_texto_switch()
        self._aplicar_tema(self.tema_atual)

    def _atualizar_texto_switch(self):
        """O texto ao lado do switch sempre nomeia o modo CONTRÁRIO ao atual —
        é o convite pra pra onde você vai, não uma etiqueta de onde já está."""
        texto_modo_contrario = "Tema claro" if self.tema_atual == "dark" else "Tema escuro"
        self.switch_tema.configure(text=texto_modo_contrario)

    def _aplicar_tema(self, nome_tema):
        cores = THEMES[nome_tema]
        self.configure(fg_color=cores["bg"])

        for widget, tipo in self.widgets_com_tema:
            try:
                if tipo == "bg":
                    widget.configure(fg_color=cores["bg"])
                elif tipo == "panel":
                    widget.configure(fg_color=cores["panel"], border_color=cores["border"])
                elif tipo == "text":
                    widget.configure(text_color=cores["text"])
                elif tipo == "subtext":
                    widget.configure(text_color=cores["subtext"])
                elif tipo == "entry":
                    widget.configure(fg_color=cores["entry_bg"], text_color=cores["text"],
                                      border_color=cores["accent"])
                elif tipo == "radio":
                    widget.configure(text_color=cores["text"], fg_color=cores["accent"],
                                      hover_color=cores["accent_hover"], border_color=cores["accent"])
                elif tipo == "switch":
                    widget.configure(text_color=cores["text"], progress_color=cores["accent"],
                                      button_color=cores["accent"], button_hover_color=cores["accent_hover"])
                elif tipo == "option":
                    widget.configure(fg_color=cores["accent"], button_color=cores["accent"],
                                      button_hover_color=cores["accent_hover"], text_color=cores["accent_text"])
                elif tipo == "accent_button":
                    widget.configure(fg_color=cores["accent"], hover_color=cores["accent_hover"],
                                      text_color=cores["accent_text"])
                elif tipo == "stop_button":
                    widget.configure(fg_color=cores["stop"], hover_color=cores["stop_hover"],
                                      text_color="#ffffff")
            except Exception:
                # Alguns widgets podem não aceitar todos os parâmetros dependendo
                # da versão do customtkinter — ignora silenciosamente esse caso.
                pass

    # ------------------------------------------------------------------
    # Interações de UI
    # ------------------------------------------------------------------

    def _recalcular_cps(self):
        try:
            intervalo_ms = float(self.entry_intervalo_ms.get())
            if intervalo_ms <= 0:
                raise ValueError
            cps = 1000.0 / intervalo_ms
            self.label_cps.configure(text=f"≈ {cps:.1f} cliques por segundo")
        except ValueError:
            self.label_cps.configure(text="Intervalo inválido")

    def _atualizar_estado_campo_quantidade(self):
        estado = "normal" if self.var_modo_quantidade.get() == "fixo" else "disabled"
        self.entry_quantidade.configure(state=estado)

    def _atualizar_estado_campo_tempo(self):
        estado = "normal" if self.var_modo_tempo.get() == "fixo" else "disabled"
        self.entry_tempo_segundos.configure(state=estado)

    def _capturar_posicao_fixa(self):
        # Captura a posição ATUAL do cursor no instante do clique do botão.
        # (Pra capturar em cima de outro app, use o atalho F7 em vez do botão.)
        mouse_temp = MouseController()
        x, y = mouse_temp.position
        self.posicao_fixa_capturada = (int(x), int(y))
        self.var_posicao.set("fixa")
        self.label_posicao_capturada.configure(text=f"({int(x)}, {int(y)})")

    # ------------------------------------------------------------------
    # Iniciar / parar o clique
    # ------------------------------------------------------------------

    def _ler_configuracoes(self):
        """Lê e valida tudo que está nos campos. Retorna None se algo estiver inválido."""
        try:
            intervalo_ms = float(self.entry_intervalo_ms.get())
            if intervalo_ms <= 0:
                raise ValueError("O intervalo precisa ser maior que zero.")
        except ValueError:
            self.label_status.configure(text="Status: intervalo de clique inválido")
            return None

        limite_cliques = None
        if self.var_modo_quantidade.get() == "fixo":
            try:
                limite_cliques = int(self.entry_quantidade.get())
                if limite_cliques <= 0:
                    raise ValueError
            except ValueError:
                self.label_status.configure(text="Status: quantidade de cliques inválida")
                return None

        limite_tempo = None
        if self.var_modo_tempo.get() == "fixo":
            try:
                limite_tempo = float(self.entry_tempo_segundos.get())
                if limite_tempo <= 0:
                    raise ValueError
            except ValueError:
                self.label_status.configure(text="Status: tempo de execução inválido")
                return None

        mapa_botoes = {"Esquerdo": Button.left, "Direito": Button.right, "Meio": Button.middle}
        botao = mapa_botoes[self.combo_botao_mouse.get()]

        usar_posicao_fixa = self.var_posicao.get() == "fixa"
        if usar_posicao_fixa and self.posicao_fixa_capturada is None:
            self.label_status.configure(text="Status: capture uma posição fixa primeiro (F7)")
            return None

        return {
            "intervalo_segundos": intervalo_ms / 1000.0,
            "botao": botao,
            "limite_cliques": limite_cliques,
            "limite_tempo": limite_tempo,
            "usar_posicao_fixa": usar_posicao_fixa,
            "posicao_fixa": self.posicao_fixa_capturada,
        }

    def _iniciar_clique(self):
        if self.motor.rodando:
            return

        config = self._ler_configuracoes()
        if config is None:
            return

        self.motor.iniciar(**config)
        self.botao_iniciar.configure(state="disabled")
        self.botao_parar.configure(state="normal")
        self.label_status.configure(text="Status: rodando... (0 cliques)")

    def _parar_clique(self):
        self.motor.parar()
        self.botao_iniciar.configure(state="normal")
        self.botao_parar.configure(state="disabled")

    def _alternar_iniciar_parar(self):
        """Chamada pelo atalho global de teclado (F6)."""
        if self.motor.rodando:
            self._parar_clique()
        else:
            self._iniciar_clique()

    # ------------------------------------------------------------------
    # Callbacks do motor de clique (rodam numa thread diferente da GUI!
    # por isso usamos `self.after(0, ...)` pra devolver a atualização
    # pra thread principal, que é a única que pode mexer nos widgets)
    # ------------------------------------------------------------------

    def _atualizar_status_thread_segura(self, cliques_feitos):
        self.after(0, lambda: self.label_status.configure(
            text=f"Status: rodando... ({cliques_feitos} cliques)"
        ))

    def _quando_parar_sozinho_thread_segura(self, cliques_feitos):
        def atualizar():
            self.botao_iniciar.configure(state="normal")
            self.botao_parar.configure(state="disabled")
            self.label_status.configure(text=f"Status: concluído ({cliques_feitos} cliques)")
        self.after(0, atualizar)

    # ------------------------------------------------------------------
    # Atalho de teclado global (funciona mesmo com a janela sem foco)
    # ------------------------------------------------------------------

    def _configurar_atalho_global(self):
        def ao_apertar_f6():
            self._alternar_iniciar_parar()

        def ao_apertar_f7():
            self.after(0, self._capturar_posicao_fixa)

        self._listener_teclado = keyboard.GlobalHotKeys({
            "<f6>": ao_apertar_f6,
            "<f7>": ao_apertar_f7,
        })
        self._listener_teclado.start()

    def _ao_fechar(self):
        self.motor.parar()
        try:
            self._listener_teclado.stop()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    app = AutoClickerApp()
    app.mainloop()