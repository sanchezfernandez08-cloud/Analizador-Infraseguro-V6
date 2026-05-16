"""
============================================================
CALCULADORA DE VALOR DE RECONSTRUCCIÓN — SEGUROS CHILE
Conforme DFL 251, DS 1055, CCom art. 553,
Ley 21.442 (Copropiedad) y NCG 556 CMF (dic. 2025)
============================================================
Para ejecutar localmente:
    pip install streamlit pandas requests
    streamlit run app.py

Para publicar en Streamlit Community Cloud:
    1. Suba este archivo y requirements.txt a GitHub
    2. En Streamlit Cloud, agregue en Secrets:
       GOOGLE_MAPS_API_KEY = "su_clave_aqui"
    3. Seleccione app.py como archivo principal
============================================================
"""

import streamlit as st
import pandas as pd
import requests
from datetime import date

# ─────────────────────────────────────────────────────────
# GOOGLE MAPS API (opcional — para estimación de superficie)
# ─────────────────────────────────────────────────────────
def get_gmaps_key():
    try:
        return st.secrets.get("GOOGLE_MAPS_API_KEY", "")
    except Exception:
        return ""

def geocodificar_direccion(direccion, api_key):
    """Retorna (lat, lng, formatted_address) o None si falla."""
    if not api_key or not direccion.strip():
        return None
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    r = requests.get(url, params={"address": direccion + ", Chile", "key": api_key}, timeout=5)
    if r.status_code != 200:
        return None
    data = r.json()
    if data.get("status") != "OK" or not data.get("results"):
        return None
    loc = data["results"][0]["geometry"]["location"]
    addr = data["results"][0]["formatted_address"]
    return loc["lat"], loc["lng"], addr

def buscar_edificio_places(lat, lng, api_key):
    """
    Intenta obtener datos del edificio desde Places API.
    Retorna dict con info útil o None.
    """
    if not api_key:
        return None
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    r = requests.get(url, params={
        "location": f"{lat},{lng}",
        "radius": 50,
        "type": "premise",
        "key": api_key,
    }, timeout=5)
    if r.status_code != 200:
        return None
    data = r.json()
    if data.get("status") != "OK" or not data.get("results"):
        return None
    return data["results"][0]

# ─────────────────────────────────────────────────────────
# PORCENTAJES BIENES COMUNES — Marco normativo y práctica
# ─────────────────────────────────────────────────────────
# Fuentes:
#   · Edifito / Ley 21.442: bienes comunes = 50–70% del VR total
#   · ComunidadFeliz: bienes comunes = 60–80% del monto asegurado
#   · OGUC art. 5.1.11: superficie común < 20% sup. útil no se
#     contabiliza para coeficiente de constructibilidad
#   · Práctica de mercado: superficie común ≈ 30–50% sup. total
#     (varía según amenidades del edificio)

PERFILES_EDIFICIO = {
    "Básico (pocos pisos, sin amenidades)": {
        "sup_comun_pct": 0.30,
        "descripcion": "Edificio simple, sin subterráneos, piscina ni gimnasio. Pasillos y escaleras básicos.",
        "rango": "25–35% de la superficie total",
        "fuente": "Práctica de mercado · OGUC art. 5.1.11",
    },
    "Estándar (piscina, gimnasio, 1 subterráneo)": {
        "sup_comun_pct": 0.40,
        "descripcion": "Edificio típico urbano con amenidades básicas y un nivel de estacionamientos.",
        "rango": "35–45% de la superficie total",
        "fuente": "Edifito / Ley 21.442 · Práctica de mercado",
    },
    "Alto estándar (múltiples subterráneos, amenidades completas)": {
        "sup_comun_pct": 0.50,
        "descripcion": "Edificio con 2+ subterráneos, sala de eventos, quinchos, gimnasio, piscina, spa.",
        "rango": "45–55% de la superficie total",
        "fuente": "Edifito / Ley 21.442 · ComunidadFeliz · NCG 556 CMF",
    },
    "Premium (torre con todas las amenidades)": {
        "sup_comun_pct": 0.60,
        "descripcion": "Torre de gran altura con múltiples subterráneos, lobby doble altura, amenities de lujo.",
        "rango": "55–70% de la superficie total",
        "fuente": "Edifito / Ley 21.442: 'bienes comunes = 50–70% del VR total'",
    },
    "Ingreso manual": {
        "sup_comun_pct": None,
        "descripcion": "Ingrese directamente los porcentajes según la información del edificio.",
        "rango": "—",
        "fuente": "Reglamento de copropiedad / Tasador",
    },
}

# ─────────────────────────────────────────────────────────
# REFERENCIAS VUB (UF/m²) — Mercado 2025–2026
# ─────────────────────────────────────────────────────────
REFERENCIAS_VUB = {
    ("Metropolitana", "Casa / Albañilería"):   {"Básico": (18,22), "Medio": (23,30), "Alto": (31,42)},
    ("Metropolitana", "Casa / Metalcon"):       {"Básico": (16,20), "Medio": (21,28), "Alto": None},
    ("Metropolitana", "Depto / Hormigón"):      {"Básico": None,    "Medio": (25,33), "Alto": (34,48)},
    ("Metropolitana", "Edificio / Hormigón"):   {"Básico": None,    "Medio": (26,35), "Alto": (36,52)},
    ("Metropolitana", "Comunidad / Hormigón"):  {"Básico": None,    "Medio": (25,34), "Alto": (35,50)},
    ("Intermedia",    "Casa / Albañilería"):    {"Básico": (17,21), "Medio": (22,29), "Alto": (30,40)},
    ("Intermedia",    "Casa / Metalcon"):       {"Básico": (15,19), "Medio": (20,27), "Alto": None},
    ("Intermedia",    "Depto / Hormigón"):      {"Básico": None,    "Medio": (24,32), "Alto": (33,46)},
    ("Intermedia",    "Edificio / Hormigón"):   {"Básico": None,    "Medio": (25,34), "Alto": (35,50)},
    ("Intermedia",    "Comunidad / Hormigón"):  {"Básico": None,    "Medio": (24,33), "Alto": (34,48)},
    ("Aislada",       "Casa / Albañilería"):    {"Básico": (20,26), "Medio": (27,36), "Alto": (37,50)},
    ("Aislada",       "Casa / Metalcon"):       {"Básico": (18,23), "Medio": (24,32), "Alto": None},
    ("Aislada",       "Depto / Hormigón"):      {"Básico": None,    "Medio": (29,38), "Alto": (39,55)},
    ("Aislada",       "Edificio / Hormigón"):   {"Básico": None,    "Medio": (30,40), "Alto": (41,58)},
    ("Aislada",       "Comunidad / Hormigón"):  {"Básico": None,    "Medio": (29,39), "Alto": (40,56)},
}

