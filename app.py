import streamlit as st
import re, os
import pandas as pd
import math
import plotly.graph_objects as go

# הגדרות דף
st.set_page_config(page_title="Darwish CNC Pro 41.3", layout="wide")

# ניהול פרופילים
if 'profiles' not in st.session_state:
    st.session_state.profiles = {
        "אבי": {
            "tools": [
                {"T_CNC": "T2", "קוטר": 6.0, "תיאור": "כרסום 6", "צבע": "red", "תיקון_Z": 0.0},
                {"T_CNC": "T47", "קוטר": 8.0, "תיאור": "מקדח 8", "צבע": "green", "תיקון_Z": -1.0},
                {"T_CNC": "T46", "קוטר": 10.0, "תיאור": "מקדח 10", "צבע": "blue", "תיקון_Z": -0.5},
                {"T_CNC": "T6", "קוטר": 35.0, "תיאור": "מקדח 35", "צבע": "orange", "תיקון_Z": -0.1},
                {"T_CNC": "T44", "קוטר": 15.0, "תיאור": "קבינאו 15", "צבע": "yellow", "תיקון_Z": 0.0},
                {"T_CNC": "T101", "קוטר": 5.0, "תיאור": "מקדח 5", "צבע": "gray", "תיקון_Z": 0.0}
            ],
            "z_off": 0.0, "mx": 0.0, "my": 0.0
        },
        "מושיקו": {
            "tools": [{"T_CNC": "T10", "קוטר": 12.0, "תיאור": "כרסום 12", "צבע": "purple", "תיקון_Z": 0.0}],
            "z_off": 0.0, "mx": 0.0, "my": 0.0
        }
    }

if 'current_machine' not in st.session_state:
    st.session_state.current_machine = "אבי"

def get_safe_float(key, block, default=0.0):
    match = re.search(f'{key}="([^"]*)"', block)
    if not match: return default
    try: return float(match.group(1))
    except:
        nums = re.findall(r'[\d.-]+', match.group(1))
        return float(nums[0]) if nums else default

def convert_logic(mpr_text, machine_config, rotate_90, zero_nesting, margin_x, margin_y, global_z_off, tool_map):
    thickness = get_safe_float('t', mpr_text, 19.0)
    tools_list = machine_config['tools']
    
    raw_drills = []
    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1)
        xa, ya, ti = [get_safe_float(k, b) for k in ['XA', 'YA', 'TI']]
        t_mpr = re.search(r'DU="([^"]*)"', b).group(1)
        
        target_t = tool_map.get(t_mpr)
        conf = next((t for t in tools_list if t['T_CNC'] == target_t), None)
        
        if conf:
            f_z = (thickness - ti) + global_z_off - conf.get("תיקון_Z", 0.0)
            raw_drills.append({
                'x': xa, 'y': ya, 'z': f_z, 't': conf['T_CNC'], 
                'desc': conf['תיאור'], 'dia': conf['קוטר'], 
                'color': conf['צבע'], 'mpr_id': t_mpr
            })

    # לוגיקת פסיעות לפי הנחיית אייל (0.3 בשר ומינוס 0.2)
    contour_info = {"tool": "לא זוהה", "passes": [f"{thickness - 0.3:.2f} מילימטר", f"{thickness + 0.2:.2f} מילימטר"]}
    c_match = re.search(r'<(105|130)(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL)
    if c_match:
        t_mpr = re.search(r'(TNO|T_CNC|DU)="([^"]*)"', c_match.group(2)).group(2)
        target_t = tool_map.get(t_mpr)
        conf = next((t for t in tools_list if t['T_CNC'] == target_t), None)
        if conf: contour_info["tool"] = f"{conf['תיאור']} ({conf['T_CNC']})"

    geos = {}
    parts = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(parts), 2):
        pts = []
        for elem in re.split(r'\$E\d+', parts[i+1]):
            x_m, y_m = re.search(r'X=([\d.-]+)', elem), re.search(r'Y=([\d.-]+)', elem)
            if x_m and y_m: pts.append([float(x_m.group(1)), float(y_m.group(1))])
        if pts: geos[parts[i]] = pts

    if rotate_90:
        for d in raw_drills: d['x'], d['y'] = -d['y'], d['x']
        for pts in geos.values():
            for p in pts: p[0], p[1] = -p[1], p[0]

    all_x = [d['x'] for d in raw_drills] + [p[0] for pts in geos.values() for p in pts]
    all_y = [d['y'] for d in raw_drills] + [p[1] for pts in geos.values() for p in pts]
    dx, dy = (max(all_x)-min(all_x), max(all_y)-min(all_y)) if all_x else (0,0)

    if zero_nesting and all_x:
        min_x, min_y = min(all_x), min(all_y)
        for d in raw_drills: d['x'] -= min_x; d['y'] -= min_y
        for pts in geos.values():
            for p in pts: p[0] -= min_x; p[1] -= min_y

    for d in raw_drills: d['x'] += margin_x; d['y'] += margin_y
    for pts in geos.values():
        for p in pts: p[0] += margin_x; p[1] += margin_y

    return raw_drills, geos, thickness, dx, dy, contour_info

