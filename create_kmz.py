import streamlit as st
import pandas as pd
import simplekml
import math
import os
from shapely.geometry import Polygon
import geopandas as gpd
import colorsys
import tempfile

# --- CONFIGURAÇÕES PADRÃO ---
DISTANCIA_KM = 0.5
SETOR_ANGULO = 30
RAIO_CIRCULO_METROS = 40
OPACIDADE_PERCENTUAL = 60
OUTPUT_KMZ = "setores_estacoes.kmz"
OUTPUT_GEOJSON = "setores_estacoes.geojson"

# --- FUNÇÕES AUXILIARES ---
def calcular_pontos(lat, lon, azimute1, azimute2, distancia_km):
    R = 6371
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

def gerar_circulo(lat, lon, raio_metros, num_pontos=36):
    R = 6371000
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
    freq = float(freq)
    min_freq, max_freq = 700, 6000
    hue = ((freq - min_freq) / (max_freq - min_freq)) % 1.0
    r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(hue, 1, 1)]
    return simplekml.Color.rgb(r, g, b)

def faixas(freq):
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

def cor_operadora(operadora, alpha):
    operadora = str(operadora).strip().upper().split()[0] if operadora else ""
    if operadora == 'CLARO':
        return simplekml.Color.changealphaint(alpha, simplekml.Color.red)
    elif operadora == 'TELEFONICA':
        return simplekml.Color.changealphaint(alpha, simplekml.Color.purple)
    elif operadora == 'TIM':
        return simplekml.Color.changealphaint(alpha, simplekml.Color.blue)
    else:
        return simplekml.Color.changealphaint(alpha, simplekml.Color.white)

def process_file(input_file, distancia_km, setor_angulo, raio_circulo_metros, opacidade_percentual):
    ALPHA = int((opacidade_percentual / 100) * 255)
    REQUIRED_COLUMNS = ['Latitude', 'Longitude', 'Azimute', 'FreqTxMHz', 'NomeEntidade', 'NumEstacao', 'Tecnologia']
    if input_file.name.lower().endswith('.csv'):
        df = pd.read_csv(input_file)
    else:
        df = pd.read_excel(input_file, sheet_name=0)
    if not all(col in df.columns for col in REQUIRED_COLUMNS):
        raise ValueError("Planilha não possui todas as colunas necessárias.")
    df = df[REQUIRED_COLUMNS].dropna()
    df['NomeEntidade'] = df['NomeEntidade'].str.split().str[0].str.upper()
    kml = simplekml.Kml()
    kml.document.name = "Setores de Estações"
    kml.document.open = 1
    geojson_features = []
    grouped = df.groupby('NomeEntidade')
    for nome_entidade, group_entidade in grouped:
        pasta_entidade = kml.newfolder(name=str(nome_entidade))
        grouped_freq = group_entidade.groupby('FreqTxMHz')
        for freq, group_freq in grouped_freq:
            faixa = faixas(freq)
            pasta_freq = pasta_entidade.newfolder(name=f"Frequência {faixa} MHz")
            estacoes = group_freq['NumEstacao'].unique()
            for estacao_id in estacoes:
                sub_group = group_freq[group_freq['NumEstacao'] == estacao_id]
                lat = sub_group.iloc[0]['Latitude']
                lon = sub_group.iloc[0]['Longitude']
                pasta_estacao = pasta_freq.newfolder(name=f"Estação {estacao_id}")
                coords_circulo = gerar_circulo(lat, lon, raio_circulo_metros)
                pol_circulo = pasta_estacao.newpolygon(
                    name=f"Estação {estacao_id}",
                    description=f"Marcador da Estação Base: {nome_entidade}"
                )
                pol_circulo.outerboundaryis = coords_circulo
                pol_circulo.style.polystyle.color = cor_operadora(nome_entidade, ALPHA)
                pol_circulo.style.linestyle.width = 0
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
                for _, row in sub_group.iterrows():
                    az = float(str(row['Azimute']).replace(',', '.'))
                    freq_row = row['FreqTxMHz']
                    tecnologia = row['Tecnologia']
                    faixa = faixas(freq_row)
                    if (faixa) == 450:
                        distancia_km_setor = 1.5
                    elif (faixa) == 700:
                        distancia_km_setor = 1.4
                    elif (faixa) == 850:
                        distancia_km_setor = 1.3
                    elif  (faixa) == 900:
                        distancia_km_setor = 1.2
                    elif  (faixa) == 1800:
                        distancia_km_setor = 1.1
                    elif  (faixa) == 2100:
                        distancia_km_setor = 1
                    elif  (faixa) == 2300:
                        distancia_km_setor = 0.9
                    elif  (faixa) == 2500:
                        distancia_km_setor = 0.8
                    elif  (faixa) == 2600:
                        distancia_km_setor = 0.7
                    elif  (faixa) == 3500:
                        distancia_km_setor = 0.6
                    elif  (faixa) == 4900:
                        distancia_km_setor = 0.5
                    else:
                        distancia_km_setor = distancia_km
                    pts = calcular_pontos(lat, lon, az - setor_angulo, az + setor_angulo, distancia_km=distancia_km_setor)
                    cor_kml = get_color(freq_row)
                    cor_com_alpha = simplekml.Color.changealphaint(ALPHA, cor_kml)
                    pol_kml = pasta_estacao.newpolygon(
                        name=f"Setor {az}° - {freq_row} MHz - {tecnologia} - {nome_entidade}",
                        description=f"Entidade: {nome_entidade}, Estação: {estacao_id}, Frequência: {freq_row} MHz, Tecnologia: {tecnologia}"
                    )
                    alt = 0
                    pol_kml.outerboundaryis = [
                        (lon, lat, alt),
                        (pts[0][1], pts[0][0], alt),
                        (pts[1][1], pts[1][0], alt),
                        (lon, lat, alt)
                    ]
                    pol_kml.style.polystyle.color = cor_com_alpha
                    pol_kml.style.linestyle.width = 1.0
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
    temp_dir = tempfile.mkdtemp()
    output_kmz_path = os.path.join(temp_dir, OUTPUT_KMZ)
    output_geojson_path = os.path.join(temp_dir, OUTPUT_GEOJSON)
    kml.savekmz(output_kmz_path, format=False)
    gdf = gpd.GeoDataFrame.from_features(geojson_features)
    gdf.crs = "EPSG:31983"
    gdf.to_file(output_geojson_path, driver="GeoJSON")
    return output_kmz_path, output_geojson_path