ZONA_CORTA = {
    "Metropolitana (RM y ciudades grandes)": "Metropolitana",
    "Intermedia (ciudades medianas)":        "Intermedia",
    "Aislada (zonas rurales o extremas)":    "Aislada",
}
TS_LABEL = {
    ("Casa","Albañilería"): "Casa / Albañilería",
    ("Casa","Metalcon"):    "Casa / Metalcon",
    ("Depto","Hormigón"):   "Depto / Hormigón",
    ("Edificio","Hormigón"):"Edificio / Hormigón",
    ("Comunidad","Hormigón"):"Comunidad / Hormigón",
}

FACTOR_GEOGRAFICO = {
    "Metropolitana (RM y ciudades grandes)": 1.05,
    "Intermedia (ciudades medianas)":        1.00,
    "Aislada (zonas rurales o extremas)":    1.15,
}
SISTEMAS_POR_TIPO = {
    "Casa":["Albañilería","Metalcon"],
    "Depto":["Hormigón"],"Edificio":["Hormigón"],"Comunidad":["Hormigón"],
}
NIVELES_POR_TS = {
    ("Casa","Albañilería"):["Básico","Medio","Alto"],
    ("Casa","Metalcon"):["Básico","Medio"],
    ("Depto","Hormigón"):["Medio","Alto"],
    ("Edificio","Hormigón"):["Medio","Alto"],
    ("Comunidad","Hormigón"):["Medio","Alto"],
}
COSTOS_IND = {"Diseño del proyecto":0.03,"Gastos generales de obra":0.06,
              "Utilidad del contratista":0.12,"Imprevistos":0.10}
TASA_IVA = 0.19

# ─────────────────────────────────────────────────────────
# MOTOR
# ─────────────────────────────────────────────────────────
def factor_normativo(anio):
    if anio<1985: return 1.15
    if anio<=2000: return 1.10
    if anio<=2010: return 1.05
    return 1.00

def factor_altura(pisos):
    if pisos<=2: return 1.00
    if pisos<=5: return 1.05
    if pisos<=10: return 1.10
    return 1.15

def calcular_vr(vub, sup, zona_label, pisos, anio, aplica_iva):
    fg=FACTOR_GEOGRAFICO[zona_label]; fn=factor_normativo(anio); fa=factor_altura(pisos)
    cd=sup*vub*fg*fn*fa
    ind_det={k:cd*v for k,v in COSTOS_IND.items()}
    ci=sum(ind_det.values()); st_=cd+ci
    iv=st_*TASA_IVA if aplica_iva else 0.0
    return {"vub":vub,"fg":fg,"fn":fn,"fa":fa,"cd":cd,"ind_det":ind_det,
            "ci":ci,"st":st_,"iv":iv,"aplica_iva":aplica_iva,"vr":st_+iv}

def evaluar(monto, vr):
    if monto<=0 or vr<=0: return 0.0, False
    r=monto/vr; return r, r<1.0

def indemn(danio, monto, vr):
    ratio,infra=evaluar(monto,vr)
    return danio*ratio if infra else danio

# ─────────────────────────────────────────────────────────
# UI HELPERS
# ─────────────────────────────────────────────────────────
def panel_ref_vub(zona_label, tipo, sis, niv):
    zc=ZONA_CORTA.get(zona_label,""); ts=TS_LABEL.get((tipo,sis),"")
    ref=REFERENCIAS_VUB.get((zc,ts),{}); rango=ref.get(niv)
    with st.expander("📊 Valores de referencia de mercado (UF/m²)", expanded=False):
        st.caption("Rangos estimados 2025–2026. **No son valores oficiales.** "
                   "Tabla MINVU en pesos: [minvu.gob.cl](https://www.minvu.gob.cl/elementos-tecnicos/tabla-de-costos-unitarios/)")
        if rango:
            st.info(f"**Rango referencial — {tipo}/{sis}/{niv}/{zc}:** **{rango[0]}–{rango[1]} UF/m²** (promedio {round((rango[0]+rango[1])/2,1)})")
        filas=[{"Tipo/Sistema":ts2,"Nivel":nv,"Mín":rg[0],"Máx":rg[1],"Promedio ref.":round((rg[0]+rg[1])/2,1)}
               for (zc2,ts2),nivs in REFERENCIAS_VUB.items() if zc2==zc
               for nv,rg in nivs.items() if rg]
        if filas:
            st.dataframe(pd.DataFrame(filas).sort_values(["Tipo/Sistema","Nivel"]),
                         use_container_width=True, hide_index=True)

def campo_vub(prefix, zona_label, tipo, sis, niv):
    zc=ZONA_CORTA.get(zona_label,""); ts=TS_LABEL.get((tipo,sis),"")
    ref=REFERENCIAS_VUB.get((zc,ts),{}); rango=ref.get(niv)
    ph=f"Ref: {rango[0]}–{rango[1]} UF/m² (prom. {round((rango[0]+rango[1])/2,1)})" if rango else "Ej: 28.0"
    return st.number_input("VUB — Valor Unitario Base (UF/m²)",
                           min_value=1.0, max_value=200.0, value=None,
                           step=0.5, format="%.1f", placeholder=ph,
                           key=f"{prefix}_vub",
                           help="Ingrese según tasación, corredor o tabla MINVU convertida a UF.")

def ui_comp(prefix, zona, pisos, anio, aplica_iva,
            default_tipo="Comunidad", label_tipo="Tipo de inmueble"):
    tipos=list(SISTEMAS_POR_TIPO.keys())
    idx=tipos.index(default_tipo) if default_tipo in tipos else 0
    tipo=st.selectbox(label_tipo, tipos, index=idx, key=f"{prefix}_tipo")
    sis=st.selectbox("Sistema constructivo", SISTEMAS_POR_TIPO[tipo], key=f"{prefix}_sis")
    niv=st.selectbox("Nivel de terminaciones", NIVELES_POR_TS[(tipo,sis)],
                     key=f"{prefix}_niv", help="Básico=sin lujos · Medio=estándar · Alto=premium")
    if zona: panel_ref_vub(zona, tipo, sis, niv)
    vub=campo_vub(prefix, zona, tipo, sis, niv)
    sup=st.number_input("Superficie (m²)", min_value=1, max_value=500_000,
                        value=None, placeholder="Ej: 3500", key=f"{prefix}_sup")
    monto=st.number_input("Monto asegurado en póliza (UF)", min_value=0,
                          value=None, placeholder="0", key=f"{prefix}_monto",
                          help="Ingrese 0 si no hay seguro contratado.")
    return {"tipo":tipo,"sis":sis,"niv":niv,"vub":vub,"sup":sup,"monto":monto,
            "zona":zona,"pisos":pisos,"anio":anio,"aplica_iva":aplica_iva}

