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

# Regiões da Grande São Paulo para consulta
LOCAIS = {
    "São Paulo - Centro / Zona Sul": (-23.5505, -46.6333),
    "São Paulo - Zona Leste": (-23.5489, -46.4714),
    "São Paulo - Zona Norte": (-23.4801, -46.6256),
    "São Paulo - Zona Oeste": (-23.5567, -46.7235),
    "ABC Paulista (Santo André)": (-23.6639, -46.5383),
    "Guarulhos": (-23.4543, -46.5337),
}

@st.cache_data(ttl=1800)
def buscar_dados_clima(lat: float, lon: float):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,cloud_cover",
        "hourly": "temperature_2m,precipitation_probability,precipitation",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,uv_index_max",
        "timezone": "America/Sao_Paulo",
        "forecast_days": 7
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()

# Cabeçalho
st.title("🌦️ Painel de Monitoramento Climático Urbano e Prevenção (ODS 13)")
st.markdown(
    "Projeto de Extensão Universitária — Ferramenta aberta para acompanhamento meteorológico local, "
    "prevenção de riscos urbanos e conscientização climática comunitária."
)

# Filtro lateral
st.sidebar.header("Configurações da Consulta")
local_escolhido = st.sidebar.selectbox("Selecione a região urbana:", list(LOCAIS.keys()))
lat, lon = LOCAIS[local_escolhido]

st.sidebar.markdown("---")
st.sidebar.info(
    "**Objetivo (ODS 13):** Democratizar o acesso a dados climáticos locais em tempo real "
    "e orientar moradores sobre prevenção a eventos extremos e consumo consciente."
)

try:
    dados = buscar_dados_clima(lat, lon)
    atual = dados["current"]
    diario = pd.DataFrame(dados["daily"])
    diario["time"] = pd.to_datetime(diario["time"]).dt.strftime("%d/%m")
    horario = pd.DataFrame(dados["hourly"]).head(24)
    horario["hora"] = pd.to_datetime(horario["time"]).dt.strftime("%H:%M")

    # KPIs em tempo real
    st.subheader(f"Condições Atuais — {local_escolhido}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🌡️ Temperatura", f"{atual['temperature_2m']} °C")
    c2.metric("💧 Umidade Relativa", f"{atual['relative_humidity_2m']}%")
    c3.metric("🌧️ Precipitação Atual", f"{atual['precipitation']} mm")
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

    st.caption("Fonte de dados meteorológicos: Open-Meteo API (atualização automática a cada 30 min).")

except Exception as e:
    st.error(f"Não foi possível carregar os dados meteorológicos no momento: {e}")