# --- INTERFACE STREAMLIT ---
st.set_page_config(page_title="Gerador de KMZ e GeoJSON", layout="centered")
st.title("Gerador de KMZ e GeoJSON para Setores de Estações")
st.markdown("Faça upload de um arquivo CSV ou Excel com as colunas necessárias.")

with st.form("params_form"):
    uploaded_file = st.file_uploader("Arquivo de entrada (CSV/Excel)", type=["csv", "xlsx", "xls"])
    col1, col2 = st.columns(2)
    with col1:
        distancia_km = st.number_input("Distância do Setor (km)", min_value=0.1, max_value=10.0, value=0.5, step=0.1)
        raio_circulo_metros = st.number_input("Raio do Círculo (m)", min_value=1, max_value=500, value=40, step=1)
    with col2:
        setor_angulo = st.number_input("Ângulo do Setor (graus)", min_value=1, max_value=180, value=30, step=1)
        opacidade_percentual = st.slider("Opacidade (%)", min_value=0, max_value=100, value=60)
    submitted = st.form_submit_button("Gerar Arquivos")

if submitted and uploaded_file:
    with st.spinner("Processando..."):
        try:
            kmz_path, geojson_path = process_file(
                uploaded_file,
                distancia_km,
                setor_angulo,
                raio_circulo_metros,
                opacidade_percentual
            )
            st.success("Arquivos gerados com sucesso!")
            with open(kmz_path, "rb") as f:
                st.download_button("Baixar KMZ", f, file_name=OUTPUT_KMZ)
            with open(geojson_path, "rb") as f:
                st.download_button("Baixar GeoJSON", f, file_name=OUTPUT_GEOJSON)
        except Exception as e:
            st.error(f"Erro: {e}")
elif submitted and not uploaded_file:
    st.warning("Por favor, selecione um arquivo de entrada.")