def validar_comp(d, campo):
    errs=[]
    if not d.get("vub"): errs.append(f"Ingrese el VUB (UF/m²) de {campo}.")
    if not d.get("sup"): errs.append(f"Ingrese la superficie de {campo}.")
    if d.get("monto") is None: errs.append(f"Ingrese el monto asegurado de {campo} (puede ser 0).")
    return errs

def ui_show(label, res, datos, danio_pct, nota="", expanded=True):
    vr=res["vr"]; monto=datos.get("monto") or 0
    ratio,infra=evaluar(monto,vr)
    danio_=vr*(danio_pct/100); ind_=indemn(danio_,monto,vr)
    with st.expander(f"📦 {label} — **{vr:,.2f} UF**", expanded=expanded):
        if nota: st.caption(nota)
        if monto<=0: st.info("ℹ️ Sin monto asegurado.")
        elif infra: st.warning(f"⚠️ **Infrasegurado.** Cobertura: **{ratio*100:.1f}%** — Brecha: **{vr-monto:,.2f} UF**")
        else: st.success(f"✅ Cobertura adecuada ({ratio*100:.1f}%)")
        c1,c2,c3=st.columns(3)
        c1.metric("Valor de reconstrucción",f"{vr:,.2f} UF")
        c2.metric("Monto asegurado",f"{monto:,.2f} UF" if monto>0 else "No indicado")
        c3.metric("Cobertura",f"{ratio*100:.1f}%" if monto>0 else "—",
                  delta=f"{(ratio-1)*100:.1f}%" if monto>0 else None,
                  delta_color="normal" if not infra else "inverse")
        if monto>0: st.progress(min(ratio,1.0),text=f"Cobertura: {ratio*100:.1f}%")
        st.markdown("**Desglose del cálculo**")
        st.markdown(f"""
| # | Concepto | Valor |
|---|----------|-------|
| 1 | VUB — {datos.get('tipo','')}/{datos.get('sis','')}/{datos.get('niv','')} | **{res['vub']:.1f} UF/m²** |
| 2 | × Factor geográfico | {res['fg']:.2f} |
| 3 | × Factor normativo (año {datos.get('anio','')}) | {res['fn']:.2f} |
| 4 | × Factor altura ({datos.get('pisos','')} pisos) | {res['fa']:.2f} |
| 5 | **Costo directo** ({(datos.get('sup') or 0):,.0f} m²) | **{res['cd']:,.2f} UF** |
| 6a | + Diseño del proyecto (3%) | {res['ind_det']['Diseño del proyecto']:,.2f} UF |
| 6b | + Gastos generales de obra (6%) | {res['ind_det']['Gastos generales de obra']:,.2f} UF |
| 6c | + Utilidad del contratista (12%) | {res['ind_det']['Utilidad del contratista']:,.2f} UF |
| 6d | + Imprevistos (10%) | {res['ind_det']['Imprevistos']:,.2f} UF |
| 7 | **Subtotal sin IVA** | **{res['st']:,.2f} UF** |
| 8 | + IVA 19% | {res['iv']:,.2f} UF |
| ✓ | **VALOR DE RECONSTRUCCIÓN** | **{vr:,.2f} UF** |
""")
        st.markdown(f"**Simulación — daño del {danio_pct}%**")
        s1,s2,s3=st.columns(3)
        s1.metric("Daño estimado",f"{danio_:,.2f} UF")
        s2.metric("Indemnización real",f"{ind_:,.2f} UF" if monto>0 else "—")
        if infra:
            s3.metric("Pérdida no cubierta",f"{danio_-ind_:,.2f} UF",delta_color="inverse")
            st.warning(f"**Art. 553 CCom:** recibiría **{ind_:,.2f} UF** en vez de **{danio_:,.2f} UF**. Pérdida: **{danio_-ind_:,.2f} UF**.")

# ─────────────────────────────────────────────────────────
# INFORME TXT
# ─────────────────────────────────────────────────────────
def _bloque(etiq, res, datos, danio_pct):
    monto=datos.get("monto") or 0; vr=res["vr"]
    ratio,infra=evaluar(monto,vr); d=vr*(danio_pct/100); ind_=indemn(d,monto,vr)
    lns=[f"  [{etiq}]",
         f"    Tipo/Sistema/Nivel : {datos.get('tipo','')}/{datos.get('sis','')}/{datos.get('niv','')}",
         f"    VUB ingresado      : {res['vub']:.1f} UF/m²",
         f"    Superficie         : {datos.get('sup',0):,.0f} m²",
         f"    Factor geográfico  : {res['fg']:.2f}  |  Factor normativo: {res['fn']:.2f}  |  Factor altura: {res['fa']:.2f}",
         f"    Costo directo      : {res['cd']:>12,.2f} UF",
         f"    Costos ind. (31%)  : {res['ci']:>12,.2f} UF",
         f"    Subtotal s/IVA     : {res['st']:>12,.2f} UF",
         (f"    IVA 19%            : {res['iv']:>12,.2f} UF" if res['aplica_iva'] else f"    IVA 19%            :       no aplica"),
         f"    VALOR RECONSTRUCCIÓN: {vr:>11,.2f} UF",
         "",
         (f"    Monto asegurado    : {monto:>12,.2f} UF" if monto>0 else f"    Monto asegurado    :    No indicado"),
         (f"    Cobertura          : {ratio*100:>11.1f} %" if monto>0 else f"    Cobertura          :            —"),
         f"    Infraseguro        : {'SÍ ⚠' if infra else 'NO ✓'}"]
    if infra: lns.append(f"    Brecha sin cubrir  : {vr-monto:>12,.2f} UF")
    lns+=[f"    Simulación ({danio_pct:.0f}% daño)",
          (f"      Daño estimado    : {d:>12,.2f} UF"),
          (f"      Indemnización    : {ind_:>12,.2f} UF" if monto>0 else f"      Indemnización    :    Ver VR")]
    if infra: lns.append(f"      Pérdida          : {d-ind_:>12,.2f} UF")
    return "\n".join(lns)