def plot_2d_pro(drills, geos, thickness, dx, dy, c_info, filename):
    st.markdown(f"### <div dir='rtl' style='text-align:right;'>קובץ: {filename}</div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.info(f"📏 מידות: {dx:.2f} × {dy:.2f} מילימטר | עובי: {thickness:.2f} מילימטר")
    c2.warning(f"🪚 קונטור: {c_info['tool']} | פסיעות: {' ← '.join(c_info['passes'])}")
    
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=1300, y1=3050, fillcolor="whitesmoke", line=dict(color="black", width=2), layer="below")
    
    for bid, pts in geos.items():
        if len(pts) > 1:
            x_p, y_p = zip(*pts)
            fig.add_trace(go.Scatter(x=x_p, y=y_p, mode='lines', line=dict(color='red', width=2), name=f"קונטור {bid}", hoverinfo="name"))

    for d in drills:
        fig.add_trace(go.Scatter(
            x=[d['x']], y=[d['y']], mode='markers',
            marker=dict(size=d['dia'], color=d['color'], line=dict(width=1, color='black')),
            name=f"MPR: {d['mpr_id']}",
            customdata=[[d['t'], d['desc'], thickness - d['z']]],
            hovertemplate="<b>%{customdata[0]}</b><br>כלי: %{customdata[1]}<br>עומק: %{customdata[2]:.2f} מילימטר<extra></extra>"
        ))

    fig.update_xaxes(title="<span dir='rtl'>ציר X (מילימטר)</span>", showline=True, mirror=True)
    fig.update_yaxes(title="<span dir='rtl'>ציר Y (מילימטר)</span>", scaleanchor="x", scaleratio=1, showline=True, mirror=True)
    fig.update_layout(width=900, height=850, template="plotly_white", showlegend=False)
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

# Sidebar
st.sidebar.title("🛠️ ממשק דרוויש 41.3")
m_names = list(st.session_state.profiles.keys())
sel_m = st.sidebar.selectbox("בחר מכונה:", m_names, index=m_names.index(st.session_state.current_machine))
st.session_state.current_machine = sel_m
cfg = st.session_state.profiles[sel_m]

with st.sidebar.expander("🔗 מפת כלים (MPR ➔ מכונה)"):
    mpr_tools = ["142", "15.0000", "10.0000", "8.0000", "5.0000"] # רשימה סטטית לטסט
    t_map = {}
    for t_id in mpr_tools:
        # לוגיקת ברירת מחדל חכמה: אם MPR=15, בחר T44 (קבינאו)
        default_idx = 0
        if t_id == "15.0000": default_idx = 4
        elif t_id == "142": default_idx = 0
        
        t_map[t_id] = st.selectbox(f"כלי MPR {t_id}:", [t['T_CNC'] for t in cfg['tools']], index=default_idx, key=f"map_{t_id}")

st.sidebar.markdown("---")
nest, rot = st.sidebar.checkbox("Nesting", value=True), st.sidebar.checkbox("Portrait 90°", value=True)
gz_off = st.sidebar.slider("כיול Z (מילימטר)", -5.0, 5.0, cfg['z_off'], 0.1)
mx, my = st.sidebar.number_input("מרג'ין X", value=cfg['mx']), st.sidebar.number_input("מרג'ין Y", value=cfg['my'])

uploaded = st.file_uploader("טען קבצי MPR", accept_multiple_files=True)
if uploaded:
    for f in uploaded:
        mpr_c = f.getvalue().decode('utf-8', errors='ignore')
        _, drls, geos, thick, dx, dy, c_inf = convert_logic(mpr_c, cfg, rot, nest, mx, my, gz_off, t_map)
        plot_2d_pro(drls, geos, thick, dx, dy, c_inf, f.name)
