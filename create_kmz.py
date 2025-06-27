# -*- coding: utf-8 -*-
import pandas as pd
import simplekml
import math
import os
from shapely.geometry import Polygon
import geopandas as gpd
import colorsys
import tkinter as tk
from tkinter import filedialog, messagebox


# --- CONFIGURAÇÕES ---
DISTANCIA_KM = 0.5                # Raio dos setores em km
SETOR_ANGULO = 30                 # Abertura do setor (graus)
RAIO_CIRCULO_METROS = 40          # Raio do círculo que marca a estação base (em metros)
INPUT_FILE = r"C:\Users\afsal\Downloads\KMZ\csv_licenciamento_f45a67d3ecccb6e0e77b5aa042686e81.csv"
OUTPUT_KMZ = "setores_estacoes.kmz"
OUTPUT_GEOJSON = "setores_estacoes.geojson"
OPACIDADE_PERCENTUAL = 60        # Translucidez dos setores (0 = transparente, 100 = opaco)

# Calcula o valor do canal alfa (0–255) 
ALPHA = int((OPACIDADE_PERCENTUAL / 100) * 255)

# Colunas necessárias na planilha
REQUIRED_COLUMNS = ['Latitude', 'Longitude', 'Azimute', 'FreqTxMHz', 'NomeEntidade', 'NumEstacao', 'Tecnologia']

# --- FUNÇÕES AUXILIARES ---

def calcular_pontos(lat, lon, azimute1, azimute2, distancia_km=DISTANCIA_KM):
    """Calcula coordenadas finais com base no azimute e distância."""
    R = 6371  # Raio da Terra em km
    azimutes = [azimute1, azimute2]
    pontos = []
    for az in azimutes:
        az_rad = math.radians(az)
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)

        lat2 = math.asin(math.sin(lat_rad) * math.cos(distancia_km / R) +
                         math.cos(lat_rad) * math.sin(distancia_km / R) * math.cos(az_rad))

        lon2 = lon_rad + math.atan2(math.sin(az_rad) * math.sin(distancia_km / R) * math.cos(lat_rad),
                                    math.cos(distancia_km / R) - math.sin(lat_rad) * math.sin(lat2))

        pontos.append((math.degrees(lat2), math.degrees(lon2)))
    return pontos

def gerar_circulo(lat, lon, raio_metros=RAIO_CIRCULO_METROS, num_pontos=36):
    """
    Gera coordenadas de um círculo ao redor de um ponto (lat, lon) em graus.
    Raio em metros.
    """
    R = 6371000  # Raio da Terra em metros
    coords = []
    for i in range(num_pontos):
        angulo = math.radians(float(i) * 360 / num_pontos)
        lat2 = math.asin(math.sin(math.radians(lat)) * math.cos(raio_metros / R) +
                         math.cos(math.radians(lat)) * math.sin(raio_metros / R) * math.cos(angulo))
        lon2 = math.radians(lon) + math.atan2(
            math.sin(angulo) * math.sin(raio_metros / R) * math.cos(math.radians(lat)),
            math.cos(raio_metros / R) - math.sin(math.radians(lat)) * math.sin(lat2)
        )
        coords.append((math.degrees(lon2), math.degrees(lat2)))
    return coords

def get_color(freq):
    """Gera cor RGB dinâmica com base na frequência (HSV)"""
    freq = float(freq)
    min_freq, max_freq = 700, 6000  # Ajuste conforme necessário
    hue = ((freq - min_freq) / (max_freq - min_freq)) % 1.0
    r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(hue, 1, 1)]
    return simplekml.Color.rgb(r, g, b)

def faixas(freq):
    """verifica qual é a faixa de frequencia utilizada"""
    freq = float(freq)
    if freq>=450 and freq <480:
        faixa = 450
    elif freq>=764 and freq <803:
        faixa = 700
    elif freq>=864 and freq <895:
        faixa = 850
    elif freq>=943 and freq <960:
        faixa = 900
    elif freq>=1800 and freq <1880:
        faixa = 1800
    elif freq>=2100 and freq <2170:
        faixa = 2100
    elif freq>=2300 and freq <2400:
        faixa = 2300  
    elif freq>=2570 and freq <2620:
        faixa = 2500
    elif freq>=2620 and freq <2690:
        faixa = 2600
    elif freq>=3300 and freq <3700:
        faixa = 3500
    elif freq>=4830 and freq <4950:
        faixa = 4900
    else:
        faixa = freq        
    return faixa