def generar_informe(caso):
    sep="="*64; sep2="─"*64; hoy=date.today().strftime("%d/%m/%Y")
    lns=["INFORME DE VALOR DE RECONSTRUCCIÓN",
         "Conforme DFL 251, DS 1055, CCom art. 553 y Ley 21.442",sep,
         f"  Nombre / Referencia  : {caso['nombre']}",
         f"  Dirección            : {caso['direccion']}",
         f"  Zona geográfica      : {caso.get('zona','—')}",
         f"  Número de pisos      : {caso.get('pisos','—')}",
         f"  Año de construcción  : {caso.get('anio','—')}",
         f"  Fecha de cálculo     : {hoy}",sep,""]
    modo=caso["modo"]
    if modo=="simple":
        lns+=["INMUEBLE COMPLETO\n",_bloque("Inmueble completo",caso["comp"]["res"],caso["comp"],caso["danio_pct"])]
    elif modo=="comunes":
        lns+=["BIENES Y ESPACIOS COMUNES (Ley 21.442 art. 43)\n",
              _bloque("Bienes comunes",caso["comp"]["res"],caso["comp"],caso["danio_pct"])]
    elif modo=="comunidad":
        # Desglose superficies
        if caso.get("desglose"):
            dg=caso["desglose"]
            lns+=["DESGLOSE DE SUPERFICIES",
                  f"  Superficie total edificio  : {dg['sup_total']:,.0f} m²",
                  f"  Perfil de amenidades       : {dg['perfil']}",
                  f"  % bienes comunes aplicado  : {dg['pct_comun']*100:.0f}%",
                  f"  Superficie bienes comunes  : {dg['sup_comun']:,.0f} m²",
                  f"  Superficie unidades priv.  : {dg['sup_units']:,.0f} m²",
                  f"  Fuente referencia          : {dg['fuente']}",""]
        lns+=["PÓLIZA COLECTIVA — NCG 556 CMF","","BLOQUE 1: BIENES Y ESPACIOS COMUNES\n",
              _bloque("Bienes comunes",caso["comp_comun"]["res"],caso["comp_comun"],caso["danio_pct"]),
              "",sep2,"","BLOQUE 2: UNIDADES PRIVADAS\n"]
        for u in caso["unidades"]:
            lns+=[_bloque(u.get("nombre") or "Unidad",u["res"],u,caso["danio_pct"]),""]
        vr_t=caso["total_vr"]; m_t=caso["total_monto"]
        r_t,i_t=evaluar(m_t,vr_t); d_t=vr_t*(caso["danio_pct"]/100); ind_t=indemn(d_t,m_t,vr_t)
        lns+=[sep2,"CONSOLIDADO TOTAL",
              f"  VR bienes comunes : {caso['vr_comun']:>12,.2f} UF",
              f"  VR unidades       : {caso['vr_units']:>12,.2f} UF",
              f"  VR TOTAL          : {vr_t:>12,.2f} UF",
              (f"  Monto asegurado   : {m_t:>12,.2f} UF" if m_t>0 else f"  Monto asegurado   :    No indicado"),
              (f"  Cobertura global  : {r_t*100:>11.1f} %" if m_t>0 else f"  Cobertura global  :            —"),
              f"  Infraseguro       : {'SÍ ⚠' if i_t else 'NO ✓'}"]
        if m_t>0: lns+=[f"  Daño {caso['danio_pct']:.0f}% estimado   : {d_t:>12,.2f} UF",
                         f"  Indemnización     : {ind_t:>12,.2f} UF"]
        if i_t: lns.append(f"  Pérdida           : {d_t-ind_t:>12,.2f} UF")
    lns+=["",sep2,"Nota: Informe referencial. Verificar con tasador habilitado.",
          "VUB ingresado por el usuario. Tabla MINVU oficial: minvu.gob.cl",
          "Normativa: DFL 251 · DS 1055 · CCom 553 · Ley 21.442 · NCG 556 CMF"]
    return "\n".join(lns)

# ─────────────────────────────────────────────────────────
# CONFIGURACIÓN PÁGINA
# ─────────────────────────────────────────────────────────
st.set_page_config(page_title="Seguro de Reconstrucción — Chile",
                   page_icon="🏢", layout="centered", initial_sidebar_state="collapsed")
st.markdown("""<style>
    .stApp{max-width:820px;margin:auto}
    .block-container{padding-top:2rem;padding-bottom:3rem}
    div[data-testid="stMetricValue"]{font-size:1.3rem}
    h1{font-size:1.6rem!important}h2{font-size:1.2rem!important}
</style>""", unsafe_allow_html=True)

st.title("🏢 Calculadora de Valor de Reconstrucción")
st.caption("Seguros de inmuebles en Chile · DFL 251 · DS 1055 · CCom art. 553 · Ley 21.442 · NCG 556 CMF")

tab_calc, tab_casos, tab_como = st.tabs(["📐 Calcular", "📋 Mis casos", "ℹ️ Marco normativo"])

