import re
from datetime import datetime, timezone, timedelta
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="Monitoramento Climático Urbano - ODS 13",
    page_icon="🌦️",
    layout="wide"
)

# ==============================================================================
# CONFIGURAÇÃO DO ENDEREÇO PADRÃO
# ==============================================================================
ENDERECO_PADRAO = "Rua Cachoeira do Sul, 271, Vila Jaguara, São Paulo, SP"
RESULTADO_PADRAO = [{
    "label": "Rua Cachoeira do Sul, 271 - Vila Jaguara - São Paulo - SP",
    "lat": -23.5124,
    "lon": -46.7449
}]

FUSO_SP = timezone(timedelta(hours=-3))


def restaurar_endereco():
    """Restaura o endereço padrão antes da renderização dos componentes."""
    st.session_state.endereco_busca = ENDERECO_PADRAO


def _buscar_photon(query: str) -> list:
    url = "https://photon.komoot.io/api/"
    params = {"q": query, "limit": 5}
    headers = {"User-Agent": "PainelClimaticoExtensaoODS13/1.0"}
    resp = requests.get(url, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    features = resp.json().get("features", [])

    resultados = []
    for feat in features:
        props = feat.get("properties", {})
        pais = props.get("country", "")
        if pais and pais.lower() not in ("brasil", "brazil"):
            continue

        lon, lat = feat["geometry"]["coordinates"]
        rua = props.get("street") or props.get("name") or ""
        numero = props.get("housenumber", "")
        bairro = props.get("district") or props.get("suburb") or props.get("locality") or ""
        cidade = props.get("city") or props.get("town") or props.get("county") or ""
        estado = props.get("state", "")

        partes = []
        if rua:
            partes.append(f"{rua}, {numero}" if numero else rua)
        if bairro and bairro != rua:
            partes.append(bairro)
        if cidade and cidade != bairro:
            partes.append(cidade)
        if estado:
            partes.append(estado)

        label = " - ".join(partes) if partes else query
        resultados.append({"label": label, "lat": float(lat), "lon": float(lon)})

    return resultados


def _buscar_nominatim(query: str) -> list:
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query,
        "format": "json",
        "limit": 5,
        "countrycodes": "br",
        "addressdetails": 1
    }
    headers = {
        "User-Agent": "PainelClimaticoExtensaoODS13/1.0",
        "Accept-Language": "pt-BR"
    }
    resp = requests.get(url, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    dados = resp.json()

    resultados = []
    for item in dados:
        end = item.get("address", {})
        rua = end.get("road") or end.get("pedestrian") or item.get("name", "")
        numero = end.get("house_number", "")
        bairro = end.get("suburb") or end.get("neighbourhood") or end.get("city_district", "")
        cidade = end.get("city") or end.get("town") or end.get("municipality", "")
        estado = end.get("state", "")

        partes = []
        if rua:
            partes.append(f"{rua}, {numero}" if numero else rua)
        if bairro and bairro != rua:
            partes.append(bairro)
        if cidade:
            partes.append(cidade)
        if estado:
            partes.append(estado)

        label = " - ".join(partes) if partes else item.get("display_name", query)
        resultados.append({
            "label": label,
            "lat": float(item["lat"]),
            "lon": float(item["lon"])
        })

    return resultados


@st.cache_data(ttl=86400, show_spinner=False)
def geocodificar_local(consulta: str) -> list:
    if consulta.strip().lower() == ENDERECO_PADRAO.strip().lower():
        return RESULTADO_PADRAO

    tentativas = [consulta]
    sem_numero = re.sub(r",?\s*\b\d+\b", "", consulta).strip(" ,")
    if sem_numero and sem_numero not in tentativas:
        tentativas.append(sem_numero)

    partes = [p.strip() for p in sem_numero.split(",") if p.strip()]
    if len(partes) >= 2:
        simplificada = f"{partes[0]}, {partes[-2] if partes[-1].upper() == 'SP' else partes[-1]}"
        if simplificada not in tentativas:
            tentativas.append(simplificada)

    for termo in tentativas:
        try:
            res = _buscar_photon(termo)
            if res:
                return res
        except Exception:
            pass

        try:
            res = _buscar_nominatim(termo)
            if res:
                return res
        except Exception:
            pass

    return []


def _consultar_met_norway(lat: float, lon: float) -> dict:
    """Fonte principal: MET Norway Locationforecast API (sem bloqueio de IP compartilhado)."""
    url = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
    params = {"lat": round(lat, 4), "lon": round(lon, 4)}
    headers = {"User-Agent": "PainelClimaticoExtensaoODS13/1.0 (https://github.com/matheusgeneze)"}
    resp = requests.get(url, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    series = resp.json()["properties"]["timeseries"]

    agora_det = series[0]["data"]["instant"]["details"]
    chuva_atual = (
        series[0]["data"].get("next_1_hours", {}).get("details", {}).get("precipitation_amount")
        or series[0]["data"].get("next_6_hours", {}).get("details", {}).get("precipitation_amount")
        or 0.0
    )

    por_dia = {}
    for item in series:
        dt_local = datetime.fromisoformat(item["time"].replace("Z", "+00:00")).astimezone(FUSO_SP)
        dia_str = dt_local.strftime("%Y-%m-%d")
        det = item["data"]["instant"]["details"]
        temp = float(det["air_temperature"])
        chuva = float(
            item["data"].get("next_1_hours", {}).get("details", {}).get("precipitation_amount")
            or (item["data"].get("next_6_hours", {}).get("details", {}).get("precipitation_amount", 0.0) / 6.0)
            or 0.0
        )

        if dia_str not in por_dia:
            por_dia[dia_str] = {"temps": [], "chuva": 0.0}
        por_dia[dia_str]["temps"].append(temp)
        por_dia[dia_str]["chuva"] += chuva

    daily_records = []
    for dia_str in sorted(por_dia.keys())[:7]:
        temps = por_dia[dia_str]["temps"]
        chuva_total = round(por_dia[dia_str]["chuva"], 1)
        prob = 80 if chuva_total >= 5.0 else (45 if chuva_total >= 0.5 else 15)
        daily_records.append({
            "time": dia_str,
            "temperature_2m_min": round(min(temps), 1),
            "temperature_2m_max": round(max(temps), 1),
            "precipitation_sum": chuva_total,
            "precipitation_probability_max": prob,
            "uv_index_max": 7.0
        })

    return {
        "fonte": "MET Norway Weather API",
        "current": {
            "temperature_2m": round(float(agora_det["air_temperature"]), 1),
            "relative_humidity_2m": int(round(float(agora_det["relative_humidity"]))),
            "precipitation": round(float(chuva_atual), 1),
            "wind_speed_10m": round(float(agora_det["wind_speed"]) * 3.6, 1),
        },
        "daily": daily_records
    }


def _consultar_open_meteo(lat: float, lon: float) -> dict:
    """Fonte secundária de contingência: Open-Meteo API."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,uv_index_max",
        "timezone": "America/Sao_Paulo",
        "forecast_days": 7
    }
    resp = requests.get(url, params=params, timeout=8)
    resp.raise_for_status()
    raw = resp.json()

    daily_df = pd.DataFrame(raw["daily"])
    return {
        "fonte": "Open-Meteo API",
        "current": {
            "temperature_2m": round(float(raw["current"]["temperature_2m"]), 1),
            "relative_humidity_2m": int(round(float(raw["current"]["relative_humidity_2m"]))),
            "precipitation": round(float(raw["current"]["precipitation"]), 1),
            "wind_speed_10m": round(float(raw["current"]["wind_speed_10m"]), 1),
        },
        "daily": daily_df.to_dict(orient="records")
    }


@st.cache_data(ttl=3600, show_spinner=False)
def buscar_dados_clima(lat_round: float, lon_round: float) -> dict:
    try:
        return _consultar_met_norway(lat_round, lon_round)
    except Exception:
        return _consultar_open_meteo(lat_round, lon_round)


# Cabeçalho
st.title("🌦️ Painel de Monitoramento Climático Urbano e Prevenção (ODS 13)")
st.markdown(
    "Projeto de Extensão Universitária — Monitoramento meteorológico hiperlocal por rua, "
    "bairro ou região para prevenção de riscos urbanos e conscientização climática."
)

# Barra lateral com endereço padrão e busca livre
st.sidebar.header("📍 Localização Monitorada")

if "endereco_busca" not in st.session_state:
    st.session_state.endereco_busca = ENDERECO_PADRAO

termo_busca = st.sidebar.text_input(
    "Busque por rua, bairro, CEP ou cidade:",
    key="endereco_busca",
    placeholder="Ex: Rua Cachoeira do Sul, 271, Vila Jaguara, SP"
)

st.sidebar.button(
    "🏠 Restaurar endereço padrão",
    on_click=restaurar_endereco,
    use_container_width=True
)

if not termo_busca.strip():
    st.info("👈 Digite o nome de uma rua, bairro ou região na barra lateral para consultar o clima.")
    st.stop()

resultados = geocodificar_local(termo_busca.strip())

if not resultados:
    st.warning(
        f"Não encontramos o endereço **'{termo_busca}'**. "
        "Tente buscar pelo nome da rua ou bairro seguido da cidade (ex.: *Vila Jaguara, São Paulo*)."
    )
    st.stop()

indice_escolhido = st.sidebar.selectbox(
    "Confirme o endereço encontrado:",
    options=range(len(resultados)),
    format_func=lambda i: resultados[i]["label"]
)

local_selecionado = resultados[indice_escolhido]
lat = local_selecionado["lat"]
lon = local_selecionado["lon"]
nome_exibicao = local_selecionado["label"]

st.sidebar.caption(f"🌐 Coordenadas: `{lat:.5f}, {lon:.5f}`")
st.sidebar.markdown("---")
st.sidebar.info(
    "**Objetivo (ODS 13):** Democratizar o acesso a dados climáticos hiperlocais em tempo real "
    "e orientar moradores sobre prevenção a eventos extremos."
)

# Consulta meteorológica
try:
    dados = buscar_dados_clima(round(lat, 2), round(lon, 2))
    atual = dados["current"]
    diario = pd.DataFrame(dados["daily"])
    diario["time"] = pd.to_datetime(diario["time"]).dt.strftime("%d/%m")

    temp_min = diario["temperature_2m_min"].iloc[0]
    temp_max = diario["temperature_2m_max"].iloc[0]

    # KPIs: Temperatura / Mínima e Máxima / Umidade Relativa / Vento
    st.subheader(f"Condições Atuais — {nome_exibicao}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🌡️ Temperatura", f"{atual['temperature_2m']} °C")
    c2.metric("↕️ Mínima / Máxima", f"{temp_min} °C / {temp_max} °C")
    c3.metric("💧 Umidade Relativa", f"{atual['relative_humidity_2m']}%")
    c4.metric("💨 Vento", f"{atual['wind_speed_10m']} km/h")

    # Alertas dinâmicos para a comunidade
    st.subheader("⚠️ Alertas e Recomendações Preventivas")
    alertas = []
    if atual["temperature_2m"] >= 30:
        alertas.append("🔥 **Calor intenso:** Mantenha hidratação constante, evite exposição solar entre 10h e 16h e reduza o uso simultâneo de aparelhos de alto consumo energético.")
    if atual["relative_humidity_2m"] <= 40:
        alertas.append("🏜️ **Baixa umidade do ar:** Umidifique ambientes internos e evite atividades físicas intensas ao ar livre.")
    if diario["precipitation_sum"].iloc[0] >= 15 or diario["precipitation_probability_max"].iloc[0] >= 70:
        alertas.append("⛈️ **Risco de chuva forte nas próximas horas:** Evite áreas sujeitas a alagamentos, não descarte lixo nas vias públicas (prevenção de entupimento de bueiros) e desconecte eletrônicos sensíveis em caso de raios.")
    if diario["uv_index_max"].iloc[0] >= 8:
        alertas.append("☀️ **Índice UV muito alto hoje:** Uso obrigatório de protetor solar, óculos UV e boné/chapéu.")

    if not alertas:
        st.success("✅ Condições climáticas estáveis no momento. Siga as boas práticas de economia de água e energia no condomínio.")
    else:
        for a in alertas:
            st.warning(a)

    # Gráficos
    col_g1, col_g2 = st.columns(2)

    with col_g1:
        fig_temp = go.Figure()
        fig_temp.add_trace(go.Scatter(
            x=diario["time"], y=diario["temperature_2m_max"],
            mode="lines+markers", name="Máxima (°C)", line=dict(color="#FF6B6B", width=3)
        ))
        fig_temp.add_trace(go.Scatter(
            x=diario["time"], y=diario["temperature_2m_min"],
            mode="lines+markers", name="Mínima (°C)", line=dict(color="#4ECDC4", width=3)
        ))
        fig_temp.update_layout(
            title="Previsão de Temperatura Máxima e Mínima (7 dias)",
            xaxis_title="Data", yaxis_title="Temperatura (°C)",
            legend=dict(orientation="h", y=1.12)
        )
        st.plotly_chart(fig_temp, use_container_width=True)

    with col_g2:
        fig_chuva = px.bar(
            diario, x="time", y="precipitation_sum",
            labels={"time": "Data", "precipitation_sum": "Chuva Acumulada (mm)"},
            title="Volume Previsto de Chuvas (7 dias)",
            color="precipitation_probability_max",
            color_continuous_scale="Blues"
        )
        st.plotly_chart(fig_chuva, use_container_width=True)

    # Mapa da região pesquisada
    with st.expander("🗺️ Ver localização exata no mapa", expanded=False):
        st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}), zoom=15)

    # Guia educativo ODS 13
    st.markdown("---")
    st.subheader("🌱 Guia Comunitário de Mitigação e Adaptação Climática (ODS 13)")
    g1, g2, g3 = st.columns(3)
    with g1:
        st.markdown("**1. Prevenção contra Alagamentos**")
        st.write("Respeite os horários de coleta de lixo do condomínio e nunca descarte resíduos ou óleo de cozinha nas redes pluviais.")
    with g2:
        st.markdown("**2. Eficiência Energética e Ilhas de Calor**")
        st.write("Priorize ventilação cruzada nos horários amenos, desligue equipamentos em stand-by e apoie a manutenção de áreas verdes no entorno.")
    with g3:
        st.markdown("**3. Uso Racional da Água**")
        st.write("Reaproveite água da máquina de lavar para limpeza de áreas externas e monitore vazamentos internos.")

    st.caption(f"Fontes: OpenStreetMap (Geocodificação) & {dados['fonte']} (Dados Meteorológicos).")

except Exception as e:
    st.error(f"Não foi possível carregar os dados meteorológicos no momento: {e}")