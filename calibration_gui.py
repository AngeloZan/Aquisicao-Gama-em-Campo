import os
import copy
import glob
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy.optimize import curve_fit
import customtkinter as ctk
from tkinter import messagebox, filedialog

# --- FUNÇÕES MATEMÁTICAS E DE PROCESSAMENTO DE ESPECTRO ---

def extrair_tempo_medio(preambulo):
    start_time_str = preambulo['START_TIME']
    start_time = datetime.strptime(start_time_str, "%m/%d/%Y %H:%M:%S")
    real_time_str = preambulo['REAL_TIME']
    real_time = float(real_time_str)
    mid_point = start_time + timedelta(seconds=(real_time / 2))
    return mid_point, real_time

def func_calibracao(calib):
    if not calib:
        raise ValueError("O dicionário de calibração está vazio!")
    canais = list(calib.keys())
    energias = list(calib.values())
    num_pontos = len(canais)

    if num_pontos == 1:
        A, C = 0.0, 0.0
        x, y = canais[0], energias[0]
        B = y / x if x != 0 else 0.0
    elif num_pontos == 2:
        C = 0.0
        coefs = np.polyfit(canais, energias, 1)
        A, B = coefs[1], coefs[0]
    else:
        x = np.array(list(calib.keys()))
        y = np.array(list(calib.values()))
        C_inv, B_inv, A_inv = np.polyfit(y, x, 2)
        B = 1 / B_inv
        A = -A_inv / B_inv - (C_inv * A_inv ** 2) / (B_inv**3)
        C = -C_inv / (B_inv**3)
    return A, B, C

def canal_para_energia(canal, calib):
    A, B, C = func_calibracao(calib)
    return A + B*canal + C*canal**2

def energia_para_canal(energia, calib):
    A, B, C = func_calibracao(calib)
    if C == 0:
        return (energia - A) / B
    delta = B**2 - 4 * C * (A - energia)
    return int((-B + np.sqrt(delta)) / (2 * C))

def extrair_ROIs(data, ROIs, calibracao):
    output = []
    for canal_inicial, canal_final in ROIs:
        energia_inicial = canal_para_energia(canal_inicial, calibracao)
        energia_final = canal_para_energia(canal_final, calibracao)
        contagem_bruta = sum(data[canal_inicial:canal_final+1])
        output.append((canal_inicial, canal_final, energia_inicial, energia_final, contagem_bruta))
    return output

def extrair_totais(data, calibracao, energia_min, energia_max):
    espectro_completo = sum(data)
    canal_inicial = energia_para_canal(energia_min, calibracao)
    canal_final = energia_para_canal(energia_max, calibracao)
    contagem_total = sum(data[canal_inicial:canal_final+1])
    return (contagem_total, espectro_completo)