# ══════════════════════════════════════════════════════════
# PESTAÑA: CALCULAR
# ══════════════════════════════════════════════════════════
with tab_calc:

    # ── Identificación ──
    st.subheader("Identificación de la propiedad")
    cn, cd2 = st.columns(2)
    with cn: nombre    = st.text_input("Nombre o referencia", placeholder="Ej: Edificio Torres del Parque")
    with cd2: direccion = st.text_input("Dirección completa", placeholder="Calle, número, comuna, región")

    # ── Estimación de superficie por dirección ──
    api_key = get_gmaps_key()
    sup_estimada = None
    if direccion.strip():
        with st.expander("🗺️ Herramienta de apoyo — Superficie desde dirección", expanded=False):
            if api_key:
                if st.button("Buscar coordenadas y ubicar en mapa", key="geo_btn"):
                    with st.spinner("Consultando Google Maps..."):
                        geo = geocodificar_direccion(direccion, api_key)
                    if geo:
                        lat, lng, addr = geo
                        st.success(f"Dirección encontrada: {addr}")
                        st.map(pd.DataFrame({"lat":[lat],"lon":[lng]}), zoom=16)
                        st.info(
                            "✏️ **Cómo medir la superficie del edificio:**\n"
                            "1. Abra [Google Earth](https://earth.google.com) o [Google Maps](https://maps.google.com)\n"
                            "2. Busque la dirección: **" + addr + "**\n"
                            "3. En Google Earth: use la herramienta **Medir** → Polígono → dibuje el contorno del edificio\n"
                            "4. En Google Maps: haga clic derecho sobre el edificio → **Medir distancia** para obtener perímetro\n"
                            "5. Ingrese la superficie obtenida abajo, multiplicada por el número de pisos"
                        )
                        st.caption(f"Coordenadas: {lat:.5f}, {lng:.5f}")
                    else:
                        st.warning("No se encontró la dirección. Verifique e intente nuevamente.")
            else:
                st.info(
                    "**Sin API de Google Maps configurada** — para activar la búsqueda automática, "
                    "agregue `GOOGLE_MAPS_API_KEY` en los Secrets de Streamlit.\n\n"
                    "**Mientras tanto, puede medir la superficie manualmente:**\n"
                    "1. Abra [Google Earth](https://earth.google.com) o [Google Maps](https://maps.google.com)\n"
                    "2. Busque la dirección ingresada\n"
                    "3. En Google Earth: use **Medir → Polígono** para trazar el contorno del edificio → obtenga el área de la planta\n"
                    "4. Multiplique el área de la planta × número de pisos (incluyendo subterráneos) para obtener la superficie total\n"
                    "5. Ingrese ese valor en el campo de superficie del formulario"
                )
                st.markdown("📐 [Abrir Google Earth Web](https://earth.google.com) &nbsp;|&nbsp; [Abrir Google Maps](https://maps.google.com)")

    # ── Datos generales ──
    st.subheader("Datos generales del inmueble")
    g1,g2,g3,g4=st.columns(4)
    with g1:
        zona=st.selectbox("Zona geográfica",[""]+ list(FACTOR_GEOGRAFICO.keys()),
                          format_func=lambda x:"Seleccionar..." if x=="" else x)
    with g2: pisos=st.number_input("N° de pisos",min_value=1,max_value=100,value=None,placeholder="Ej: 12")
    with g3: anio=st.number_input("Año construc.",min_value=1900,max_value=2025,value=None,placeholder="Ej: 2005")
    with g4: aplica_iva=st.checkbox("IVA (19%)",value=True)
    danio_pct=st.slider("% de daño a simular",1,100,50)
    datos_ok=bool(zona and pisos and anio)

    # ── Modo ──
    st.subheader("¿Qué desea calcular?")
    modo=st.radio("Seleccione el alcance:",[
        "🏠  Inmueble completo — casas, locales o edificio en bloque",
        "🏛️  Solo bienes y espacios comunes — póliza de la comunidad (Ley 21.442 art. 43)",
        "🏢  Comunidad completa — bienes comunes + unidades privadas (NCG 556 CMF)",
    ])
    modo_key="simple" if "completo" in modo else ("comunes" if "Solo bienes" in modo else "comunidad")
    st.divider()

    # ══════════════════
    # MODO 1: SIMPLE
    # ══════════════════
    if modo_key=="simple":
        st.markdown("#### Datos del inmueble")
        if not datos_ok: st.info("Complete primero zona, pisos y año."); d=None
        else: d=ui_comp("s",zona,pisos,anio,aplica_iva,default_tipo="Edificio")
        if st.button("Calcular",type="primary",use_container_width=True,key="btn_s"):
            errs=[] if datos_ok else ["Complete zona, pisos y año."]
            if d: errs+=validar_comp(d,"el inmueble")
            for e in errs: st.error(f"⚠️ {e}")
            if not errs:
                res=calcular_vr(d["vub"],d["sup"],zona,pisos,anio,aplica_iva)
                ui_show("Inmueble completo",res,{**d,"zona":zona,"pisos":pisos,"anio":anio},danio_pct)
                caso=dict(nombre=nombre or "Sin nombre",direccion=direccion or "—",
                          zona=zona,pisos=pisos,anio=anio,danio_pct=danio_pct,modo="simple",
                          comp={**d,"res":res,"zona":zona,"pisos":pisos,"anio":anio},
                          total_vr=res["vr"],total_monto=d["monto"] or 0)
                b1,b2=st.columns(2)
                with b1:
                    if st.button("💾 Guardar",use_container_width=True,key="g_s"):
                        st.session_state.setdefault("casos",[]).append(caso); st.success("Guardado.")
                with b2:
                    st.download_button("📄 Descargar informe",data=generar_informe(caso).encode(),
                                       file_name=f"informe_{(nombre or 'inmueble').replace(' ','_').lower()}.txt",
                                       mime="text/plain",use_container_width=True,key="dl_s")

    # ══════════════════
    # MODO 2: COMUNES
    # ══════════════════
    elif modo_key=="comunes":
        st.markdown("#### Bienes y espacios comunes")
        st.info("**Ley 21.442, art. 43** — Seguro obligatorio de la comunidad. Independiente del seguro de cada unidad.")
        if not datos_ok: st.info("Complete zona, pisos y año."); d=None
        else: d=ui_comp("bc",zona,pisos,anio,aplica_iva,default_tipo="Comunidad",label_tipo="Tipo (bienes comunes)")
        if st.button("Calcular bienes comunes",type="primary",use_container_width=True,key="btn_bc"):
            errs=[] if datos_ok else ["Complete zona, pisos y año."]
            if d: errs+=validar_comp(d,"bienes comunes")
            for e in errs: st.error(f"⚠️ {e}")
            if not errs:
                res=calcular_vr(d["vub"],d["sup"],zona,pisos,anio,aplica_iva)
                ui_show("Bienes y espacios comunes",res,{**d,"zona":zona,"pisos":pisos,"anio":anio},danio_pct,
                        nota="Asegurado: la comunidad (Ley 21.442 art. 43 — OBLIGATORIO)")
                caso=dict(nombre=nombre or "Sin nombre",direccion=direccion or "—",
                          zona=zona,pisos=pisos,anio=anio,danio_pct=danio_pct,modo="comunes",
                          comp={**d,"res":res,"zona":zona,"pisos":pisos,"anio":anio},
                          total_vr=res["vr"],total_monto=d["monto"] or 0)
                b1,b2=st.columns(2)
                with b1:
                    if st.button("💾 Guardar",use_container_width=True,key="g_bc"):
                        st.session_state.setdefault("casos",[]).append(caso); st.success("Guardado.")
                with b2:
                    st.download_button("📄 Descargar informe",data=generar_informe(caso).encode(),
                                       file_name=f"informe_{(nombre or 'comunes').replace(' ','_').lower()}.txt",
                                       mime="text/plain",use_container_width=True,key="dl_bc")

    # ══════════════════
    # MODO 3: COMUNIDAD
    # ══════════════════
    else:
        st.markdown("""> **NCG 556 CMF** — La póliza colectiva se estructura en dos bloques separados:
> **Bloque 1 — Bienes comunes** (asegurado: la comunidad) · **Bloque 2 — Unidades privadas** (asegurado: cada copropietario)""")

        # ── DESGLOSE DE SUPERFICIE ──
        st.markdown("---")
        st.markdown("#### Distribución de la superficie total")
        st.markdown("""
> **Contexto normativo:**
> Según Edifito / Ley 21.442, los espacios comunes **representan entre el 50% y 70% del valor total de reconstrucción**.
> En la práctica, la superficie física de bienes comunes equivale al **30–60% de la superficie total del edificio**,
> dependiendo de sus amenidades (subterráneos, piscina, gimnasio, etc.).
> No existe un porcentaje fijo por ley — cada edificio lo define en su Reglamento de Copropiedad
> (inscrito en el Conservador de Bienes Raíces).
""")

        col_st, col_pf = st.columns(2)
        with col_st:
            sup_total_edificio = st.number_input(
                "Superficie total del edificio (m²)",
                min_value=1, max_value=2_000_000,
                value=None, placeholder="Ej: 12000",
                help=(
                    "Suma de TODOS los pisos y subterráneos. "
                    "Si no la conoce, mídala en Google Earth (ver herramienta arriba) "
                    "y multiplique por el N° de pisos + subterráneos."
                ),
                key="sup_total_edificio",
            )
        with col_pf:
            perfil_key = st.selectbox(
                "Perfil de amenidades del edificio",
                list(PERFILES_EDIFICIO.keys()),
                key="perfil_edificio",
                help="Define el porcentaje estimado de superficie de bienes comunes.",
            )

        perfil = PERFILES_EDIFICIO[perfil_key]
        st.caption(f"📋 {perfil['descripcion']} — Rango referencial: **{perfil['rango']}**")
        st.caption(f"Fuente: {perfil['fuente']}")

        # Porcentaje manual o automático
        if perfil["sup_comun_pct"] is None:
            pct_comun_input = st.slider(
                "% superficie bienes comunes (ingreso manual)",
                min_value=10, max_value=70, value=40,
                help="Obténgalo del Reglamento de Copropiedad o de una tasación profesional.",
                key="pct_comun_manual",
            )
            pct_comun = pct_comun_input / 100
        else:
            pct_comun = perfil["sup_comun_pct"]
            st.info(f"**Porcentaje aplicado: {pct_comun*100:.0f}% bienes comunes / {(1-pct_comun)*100:.0f}% unidades privadas**")

        # Mostrar desglose si hay superficie total
        sup_comun_calc = None
        sup_units_calc = None
        if sup_total_edificio:
            sup_comun_calc = round(sup_total_edificio * pct_comun)
            sup_units_calc = sup_total_edificio - sup_comun_calc
            dc1, dc2, dc3 = st.columns(3)
            dc1.metric("Superficie total", f"{sup_total_edificio:,.0f} m²")
            dc2.metric(f"Bienes comunes ({pct_comun*100:.0f}%)", f"{sup_comun_calc:,.0f} m²")
            dc3.metric(f"Unidades privadas ({(1-pct_comun)*100:.0f}%)", f"{sup_units_calc:,.0f} m²")
            st.caption(
                "⚠️ Distribución **estimada**. Para mayor precisión, use los m² reales del Reglamento "
                "de Copropiedad o de los planos de arquitectura del edificio."
            )

        # ── BLOQUE 1: BIENES COMUNES ──
        st.markdown("---")
        st.markdown("#### Bloque 1 — Bienes y espacios comunes")
        st.caption("Estructura, fachadas, instalaciones centrales, ascensores, subterráneos y toda área de dominio común.")
        if datos_ok:
            d_comun=ui_comp("c_bc",zona,pisos,anio,aplica_iva,default_tipo="Comunidad",label_tipo="Tipo (bienes comunes)")
            # Pre-rellenar superficie si se calculó
            if sup_comun_calc and not d_comun.get("sup"):
                st.info(f"💡 Superficie estimada de bienes comunes: **{sup_comun_calc:,.0f} m²** — puede editarla arriba.")
                d_comun["sup"] = d_comun["sup"] or sup_comun_calc
        else:
            st.info("Complete zona, pisos y año."); d_comun=None

        # ── BLOQUE 2: UNIDADES ──
        st.markdown("---")
        st.markdown("#### Bloque 2 — Unidades privadas")
        st.caption("VUB con tipo **Depto** — corresponde al valor habitable de cada unidad, sin incluir áreas comunes.")

        incluir_uni=st.checkbox("Incluir unidades privadas en este análisis",value=True,
                                help="Desmarque si las unidades tienen seguros individuales separados.")
        datos_uni=[]
        if incluir_uni and datos_ok:
            if "n_uni" not in st.session_state: st.session_state.n_uni=1
            ca,cr=st.columns(2)
            with ca:
                if st.button("➕ Agregar unidad",use_container_width=True): st.session_state.n_uni+=1
            with cr:
                if st.button("➖ Quitar última",use_container_width=True,
                             disabled=st.session_state.n_uni<=1): st.session_state.n_uni-=1

            # Si hay superficie de unidades estimada, dividir por número de unidades
            if sup_units_calc and st.session_state.n_uni>0:
                sup_uni_sugerida=round(sup_units_calc/st.session_state.n_uni)
                st.caption(f"💡 Superficie promedio sugerida por unidad: **{sup_uni_sugerida:,.0f} m²** "
                           f"({sup_units_calc:,.0f} m² ÷ {st.session_state.n_uni} unidades)")
            else:
                sup_uni_sugerida=None

            for i in range(st.session_state.n_uni):
                with st.expander(f"Unidad privada {i+1}",expanded=(i==0)):
                    nom_u=st.text_input("Identificación",key=f"u_{i}_nom",
                                        placeholder="Ej: Depto 501, Local 2")
                    du=ui_comp(f"u_{i}",zona,pisos,anio,aplica_iva,
                               default_tipo="Depto",label_tipo="Tipo de unidad")
                    du["nombre"]=nom_u
                    du["poliza_propia"]=st.checkbox(
                        "Tiene póliza propia vigente (hipotecaria u otra)",key=f"u_{i}_prop",
                        help="Puede renunciar a cobertura en póliza colectiva (art. 43 b), pero igual contribuye a bienes comunes.")
                    datos_uni.append(du)
        elif incluir_uni and not datos_ok:
            st.info("Complete los datos generales para habilitar las unidades.")

        st.divider()
        if st.button("Calcular comunidad completa",type="primary",use_container_width=True,key="btn_com"):
            errs=[] if datos_ok else ["Complete zona, pisos y año."]
            if d_comun: errs+=validar_comp(d_comun,"bienes comunes")
            else: errs+=["Complete datos de bienes comunes."]
            if incluir_uni:
                for i,du in enumerate(datos_uni,1): errs+=validar_comp(du,f"unidad {i}")
            for e in errs: st.error(f"⚠️ {e}")

            if not errs:
                res_c=calcular_vr(d_comun["vub"],d_comun["sup"],zona,pisos,anio,aplica_iva)
                comp_c={**d_comun,"res":res_c,"zona":zona,"pisos":pisos,"anio":anio}
                units_calc=[]
                for du in datos_uni:
                    r_u=calcular_vr(du["vub"],du["sup"],zona,pisos,anio,aplica_iva)
                    units_calc.append({**du,"res":r_u,"zona":zona,"pisos":pisos,"anio":anio})

                vr_c=res_c["vr"]; vr_u=sum(u["res"]["vr"] for u in units_calc)
                vr_t=vr_c+vr_u
                m_c=d_comun["monto"] or 0; m_u=sum(u.get("monto") or 0 for u in datos_uni); m_t=m_c+m_u
                r_t,i_t=evaluar(m_t,vr_t); d_t=vr_t*(danio_pct/100); ind_t=indemn(d_t,m_t,vr_t)

                st.divider(); st.subheader("Resultados")
                st.markdown("##### Resumen consolidado")
                if m_t<=0: st.info("ℹ️ Sin monto asegurado. El valor calculado indica cuánto debería asegurarse.")
                elif i_t: st.warning(f"⚠️ **Infraseguro global.** Cobertura: **{r_t*100:.1f}%** — Brecha: **{vr_t-m_t:,.2f} UF**")
                else: st.success(f"✅ Cobertura global adecuada ({r_t*100:.1f}%)")

                t1,t2,t3,t4=st.columns(4)
                t1.metric("VR total comunidad",f"{vr_t:,.2f} UF")
                t2.metric("Bienes comunes",f"{vr_c:,.2f} UF")
                t3.metric("Unidades privadas",f"{vr_u:,.2f} UF")
                t4.metric("Cobertura global",f"{r_t*100:.1f}%" if m_t>0 else "—",
                          delta=f"{(r_t-1)*100:.1f}%" if m_t>0 else None,
                          delta_color="normal" if not i_t else "inverse")
                if m_t>0: st.progress(min(r_t,1.0),text=f"Cobertura global: {r_t*100:.1f}%")

                # Mostrar distribución superficies si aplica
                if sup_total_edificio:
                    st.markdown("##### Distribución de superficies aplicada")
                    p1,p2,p3=st.columns(3)
                    p1.metric("Superficie total",f"{sup_total_edificio:,.0f} m²")
                    p2.metric(f"Bienes comunes ({pct_comun*100:.0f}%)",f"{sup_comun_calc:,.0f} m²")
                    p3.metric(f"Unidades ({(1-pct_comun)*100:.0f}%)",f"{sup_units_calc:,.0f} m²")
                    st.caption(f"Perfil aplicado: {perfil_key} · Fuente: {perfil['fuente']}")

                with st.expander(f"🔥 Simulación total — daño {danio_pct}%"):
                    sc1,sc2,sc3=st.columns(3)
                    sc1.metric("Daño total",f"{d_t:,.2f} UF")
                    sc2.metric("Indemnización global",f"{ind_t:,.2f} UF" if m_t>0 else "—")
                    if i_t and m_t>0:
                        sc3.metric("Pérdida no cubierta",f"{d_t-ind_t:,.2f} UF",delta_color="inverse")

                # Tabla comparativa
                st.markdown("---"); st.markdown("##### Tabla comparativa")
                filas=[]
                r_c2,i_c2=evaluar(m_c,vr_c)
                filas.append({"Componente":"Bienes comunes","Asegurado":"Comunidad",
                              "Sup. m²":f"{d_comun['sup']:,.0f}","VUB":f"{d_comun['vub']:.1f}",
                              "VR (UF)":f"{vr_c:,.2f}",
                              "Asegurado (UF)":f"{m_c:,.2f}" if m_c>0 else "—",
                              "Cobertura":f"{r_c2*100:.1f}%" if m_c>0 else "—",
                              "Estado":"⚠️" if i_c2 else ("✅" if m_c>0 else "ℹ️")})
                for u in units_calc:
                    vr_u2=u["res"]["vr"]; m_u2=u.get("monto") or 0
                    r_u2,i_u2=evaluar(m_u2,vr_u2)
                    pp=" (póliza propia)" if u.get("poliza_propia") else ""
                    filas.append({"Componente":u.get("nombre") or "Unidad","Asegurado":f"Copropietario{pp}",
                                  "Sup. m²":f"{u['sup']:,.0f}","VUB":f"{u['vub']:.1f}",
                                  "VR (UF)":f"{vr_u2:,.2f}",
                                  "Asegurado (UF)":f"{m_u2:,.2f}" if m_u2>0 else "—",
                                  "Cobertura":f"{r_u2*100:.1f}%" if m_u2>0 else "—",
                                  "Estado":"⚠️" if i_u2 else ("✅" if m_u2>0 else "ℹ️")})
                filas.append({"Componente":"TOTAL","Asegurado":"—",
                              "Sup. m²":f"{(d_comun['sup'] or 0)+sum(u.get('sup') or 0 for u in datos_uni):,.0f}",
                              "VUB":"—","VR (UF)":f"{vr_t:,.2f}",
                              "Asegurado (UF)":f"{m_t:,.2f}" if m_t>0 else "—",
                              "Cobertura":f"{r_t*100:.1f}%" if m_t>0 else "—",
                              "Estado":"⚠️" if i_t else ("✅" if m_t>0 else "ℹ️")})
                st.dataframe(pd.DataFrame(filas),use_container_width=True,hide_index=True)

                st.markdown("---"); st.markdown("##### Detalle por componente")
                ui_show("Bienes y espacios comunes",res_c,comp_c,danio_pct,
                        nota="Asegurado: la comunidad (Ley 21.442 art. 43 — OBLIGATORIO)",expanded=True)
                for i,u in enumerate(units_calc,1):
                    lbl=u.get("nombre") or f"Unidad {i}"
                    nota_u=("Póliza propia — puede renunciar a cobertura colectiva"
                            if u.get("poliza_propia") else "Asegurado: copropietario (NCG 556 Bloque 2)")
                    ui_show(lbl,u["res"],u,danio_pct,nota=nota_u,expanded=(i==1))

                caso=dict(nombre=nombre or "Sin nombre",direccion=direccion or "—",
                          zona=zona,pisos=pisos,anio=anio,danio_pct=danio_pct,modo="comunidad",
                          comp_comun=comp_c,
                          unidades=[{**u,"nombre":u.get("nombre") or f"Unidad {j+1}"} for j,u in enumerate(units_calc)],
                          vr_comun=vr_c,vr_units=vr_u,total_vr=vr_t,total_monto=m_t,
                          desglose={"sup_total":sup_total_edificio,"perfil":perfil_key,
                                    "pct_comun":pct_comun,"sup_comun":sup_comun_calc,
                                    "sup_units":sup_units_calc,"fuente":perfil["fuente"]} if sup_total_edificio else None)
                b1,b2=st.columns(2)
                with b1:
                    if st.button("💾 Guardar",use_container_width=True,key="g_com"):
                        st.session_state.setdefault("casos",[]).append(caso); st.success("Guardado.")
                with b2:
                    st.download_button("📄 Descargar informe",data=generar_informe(caso).encode(),
                                       file_name=f"informe_{(nombre or 'comunidad').replace(' ','_').lower()}.txt",
                                       mime="text/plain",use_container_width=True,key="dl_com")