def cor_operadora(operadora):
    """cor da operadora"""
    # pega primeira palavra da string operadora
    operadora = str(operadora).strip().upper().split()[0] if operadora else ""

    if str(operadora).strip().upper() == 'CLARO':
        cor_operadora = simplekml.Color.changealphaint(ALPHA, simplekml.Color.red)
    elif str(operadora).strip().upper() == 'TELEFONICA':
        cor_operadora = simplekml.Color.changealphaint(ALPHA, simplekml.Color.purple)
    elif str(operadora).strip().upper() == 'TIM':
        cor_operadora = simplekml.Color.changealphaint(ALPHA, simplekml.Color.blue)
    else:
        cor_operadora = simplekml.Color.changealphaint(ALPHA, simplekml.Color.white)     
    return cor_operadora
# --- PROCESSAMENTO PRINCIPAL ---

def run_process(input_file):
    global INPUT_FILE
    INPUT_FILE = input_file
    try:
        # Ler arquivo Excel ou CSV
        if INPUT_FILE.lower().endswith('.csv'):
            df = pd.read_csv(INPUT_FILE)
        else:
            df = pd.read_excel(INPUT_FILE, sheet_name=0)

        # Verificar colunas obrigatórias
        if not all(col in df.columns for col in REQUIRED_COLUMNS):
            raise ValueError("Planilha não possui todas as colunas necessárias.")

        # Remover linhas com valores nulos nas colunas obrigatórias
        df = df[REQUIRED_COLUMNS].dropna()

        # uniformizando os Nomes das Entidades, pega primeira palavra e deixa maiscula
        df['NomeEntidade'] = df['NomeEntidade'].str.split().str[0].str.upper()

        # Criar KML
        kml = simplekml.Kml()
        kml.document.name = "Setores de Estações"
        kml.document.open = 1

        # Estrutura GeoJSON
        geojson_features = []

        # Agrupar por entidade
        grouped = df.groupby('NomeEntidade')

        # Agrupar por entidade e faixa de frequência
        for nome_entidade, group_entidade in grouped:
            pasta_entidade = kml.newfolder(name=str(nome_entidade))
            # Agrupar por faixa de frequência (FreqTxMHz)
            grouped_freq = group_entidade.groupby('FreqTxMHz')

            for freq, group_freq in grouped_freq:
                faixa = faixas(freq)
                pasta_freq = pasta_entidade.newfolder(name=f"Frequência {faixa} MHz")
                estacoes = group_freq['NumEstacao'].unique()
                for estacao_id in estacoes:
                    sub_group = group_freq[group_freq['NumEstacao'] == estacao_id]
                    lat = sub_group.iloc[0]['Latitude']
                    lon = sub_group.iloc[0]['Longitude']
                    # Pasta para estação
                    pasta_estacao = pasta_freq.newfolder(name=f"Estação {estacao_id}")
                    # --- Adicionar círculo vermelho COM TRANSPARÊNCIA como marcador da estação ---
                    
                    coords_circulo = gerar_circulo(lat, lon, RAIO_CIRCULO_METROS)
                    #red_with_alpha = simplekml.Color.changealphaint(ALPHA, simplekml.Color.red)
                    pol_circulo = pasta_estacao.newpolygon(
                        name=f"Estação {estacao_id}",
                        description=f"Marcador da Estação Base: {nome_entidade}"
                    )
                    pol_circulo.outerboundaryis = coords_circulo
                    pol_circulo.style.polystyle.color = cor_operadora(nome_entidade) # deine a cor da operadora
                    pol_circulo.style.linestyle.width = 0

                    # Adicionar ao GeoJSON como ponto
                    geojson_features.append({
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [lon, lat]
                        },
                        "properties": {
                            "NomeEntidade": nome_entidade,
                            "NumEstacao": estacao_id,
                            "Tipo": "Estação Base",
                            "FreqTxMHz": freq
                        }
                    })

                    # Para cada linha (setor) da estação, criar setor vinculado à tecnologia
                    for _, row in sub_group.iterrows():
                        az = float(str(row['Azimute']).replace(',', '.'))
                        freq_row = row['FreqTxMHz']
                        tecnologia = row['Tecnologia']

                        # Ajustar distância conforme tecnologia
                        #if str(tecnologia).strip().upper() == 'NR':
                            #distancia_km = 0.6
                        #elif str(tecnologia).strip().upper() == 'LTE':
                            #distancia_km = 0.7
                        #elif str(tecnologia).strip().upper() == 'WCDMA':
                            #distancia_km = 0.8
                        #elif str(tecnologia).strip().upper() == 'GSM':
                            #distancia_km = 0.9
                        #else:
                            #distancia_km = DISTANCIA_KM  # valor padrão
                        
                        # Ajustar distância conforme faixa
                        faixa = faixas(freq_row)

                        if (faixa) == 450:
                            distancia_km = 1.5
                        elif (faixa) == 700:
                            distancia_km = 1.4
                        elif (faixa) == 850:
                            distancia_km = 1.3
                        elif  (faixa) == 900:
                            distancia_km = 1.2
                        elif  (faixa) == 1800:
                            distancia_km = 1.1
                        elif  (faixa) == 2100:
                            distancia_km = 1
                        elif  (faixa) == 2300:
                            distancia_km = 0.9
                        elif  (faixa) == 2500:
                            distancia_km = 0.8
                        elif  (faixa) == 2600:
                            distancia_km = 0.7
                        elif  (faixa) == 3500:
                            distancia_km = 0.6
                        elif  (faixa) == 4900:
                            distancia_km = 0.5
                        else:
                            distancia_km = DISTANCIA_KM  # valor padrão

                        # Calcular pontos do setor com distância ajustada
                        pts = calcular_pontos(lat, lon, az - SETOR_ANGULO, az + SETOR_ANGULO, distancia_km=distancia_km)

                        # Cor com base na frequência
                        cor_kml = get_color(freq_row)
                        cor_com_alpha = simplekml.Color.changealphaint(ALPHA, cor_kml)

                        # Polígono no KML
                        pol_kml = pasta_estacao.newpolygon(
                            name=f"Setor {az}° - {freq_row} MHz - {tecnologia} - {nome_entidade}",
                            description=f"Entidade: {nome_entidade}, Estação: {estacao_id}, Frequência: {freq_row} MHz, Tecnologia: {tecnologia}"
                        )

                        alt = 0 #altura acima do solo
                        # foi incluido uma altura para ficar acima do solo os setores, ainda nao esta ok!

                        pol_kml.outerboundaryis = [
                            (lon, lat, alt),
                            (pts[0][1], pts[0][0], alt),
                            (pts[1][1], pts[1][0], alt),
                            (lon, lat, alt)
                        ]
                        pol_kml.style.polystyle.color = cor_com_alpha
                        pol_kml.style.linestyle.width = 1.0


                        # Polígono no GeoJSON
                        pol_geojson = Polygon([
                            (lon, lat, alt),
                            (pts[0][1], pts[0][0], alt),
                            (pts[1][1], pts[1][0], alt),
                            (lon, lat, alt)
                        ])

                        geojson_features.append({
                            "type": "Feature",
                            "geometry": pol_geojson.__geo_interface__,
                            "properties": {
                                "NomeEntidade": nome_entidade,
                                "NumEstacao": estacao_id,
                                "Azimute": az,
                                "FreqTxMHz": freq_row,
                                "Tecnologia": tecnologia,
                                "Tipo": "Setor"
                            }
                        })
        # --- SALVAR ARQUIVOS DE SAÍDA ---
        output_dir = os.path.dirname(INPUT_FILE)
        output_kmz_path = os.path.join(output_dir, OUTPUT_KMZ)
        output_geojson_path = os.path.join(output_dir, OUTPUT_GEOJSON)

        # Salvar KMZ
        kml.savekmz(output_kmz_path, format=False)

        # Salvar GeoJSON
        gdf = gpd.GeoDataFrame.from_features(geojson_features)
        gdf.crs = "EPSG:31983" # WGS84
        gdf.to_file(output_geojson_path, driver="GeoJSON")

        return output_kmz_path, output_geojson_path
    except Exception as e:
        raise e

def main_gui():
    def select_file():
        file_path = filedialog.askopenfilename(filetypes=[("CSV/Excel files", "*.csv;*.xlsx;*.xls")])
        if file_path:
            entry_file.delete(0, tk.END)
            entry_file.insert(0, file_path)

    def process():
        input_file = entry_file.get()
        if not input_file:
            messagebox.showerror("Erro", "Selecione o arquivo de entrada.")
            return
        try:
            kmz, geojson = run_process(input_file)
            messagebox.showinfo("Sucesso", f"Arquivos gerados:\nKMZ: {kmz}\nGeoJSON: {geojson}")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    root = tk.Tk()
    root.title("Gerador de KMZ e GeoJSON")
    root.geometry("500x180")

    tk.Label(root, text="Arquivo de entrada (CSV/Excel):").pack(pady=10)
    frame = tk.Frame(root)
    frame.pack()
    entry_file = tk.Entry(frame, width=50)
    entry_file.pack(side=tk.LEFT, padx=5)
    tk.Button(frame, text="Selecionar", command=select_file).pack(side=tk.LEFT)
    tk.Button(root, text="Gerar Arquivos", command=process, width=20).pack(pady=20)
    root.mainloop()

if __name__ == "__main__":
    main_gui()
