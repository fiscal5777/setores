# -*- coding: utf-8 -*-
import pandas as pd
import simplekml
import math
import os
from shapely.geometry import Polygon
import geopandas as gpd
import colorsys

# --- CONFIGURAÇÕES ---
DISTANCIA_KM = 0.5                # Raio dos setores em km
SETOR_ANGULO = 30                 # Abertura do setor (graus)
RAIO_CIRCULO_METROS = 20          # Raio do círculo que marca a estação base (em metros)
INPUT_FILE = r"C:\Users\afsal\Downloads\KMZ\csv_licenciamento_761383dc857bcdefd4483b578d459e72.csv"
OUTPUT_KMZ = "setores_estacoes.kmz"
OUTPUT_GEOJSON = "setores_estacoes.geojson"
OPACIDADE_PERCENTUAL = 50         # Translucidez dos setores (0 = transparente, 100 = opaco)

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

# --- PROCESSAMENTO PRINCIPAL ---

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
        pasta_freq = pasta_entidade.newfolder(name=f"Frequência {freq} MHz")
        estacoes = group_freq['NumEstacao'].unique()
        for estacao_id in estacoes:
            sub_group = group_freq[group_freq['NumEstacao'] == estacao_id]
            lat = sub_group.iloc[0]['Latitude']
            lon = sub_group.iloc[0]['Longitude']
            # Pasta para estação
            pasta_estacao = pasta_freq.newfolder(name=f"Estação {estacao_id}")
            # --- Adicionar círculo vermelho COM TRANSPARÊNCIA como marcador da estação ---
            coords_circulo = gerar_circulo(lat, lon, RAIO_CIRCULO_METROS)
            red_with_alpha = simplekml.Color.changealphaint(ALPHA, simplekml.Color.red)
            pol_circulo = pasta_estacao.newpolygon(
                name=f"Estação {estacao_id}",
                description=f"Marcador da Estação Base: {nome_entidade}"
            )
            pol_circulo.outerboundaryis = coords_circulo
            pol_circulo.style.polystyle.color = red_with_alpha
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
                if str(tecnologia).strip().upper() == 'NR':
                    distancia_km = 0.6
                elif str(tecnologia).strip().upper() == 'LTE':
                    distancia_km = 0.7
                elif str(tecnologia).strip().upper() == 'WCDMA':
                    distancia_km = 0.8
                elif str(tecnologia).strip().upper() == 'GSM':
                    distancia_km = 0.9
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
                pol_kml.outerboundaryis = [
                    (lon, lat),
                    (pts[0][1], pts[0][0]),
                    (pts[1][1], pts[1][0]),
                    (lon, lat)
                ]
                pol_kml.style.polystyle.color = cor_com_alpha
                pol_kml.style.linestyle.width = 1.0

                # Polígono no GeoJSON
                pol_geojson = Polygon([
                    (lon, lat),
                    (pts[0][1], pts[0][0]),
                    (pts[1][1], pts[1][0]),
                    (lon, lat)
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
gdf.to_file(output_geojson_path, driver="GeoJSON")

print(f"\nKMZ criado com sucesso: {os.path.abspath(output_kmz_path)}")
print(f"GeoJSON criado com sucesso: {os.path.abspath(output_geojson_path)}")