# ══════════════════════════════════════════════════════════
# PESTAÑA: MIS CASOS
# ══════════════════════════════════════════════════════════
with tab_casos:
    casos=st.session_state.get("casos",[])
    if not casos: st.info("Aún no tiene casos guardados.")
    else:
        st.caption(f"{len(casos)} caso{'s' if len(casos)>1 else ''} guardado{'s' if len(casos)>1 else ''}")
        for i,c in enumerate(casos):
            vr_c=c["total_vr"]; m_c=c["total_monto"]; r_c,inf_c=evaluar(m_c,vr_c)
            estado="⚠️ Infraseguro" if inf_c else ("✅ Cubierto" if m_c>0 else "ℹ️ Sin seguro")
            modos={"simple":"Completo","comunes":"Bienes comunes","comunidad":"Comunidad"}
            with st.expander(f"{estado}  |  {c['nombre']}  —  {vr_c:,.2f} UF  [{modos.get(c['modo'],'—')}]"):
                cc1,cc2,cc3=st.columns(3)
                cc1.metric("Valor de reconstrucción",f"{vr_c:,.2f} UF")
                cc2.metric("Monto asegurado",f"{m_c:,.2f} UF" if m_c>0 else "No indicado")
                cc3.metric("Cobertura",f"{r_c*100:.1f}%" if m_c>0 else "—")
                st.caption(f"{c.get('zona','—')} · {c.get('pisos','—')} pisos · año {c.get('anio','—')}")
                st.download_button("📄 Descargar informe",data=generar_informe(c).encode(),
                                   file_name=f"informe_{c['nombre'].replace(' ','_').lower()}.txt",
                                   mime="text/plain",key=f"dl_caso_{i}")
        if st.button("🗑️ Limpiar todos"): st.session_state.casos=[]; st.rerun()