# --- INTERFACE GRÁFICA ---

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class CalibradorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Análise e Calibração de Espectros Gama")
        self.geometry("650x750")
        self.resizable(False, False)

        # Variáveis globais separadas por aba
        self.PASTA_ESPECTROS_CALIB = ""
        self.PASTA_ESPECTROS_GPS = ""
        self.PASTA_SOMADOS = ""
        self.PASTA_ESPECTROS_CALIBRADOS = ""
        self.ARQUIVO_GPS = ""

        # Comando de validação para permitir apenas números
        self.vcmd = (self.register(self.validar_numero), '%P')

        self.criar_interface()

    def validar_numero(self, valor_novo):
        """Permite a inserção apenas se for um dígito numérico ou se o campo ficar vazio (para apagar)."""
        if valor_novo.isdigit() or valor_novo == "":
            return True
        return False

    def criar_interface(self):
        # Criação das abas
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=20, pady=20)

        self.tab_calib = self.tabview.add("1. Calibração")
        self.tab_gps = self.tabview.add("2. GPS e ROIs")

        self.construir_aba_calibracao()
        self.construir_aba_gps()

    def construir_aba_calibracao(self):
        # ---------------- SELEÇÃO DE PASTA (CALIBRAÇÃO) ----------------
        self.frame_pasta_calib = ctk.CTkFrame(self.tab_calib)
        self.frame_pasta_calib.pack(pady=5, padx=10, fill="x")
        
        self.btn_selecionar_calib = ctk.CTkButton(self.frame_pasta_calib, text="Selecionar Pasta de Espectros (.mca)", command=self.selecionar_pasta_calib)
        self.btn_selecionar_calib.pack(pady=(10, 5))
        
        self.label_caminho_calib = ctk.CTkLabel(self.frame_pasta_calib, text="Nenhuma pasta selecionada para calibração", text_color="gray", wraplength=550)
        self.label_caminho_calib.pack(pady=(0, 10))

        # ---------------- PASSO 1: SOMAR ----------------
        self.frame_passo2 = ctk.CTkFrame(self.tab_calib)
        self.frame_passo2.pack(pady=10, padx=10, fill="x")

        self.label_passo2 = ctk.CTkLabel(self.frame_passo2, text="Passo 1: Somar Espectros", font=ctk.CTkFont(size=14, weight="bold"))
        self.label_passo2.pack(pady=(10, 5))

        self.label_tempo = ctk.CTkLabel(self.frame_passo2, text="Intervalo de tempo para soma (em minutos):")
        self.label_tempo.pack()

        self.entry_tempo = ctk.CTkEntry(self.frame_passo2, width=100, justify="center", validate="key", validatecommand=self.vcmd)
        self.entry_tempo.pack(pady=5)
        self.entry_tempo.insert(0, "30")

        self.btn_somar = ctk.CTkButton(self.frame_passo2, text="Somar Espectros", command=self.somar_espectros, fg_color="#2b7b54", hover_color="#1e5c3e")
        self.btn_somar.pack(pady=(10, 15))

        # ---------------- PASSO 2: APLICAR ----------------
        self.frame_passo3 = ctk.CTkFrame(self.tab_calib)
        self.frame_passo3.pack(pady=10, padx=10, fill="x")

        self.label_passo3 = ctk.CTkLabel(self.frame_passo3, text="Passo 2: Aplicar Calibração", font=ctk.CTkFont(size=14, weight="bold"))
        self.label_passo3.pack(pady=(10, 5))

        self.label_aviso = ctk.CTkLabel(self.frame_passo3, text="Atenção: Calibre os arquivos na pasta 'Espectros_Somados'\nmanualmente antes de clicar no botão abaixo.", text_color="gray")
        self.label_aviso.pack(pady=5)

        self.label_aviso = ctk.CTkLabel(self.frame_passo3, text="Ao clicar no botão abaixo, as calibrações feitas nos espectros unidos por intervalo de tempo serão aplicadas individualmente aos espectros referentes a cada intervalo de tempo.", text_color="gray")
        self.label_aviso.pack(pady=5)

        self.btn_aplicar = ctk.CTkButton(self.frame_passo3, text="Aplicar Calibração aos Individuais", command=self.aplicar_calibracao)
        self.btn_aplicar.pack(pady=(10, 15))

    def construir_aba_gps(self):
        # ---------------- SELEÇÃO DE PASTA (GPS E ROIs) ----------------
        self.frame_pasta_gps = ctk.CTkFrame(self.tab_gps)
        self.frame_pasta_gps.pack(pady=5, padx=10, fill="x")
        
        self.btn_selecionar_gps = ctk.CTkButton(self.frame_pasta_gps, text="Selecionar Pasta de Espectros (.mca)", command=self.selecionar_pasta_gps)
        self.btn_selecionar_gps.pack(pady=(10, 5))
        
        self.label_caminho_gps_folder = ctk.CTkLabel(self.frame_pasta_gps, text="Nenhuma pasta selecionada para processamento", text_color="gray", wraplength=550)
        self.label_caminho_gps_folder.pack(pady=(0, 10))

        # ---------------- SELEÇÃO DE ARQUIVO GPS ----------------
        self.btn_gps = ctk.CTkButton(self.tab_gps, text="Selecionar Arquivo GPS (.csv)", command=self.selecionar_gps)
        self.btn_gps.pack(pady=(10, 5))

        self.label_caminho_gps = ctk.CTkLabel(self.tab_gps, text="Nenhum arquivo de GPS selecionado", text_color="gray", wraplength=550)
        self.label_caminho_gps.pack(pady=(0, 10))

        # ---------------- CONFIGURAÇÕES GERAIS ----------------
        self.frame_config = ctk.CTkFrame(self.tab_gps)
        self.frame_config.pack(pady=5, padx=10, fill="x")

        # Tolerância
        self.label_tol = ctk.CTkLabel(self.frame_config, text="Tolerância (segundos):")
        self.label_tol.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="e")
        
        self.entry_tol = ctk.CTkEntry(self.frame_config, width=80, justify="center", validate="key", validatecommand=self.vcmd)
        self.entry_tol.grid(row=0, column=1, padx=5, pady=10, sticky="w")
        self.entry_tol.insert(0, "10")

        # Espectro Total
        self.label_total = ctk.CTkLabel(self.frame_config, text="Limites do Espectro Total (keV):")
        self.label_total.grid(row=1, column=0, padx=(10, 5), pady=(0, 10), sticky="e")

        self.frame_total_entries = ctk.CTkFrame(self.frame_config, fg_color="transparent")
        self.frame_total_entries.grid(row=1, column=1, padx=5, pady=(0, 10), sticky="w")

        self.entry_total_ini = ctk.CTkEntry(self.frame_total_entries, width=60, justify="center", validate="key", validatecommand=self.vcmd)
        self.entry_total_ini.pack(side="left")
        self.entry_total_ini.insert(0, "400")

        self.label_sep_total = ctk.CTkLabel(self.frame_total_entries, text="-")
        self.label_sep_total.pack(side="left", padx=5)

        self.entry_total_fim = ctk.CTkEntry(self.frame_total_entries, width=60, justify="center", validate="key", validatecommand=self.vcmd)
        self.entry_total_fim.pack(side="left")
        self.entry_total_fim.insert(0, "2810")

        # ---------------- CONFIGURAÇÕES (ROIs DINÂMICOS) ----------------
        self.label_rois_title = ctk.CTkLabel(self.tab_gps, text="ROIs (Energia em keV):", font=ctk.CTkFont(weight="bold"))
        self.label_rois_title.pack(pady=(10, 0))

        self.roi_frame = ctk.CTkScrollableFrame(self.tab_gps, height=130)
        self.roi_frame.pack(pady=5, padx=10, fill="x")

        self.roi_entries = []
        
        self.btn_add_roi = ctk.CTkButton(self.tab_gps, text="+ Adicionar ROI", command=self.adicionar_roi, fg_color="#4a4a4a", hover_color="#333333")
        self.btn_add_roi.pack(pady=5)

        rois_padrao = [(50, 90), (216, 261), (324, 388), (553, 688), (853, 1036), (1360, 1560), (1660, 1860), (2410, 2810)]
        for ini, fim in rois_padrao:
            self.adicionar_roi(ini, fim)

        # ---------------- BOTÃO PROCESSAR ----------------
        self.btn_processar_gps = ctk.CTkButton(self.tab_gps, text="Processar e Cruzar Dados", command=self.processar_gps, fg_color="#91480f", hover_color="#6b340a")
        self.btn_processar_gps.pack(pady=10)

    # --- LÓGICA DOS ROIs DINÂMICOS ---

    def adicionar_roi(self, val_ini="", val_fim=""):
        row_frame = ctk.CTkFrame(self.roi_frame, fg_color="transparent")
        row_frame.pack(fill="x", pady=2)
        
        entry_ini = ctk.CTkEntry(row_frame, width=80, placeholder_text="Inicial", validate="key", validatecommand=self.vcmd)
        entry_ini.pack(side="left", padx=5)
        if val_ini: entry_ini.insert(0, str(val_ini))
        
        lbl_sep = ctk.CTkLabel(row_frame, text="-")
        lbl_sep.pack(side="left")
        
        entry_fim = ctk.CTkEntry(row_frame, width=80, placeholder_text="Final", validate="key", validatecommand=self.vcmd)
        entry_fim.pack(side="left", padx=5)
        if val_fim: entry_fim.insert(0, str(val_fim))
        
        btn_rem = ctk.CTkButton(row_frame, text="X", width=30, fg_color="#a83232", hover_color="#7a2121", 
                                command=lambda: self.remover_roi(row_frame, entry_ini, entry_fim))
        btn_rem.pack(side="right", padx=5)
        
        self.roi_entries.append((entry_ini, entry_fim))

    def remover_roi(self, frame, entry_ini, entry_fim):
        frame.destroy()
        self.roi_entries.remove((entry_ini, entry_fim))


    # --- FUNÇÕES DE EVENTOS (BOTÕES PRINCIPAIS) ---

    def selecionar_pasta_calib(self):
        pasta_selecionada = filedialog.askdirectory(title="Selecione a pasta contendo os espectros (Calibração)")
        if pasta_selecionada:
            self.PASTA_ESPECTROS_CALIB = pasta_selecionada
            self.PASTA_SOMADOS = os.path.join(self.PASTA_ESPECTROS_CALIB, 'Espectros_Somados')
            self.PASTA_ESPECTROS_CALIBRADOS = os.path.join(self.PASTA_ESPECTROS_CALIB, 'Espectros_Calibrados')
            self.label_caminho_calib.configure(text=f"Pasta: {self.PASTA_ESPECTROS_CALIB}", text_color=("black", "white"))

    def selecionar_pasta_gps(self):
        pasta_selecionada = filedialog.askdirectory(title="Selecione a pasta contendo os espectros calibrados (GPS)")
        if pasta_selecionada:
            self.PASTA_ESPECTROS_GPS = pasta_selecionada
            self.label_caminho_gps_folder.configure(text=f"Pasta: {self.PASTA_ESPECTROS_GPS}", text_color=("black", "white"))

    def selecionar_gps(self):
        arquivo_selecionado = filedialog.askopenfilename(title="Selecione o arquivo de Logs GPS", filetypes=[("Arquivos CSV", "*.csv")])
        if arquivo_selecionado:
            self.ARQUIVO_GPS = arquivo_selecionado
            self.label_caminho_gps.configure(text=f"GPS: {self.ARQUIVO_GPS}", text_color=("black", "white"))

    def processar_gps(self):
        if not self.PASTA_ESPECTROS_GPS:
            messagebox.showwarning("Aviso", "Selecione a pasta de espectros na aba atual (GPS e ROIs).")
            return
        if not self.ARQUIVO_GPS:
            messagebox.showwarning("Aviso", "Selecione o arquivo GPS (.csv) na aba atual.")
            return

        try:
            tolerancia_seg = int(self.entry_tol.get())
            espectro_total_min = int(self.entry_total_ini.get())
            espectro_total_max = int(self.entry_total_fim.get())
        except ValueError:
            messagebox.showerror("Erro", "A tolerância e os limites do Espectro Total devem ser números inteiros.")
            return

        arq_ROIs_energia = []
        for entry_ini, entry_fim in self.roi_entries:
            val_ini = entry_ini.get().strip()
            val_fim = entry_fim.get().strip()
            
            if not val_ini and not val_fim:
                continue
                
            try:
                arq_ROIs_energia.append((int(val_ini), int(val_fim)))
            except ValueError:
                messagebox.showerror("Erro de Formato", f"Os valores de ROI devem estar preenchidos.\nVerifique a linha com: '{val_ini}' e '{val_fim}'.")
                return
                
        if not arq_ROIs_energia:
            messagebox.showwarning("Aviso", "Por favor, adicione e preencha pelo menos um ROI válido para processar.")
            return

        ARQUIVO_SAIDA = os.path.join(self.PASTA_ESPECTROS_GPS, "Localizacoes.csv")

        try:
            df_gps = pd.read_csv(self.ARQUIVO_GPS)
            if 'timestamp' not in df_gps.columns:
                messagebox.showerror("Erro no CSV", "A coluna 'timestamp' não foi encontrada no arquivo de GPS.")
                return
            df_gps['timestamp'] = pd.to_datetime(df_gps['timestamp'], utc=True).dt.tz_localize(None)

            # Corrigindo o fuso horário
            df_gps['timestamp'] = df_gps['timestamp'] - pd.Timedelta(hours=3)

            df_gps = df_gps.sort_values('timestamp')

            lista_espectros = []
            arquivos = glob.glob(os.path.join(self.PASTA_ESPECTROS_GPS, "*.mca"))
            
            if not arquivos:
                messagebox.showwarning("Aviso", "Nenhum arquivo .mca encontrado na pasta selecionada.")
                return

            colunas_ROIs = []

            for arq in arquivos:
                with open(arq, 'r') as f:
                    arq_list = f.read().splitlines()
                
                if '<<CALIBRATION>>' not in arq_list:
                    messagebox.showerror("Erro de Calibração", f"O arquivo {os.path.basename(arq)} não possui calibração.\nUse a Aba 1 para calibrar todos os arquivos primeiro.")
                    return

                index_calibration = arq_list.index('<<CALIBRATION>>')
                
                if '<<ROI>>' in arq_list:
                    index_ROI = arq_list.index('<<ROI>>')
                else:
                    index_ROI = arq_list.index('<<DATA>>')

                arq_preambulo = {}
                index_pmca_spectrum = arq_list.index('<<PMCA SPECTRUM>>')
                for linha in arq_list[index_pmca_spectrum+1:index_calibration]:
                    if " - " in linha:
                        chave, valor = linha.split(' - ', 1)
                        arq_preambulo[chave.strip()] = valor.strip()

                arq_calib = {}
                for linha in arq_list[index_calibration+2:index_ROI]:
                    if not linha.strip(): continue
                    partes = linha.split()
                    arq_calib[int(partes[0])] = int(partes[1])
                
                if not arq_calib:
                    messagebox.showerror("Erro", f"Calibração vazia no arquivo {os.path.basename(arq)}.")
                    return

                arq_ROIs = [(energia_para_canal(inicio, arq_calib), energia_para_canal(fim, arq_calib)) for inicio, fim in arq_ROIs_energia]

                index_data = arq_list.index('<<DATA>>')
                
                novas_linhas = [f"{i}\n" for i in arq_list[:index_calibration+2]]
                for inicio, fim in arq_calib.items():
                    novas_linhas.append(f"{inicio} {fim}\n")
                
                novas_linhas.append('<<ROI>>\n')
                for inicio, fim in arq_ROIs:
                    novas_linhas.append(f"{inicio} {fim}\n")
                
                novas_linhas.extend([f"{i}\n" for i in arq_list[index_data:]])
                novas_linhas[-1] = novas_linhas[-1].strip()

                with open(arq, 'w') as f:
                    f.writelines(novas_linhas)

                index_end = arq_list.index('<<END>>')
                arq_data = [int(count) for count in arq_list[index_data+1:index_end]]

                mid_time, duracao = extrair_tempo_medio(arq_preambulo)
                contagens_ROIs = extrair_ROIs(arq_data, arq_ROIs, arq_calib)
                
                # Chamando a função extrair_totais com os novos parâmetros fornecidos na interface
                contagens_totais = extrair_totais(arq_data, arq_calib, espectro_total_min, espectro_total_max)
                
                info_dict = {
                    'Arquivo': os.path.basename(arq),
                    'Hora_MidPoint': mid_time,
                    'Duracao_Seg': duracao,
                    'Caminho_Completo': arq
                }

                for i in range(len(contagens_ROIs)):
                    contagem_bruta = contagens_ROIs[i][4]
                    energia_inicial, energia_final = arq_ROIs_energia[i]
                    nome_coluna = f"{energia_inicial}_keV-{energia_final}_keV"
                    info_dict[nome_coluna] = contagem_bruta

                    if arquivos.index(arq) == 0:
                        colunas_ROIs.append(nome_coluna)
                
                info_dict['Contagem_Total'] = contagens_totais[0]
                info_dict['Espectro_Completo'] = contagens_totais[1]
                lista_espectros.append(info_dict)

            df_spec = pd.DataFrame(lista_espectros)
            df_spec = df_spec.sort_values('Hora_MidPoint')

            df_final = pd.merge_asof(
                df_spec,
                df_gps,
                left_on='Hora_MidPoint',
                right_on='timestamp',
                direction='nearest',
                tolerance=pd.Timedelta(seconds=tolerancia_seg)
            )

            colunas_finais = ['Arquivo', 'Hora_MidPoint', 'latitude', 'longitude', 'Duracao_Seg']
            colunas_finais += colunas_ROIs
            colunas_finais += ['Contagem_Total', 'Espectro_Completo']

            colunas_existentes = [col for col in colunas_finais if col in df_final.columns]

            df_final[colunas_existentes].to_csv(ARQUIVO_SAIDA, index=False, sep=',', decimal='.')

            messagebox.showinfo("Concluído", f"Cruzamento concluído com sucesso!\n\nArquivo salvo em:\n{ARQUIVO_SAIDA}")

        except Exception as e:
            messagebox.showerror("Erro Crítico", f"Ocorreu um erro durante o processamento:\n{str(e)}")

    def somar_espectros(self):
        if not self.PASTA_ESPECTROS_CALIB:
            messagebox.showwarning("Aviso", "Selecione a pasta de espectros na aba atual (Calibração).")
            return

        try:
            minutos = float(self.entry_tempo.get())
            intervalo_calib = minutos * 60
        except ValueError:
            messagebox.showerror("Erro", "Por favor, insira um número válido para os minutos.")
            return

        lista_arq = [file for file in os.listdir(self.PASTA_ESPECTROS_CALIB) if file.endswith('.mca')]
        
        if not lista_arq:
            messagebox.showwarning("Aviso", f"Nenhum arquivo .mca encontrado na pasta:\n{self.PASTA_ESPECTROS_CALIB}")
            return

        os.makedirs(self.PASTA_SOMADOS, exist_ok=True)
        lista_arq.sort()

        try:
            num_iteracoes = 1
            num_arquivos = len(lista_arq)
            global_data = []
            global_time = 0

            for file_name in lista_arq:
                clean_name = file_name[:-4]
                with open(os.path.join(self.PASTA_ESPECTROS_CALIB, file_name), 'r') as f:
                    file_lst = [linha.strip() for linha in f.readlines()]
                
                index_pmca = file_lst.index('<<PMCA SPECTRUM>>')
                index_data = file_lst.index('<<DATA>>')
                index_end = file_lst.index('<<END>>')
                arq_preambulo = {}

                if '<<CALIBRATION>>' in file_lst:
                    index_calibration = file_lst.index('<<CALIBRATION>>')
                    for linha in file_lst[index_pmca+1:index_calibration]:
                        chave, valor = [s.strip() for s in linha.split('-')]
                        arq_preambulo[chave] = valor
                elif '<<ROI>>' in file_lst:
                    index_roi = file_lst.index('<<ROI>>')
                    for linha in file_lst[index_pmca+1:index_roi]:
                        chave, valor = [s.strip() for s in linha.split('-')]
                        arq_preambulo[chave] = valor
                else:
                    for linha in file_lst[index_pmca+1:index_data]:
                        chave, valor = [s.strip() for s in linha.split('-')]
                        arq_preambulo[chave] = valor

                arq_data = [int(contagem) for contagem in file_lst[index_data+1:index_end]]
                num_canais = len(arq_data)
                real_time = float(arq_preambulo['REAL_TIME'].strip())
                start_time = arq_preambulo['START_TIME'].strip()
                start_time_dt = datetime.strptime(start_time, '%m/%d/%Y %H:%M:%S')
                end_time = start_time_dt + timedelta(seconds=real_time)

                if num_iteracoes == 1:
                    first_file = clean_name
                    first_time = start_time_dt
                    accum_data = [0] * num_canais
                    global_data = [0] * num_canais
                    first_global_time = start_time_dt
                
                for canal in range(num_canais):
                    global_data[canal] += arq_data[canal]
                
                global_time += real_time

                if first_file == 'next':
                    first_file = clean_name
                
                accum_time = (end_time - first_time).total_seconds()

                for canal in range(num_canais):
                    accum_data[canal] += arq_data[canal]

                if accum_time >= intervalo_calib or num_iteracoes == num_arquivos:
                    preambulo_final = copy.deepcopy(arq_preambulo)
                    preambulo_final['LIVE_TIME'] = accum_time
                    preambulo_final['REAL_TIME'] = accum_time
                    preambulo_final['START_TIME'] = first_time.strftime("%m/%d/%Y %H:%M:%S")

                    lista_final = ['<<PMCA SPECTRUM>>\n']
                    for chave in preambulo_final.keys():
                        valor = preambulo_final[chave]
                        lista_final.append(f'{chave.strip()} - {str(valor).strip()}\n')
                    
                    lista_final.append('<<DATA>>\n')
                    for contagem in accum_data:
                        lista_final.append(f'{str(contagem)}\n')

                    lista_final.append('<<END>>\n')
                    config_final = [f'{i}\n' for i in file_lst[index_end+1:]]

                    for linha in config_final:
                        if 'Real Time:' in linha:
                            linha = f'Real Time: {accum_time:.6f}\n'
                        elif 'Accumulation Time:' in linha:
                            linha = f'Accumulation Time: {accum_time:.6f}\n'
                        lista_final.append(linha)
                  
                    with open(os.path.join(self.PASTA_SOMADOS, f'{first_file}___{clean_name}.mca'), 'w') as arquivo_final:
                        arquivo_final.writelines(lista_final)
                    
                    first_file = 'next'
                    first_time = start_time_dt
                    accum_data = [0] * num_canais
                
                if num_iteracoes == num_arquivos:
                    preambulo_final = copy.deepcopy(arq_preambulo)
                    preambulo_final['LIVE_TIME'] = global_time
                    preambulo_final['REAL_TIME'] = global_time
                    preambulo_final['START_TIME'] = first_global_time.strftime("%m/%d/%Y %H:%M:%S")

                    lista_final = ['<<PMCA SPECTRUM>>\n']
                    for chave in preambulo_final.keys():
                        valor = preambulo_final[chave]
                        lista_final.append(f'{chave.strip()} - {str(valor).strip()}\n')
                    
                    lista_final.append('<<DATA>>\n')
                    for contagem in global_data:
                        lista_final.append(f'{str(contagem)}\n')

                    lista_final.append('<<END>>\n')
                    config_final = [f'{i}\n' for i in file_lst[index_end+1:]]

                    for linha in config_final:
                        if 'Real Time:' in linha:
                            linha = f'Real Time: {global_time:.6f}\n'
                        elif 'Accumulation Time:' in linha:
                            linha = f'Accumulation Time: {global_time:.6f}\n'
                        lista_final.append(linha)
                  
                    with open(os.path.join(self.PASTA_SOMADOS, 'Espectro_Total.mca'), 'w') as arquivo_final:
                        arquivo_final.writelines(lista_final)

                num_iteracoes += 1

            messagebox.showinfo("Sucesso", f"Espectros somados!\n\nUma pasta 'Espectros_Somados' foi criada dentro de:\n{self.PASTA_ESPECTROS_CALIB}\n\nFaça a calibração manual lá antes do Passo 2.")

        except Exception as e:
            messagebox.showerror("Erro na Execução", f"Ocorreu um erro ao processar os arquivos:\n{str(e)}")

    def aplicar_calibracao(self):
        if not self.PASTA_ESPECTROS_CALIB:
            messagebox.showwarning("Aviso", "Selecione a pasta de espectros na aba atual (Calibração).")
            return

        if not os.path.exists(self.PASTA_SOMADOS):
            messagebox.showwarning("Aviso", "A pasta 'Espectros_Somados' não existe. Você executou o Passo 1?")
            return

        lst_arq_calibrados = [file for file in os.listdir(self.PASTA_SOMADOS) if file.endswith('.mca')]
        
        if not lst_arq_calibrados:
            messagebox.showwarning("Aviso", f"Nenhum arquivo encontrado na pasta:\n{self.PASTA_SOMADOS}")
            return

        os.makedirs(self.PASTA_ESPECTROS_CALIBRADOS, exist_ok=True)
        lst_arq_calibrados.sort()
        ARQ_ESPECTRO_TOTAL = 'Espectro_Total.mca'

        if ARQ_ESPECTRO_TOTAL in lst_arq_calibrados:
            lst_arq_calibrados.remove(ARQ_ESPECTRO_TOTAL)

        lst_arq_originais = [file for file in os.listdir(self.PASTA_ESPECTROS_CALIB) if file.endswith('.mca')]
        lst_arq_originais.sort()

        arquivos_nao_calibrados = []

        try:
            for arq_calibrado in lst_arq_calibrados:
                clean_name = arq_calibrado[:-4]
                with open(os.path.join(self.PASTA_SOMADOS, arq_calibrado), 'r') as f:
                    file_lst = [linha.strip() for linha in f.readlines()]
                
                index_pmca = file_lst.index('<<PMCA SPECTRUM>>')
                index_data = file_lst.index('<<DATA>>')
                index_end = file_lst.index('<<END>>')

                try:
                    index_calibration = file_lst.index('<<CALIBRATION>>')
                except ValueError:
                    arquivos_nao_calibrados.append(arq_calibrado)
                    continue
                    
                if '<<ROI>>' in file_lst:
                    index_roi = file_lst.index('<<ROI>>')
                    calibracao = file_lst[index_calibration:index_roi]
                else:
                    calibracao = file_lst[index_calibration:index_data]

                arq_start, arq_end = clean_name.split('___')
                arq_start += '.mca'
                arq_end += '.mca'

                index_start = lst_arq_originais.index(arq_start)
                index_end = lst_arq_originais.index(arq_end)

                for arq_original in lst_arq_originais[index_start:index_end+1]:
                    with open(os.path.join(self.PASTA_ESPECTROS_CALIB, arq_original), 'r') as arq_original_ler:
                        file_lst_original = arq_original_ler.readlines()

                    novo_arq = []
                    if '<<CALIBRATION>>\n' in file_lst_original:
                        index_calibration_original = file_lst_original.index('<<CALIBRATION>>\n')
                        novo_arq.extend(file_lst_original[:index_calibration_original])
                        novo_arq.extend([f'{linha}\n' for linha in calibracao])

                        if "<<ROI>>\n" in file_lst_original:
                            index_roi_original = file_lst_original.index('<<ROI>>\n')
                            novo_arq.extend(file_lst_original[index_roi_original:])
                        else:
                            index_data_original = file_lst_original.index('<<DATA>>\n')
                            novo_arq.extend(file_lst_original[index_data_original:])

                    elif "<<ROI>>\n" in file_lst_original:
                        index_roi_original = file_lst_original.index('<<ROI>>\n')
                        novo_arq.extend(file_lst_original[:index_roi_original])
                        novo_arq.extend([f'{linha}\n' for linha in calibracao])
                        novo_arq.extend(file_lst_original[index_roi_original:])
                    else:
                        index_data_original = file_lst_original.index('<<DATA>>\n')
                        novo_arq.extend(file_lst_original[:index_data_original])
                        novo_arq.extend([f'{linha}\n' for linha in calibracao])
                        novo_arq.extend(file_lst_original[index_data_original:])
                    
                    with open(os.path.join(self.PASTA_ESPECTROS_CALIBRADOS, arq_original), 'w') as arq_original_escrever:
                        arq_original_escrever.writelines(novo_arq)

            if arquivos_nao_calibrados:
                nomes = ", ".join(arquivos_nao_calibrados)
                messagebox.showwarning("Atenção", f"Calibração concluída, mas os seguintes arquivos não tinham calibração salva: {nomes}")
            else:
                messagebox.showinfo("Sucesso", f"Sucesso!\n\nOs espectros individuais calibrados foram salvos na pasta:\n'Espectros_Calibrados'.")

        except Exception as e:
            messagebox.showerror("Erro na Execução", f"Ocorreu um erro ao colar a calibração:\n{str(e)}")


if __name__ == "__main__":
    app = CalibradorApp()
    app.mainloop()