# ══════════════════════════════════════════════════════════
# PESTAÑA: MARCO NORMATIVO
# ══════════════════════════════════════════════════════════
with tab_como:
    st.subheader("Distribución de superficies: bienes comunes vs unidades privadas")
    st.markdown("""
No existe en Chile una norma que fije un porcentaje único obligatorio de superficie de bienes comunes.
La distribución depende de cada edificio y queda establecida en su **Reglamento de Copropiedad**
(inscrito en el Conservador de Bienes Raíces). Sin embargo, existen referencias importantes:
""")
    st.markdown("""
| Fuente | Referencia | Aplicación |
|--------|------------|------------|
| **Edifito / Ley 21.442** | Bienes comunes = **50–70% del valor total de reconstrucción** | Valor asegurado |
| **ComunidadFeliz** | Bienes comunes = **60–80% del monto asegurado total** | Monto póliza |
| **OGUC art. 5.1.11** | Superficie común < **20% de la sup. útil** no se contabiliza para constructibilidad | Permisos edificación |
| **Práctica de mercado** | Superficie física común ≈ **30–60% de la sup. total** según amenidades | Estimación operativa |
| **Reglamento de Copropiedad** | Porcentaje exacto inscrito en el Conservador de Bienes Raíces | Valor legal vinculante |
""")
    st.info("**Para el cálculo del seguro**, lo más relevante es el valor de reconstrucción, no solo la superficie. "
            "Un edificio con piscina, subterráneos y gimnasio tiene más valor de bienes comunes aunque su superficie "
            "sea similar a uno sin amenidades.")

    st.subheader("Cómo medir la superficie del edificio")
    st.markdown("""
Si no dispone de los planos o de la información del SII, puede estimar la superficie total así:

**Método Google Earth (recomendado):**
1. Abra [Google Earth Web](https://earth.google.com) y busque la dirección del edificio
2. Use la herramienta **Medir** → seleccione **Polígono**
3. Trace el contorno exterior del edificio en planta (el área de la huella)
4. Google Earth le entregará el área en m²
5. Multiplique ese valor × (número de pisos + número de subterráneos)

**Otras fuentes:**
- Escritura de compraventa o certificado del SII (Formulario 2803-2804)
- Planos de arquitectura del edificio
- Administración del condominio (tiene acceso al expediente de obras)
- Reglamento de Copropiedad inscrito en el Conservador de Bienes Raíces
""")

    st.subheader("Marco normativo")
    with st.expander("Ley 21.442 art. 43 — Seguro obligatorio comunidad"):
        st.markdown("Todo condominio habitacional debe contratar seguro colectivo contra incendio que cubra **obligatoriamente** bienes e instalaciones comunes, y **opcionalmente** las unidades privadas. El copropietario puede renunciar a la cobertura de su unidad si tiene póliza propia vigente, **pero nunca puede eximirse del pago por bienes comunes**.")
    with st.expander("NCG 556 CMF dic. 2025 — Estructura de la póliza"):
        st.markdown("""
La póliza colectiva debe presentarse en **dos bloques separados** con montos y deducibles claramente identificados:

| Bloque | Cubre | Asegurado | Carácter |
|--------|-------|-----------|----------|
| **1 — Bienes comunes** | Estructura, instalaciones, áreas comunes | La comunidad | Obligatorio |
| **2 — Unidades privadas** | Cada depto, local, bodega | El copropietario | Opcional colectivo |

Ante daños parciales en una unidad, la indemnización se destina **primero a reparación**, no al crédito hipotecario.
""")
    with st.expander("CCom Art. 553 — Regla proporcional"):
        st.markdown("Si el monto asegurado < valor real → la compañía paga solo en proporción a la prima pagada. **Por esto es fundamental calcular y asegurar el valor correcto.**")
    with st.expander("Pasos del cálculo de VR"):
        st.markdown("""
| Paso | Concepto |
|------|----------|
| 1 | VUB (UF/m²) ingresado × sup. (m²) |
| 2 | × Factor geográfico: Metropolitana 1.05 / Intermedia 1.00 / Aislada 1.15 |
| 3 | × Factor normativo: <1985→1.15 / 1985-2000→1.10 / 2001-2010→1.05 / >2010→1.00 |
| 4 | × Factor altura: 1-2p→1.00 / 3-5p→1.05 / 6-10p→1.10 / 11+→1.15 |
| 5 | = Costo directo |
| 6 | + Indirectos 31%: diseño 3% + GG 6% + utilidad 12% + imprevistos 10% |
| 7 | + IVA 19% (si aplica) |
| ✓ | = Valor de Reconstrucción |
""")
    with st.expander("Fuentes de referencia VUB"):
        st.markdown("""
- **Tabla MINVU** (oficial, en pesos, trimestral): [minvu.gob.cl](https://www.minvu.gob.cl/elementos-tecnicos/tabla-de-costos-unitarios/)
- **Troncoso Arquitectos** — Precio m² construcción Chile 2025
- **Constructora Márquez Arranz** — Costos Gran Concepción 2025
- **Almazán Ltda.** — Costos sur de Chile 2025
- Corredores y tasadores de seguros (tablas propias por compañía)
""")
    st.divider()
    st.caption("Programa referencial. No reemplaza tasación profesional. Consulte a un corredor o tasador certificado.")
