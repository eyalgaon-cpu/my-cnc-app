import streamlit as st
import re, os
import pandas as pd
import math
import plotly.graph_objects as go

# הגדרות דף
st.set_page_config(page_title="Darwish CNC Pro 41.4", layout="wide")

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
        
        # מיפוי לכלי המכונה
        target_t = tool_map.get(t_mpr)
        conf = next((t for t in tools_list if t['T_CNC'] == target_t), None)
        
        if conf:
            # לוגיקה: שלילי מעמיק, חיובי מרים
            f_z = (thickness - ti) + global_z_off - conf.get("תיקון_Z", 0.0)
            raw_drills.append({
                'x': xa, 'y': ya, 'z': f_z, 't': conf['T_CNC'], 
                'desc': conf['תיאור'], 'dia': conf['קוטר'], 
                'color': conf['צבע'], 'mpr_id': t_mpr
            })

    # לוגיקת פסיעות: פסיעה 1 משאירה 0.3. פסיעה 2 יורדת 0.2 מתחת לפלטה
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
        mx_part, my_part = min(all_x), min(all_y)
        for d in raw_drills: d['x'] -= mx_part; d['y'] -= my_part
        for pts in geos.values():
            for p in pts: p[0] -= mx_part; p[1] -= my_part

    for d in raw_drills: d['x'] += margin_x; d['y'] += margin_y
    for pts in geos.values():
        for p in pts: p[0] += margin_x; p[1] += margin_y

    nc = [f"G90 G54"]
    for d in raw_drills:
        nc.append(f"T{d['t']} M06 (MPR: {d['mpr_id']})")
        nc.append(f"G00 X{d['x']:.3f} Y{d['y']:.3f}")
        nc.append(f"G01 Z{d['z']:.3f} F2000")
        nc.append(f"G00 Z{thickness+10:.3f}")
    
    # החזרת 7 ערכים בדיוק כדי למנוע ValueError
    return "\n".join(nc), raw_drills, geos, thickness, dx, dy, contour_info

def plot_2d_pro(drills, geos, thickness, dx, dy, c_info, filename):
    st.markdown(f"### <div dir='rtl' style='text-align:right;'>קובץ: {filename}</div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.info(f"📏 מידות חלק: {dx:.2f} × {dy:.2f} מילימטר | עובי: {thickness:.2f} מילימטר")
    c2.warning(f"🪚 קונטור: {c_info['tool']} | פסיעות: {' ← '.join(c_info['passes'])}")
    
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=1300, y1=3050, fillcolor="whitesmoke", line=dict(color="black", width=2), layer="below")
    
    for bid, pts in geos.items():
        if len(pts) > 1:
            x_p, y_p = zip(*pts)
            fig.add_trace(go.Scatter(x=x_p, y=y_p, mode='lines', line=dict(color='red', width=2), name=f"קונטור {bid}"))

    for d in drills:
        fig.add_trace(go.Scatter(
            x=[d['x']], y=[d['y']], mode='markers',
            marker=dict(size=d['dia'], color=d['color'], line=dict(width=1, color='black')),
            customdata=[[d['t'], d['desc'], thickness - d['z'], d['mpr_id']]],
            hovertemplate="<b>%{customdata[0]}</b> (MPR: %{customdata[3]})<br>כלי: %{customdata[1]}<br>עומק: %{customdata[2]:.2f} מילימטר<extra></extra>"
        ))

    fig.update_xaxes(title="<span dir='rtl'>ציר X (מילימטר)</span>", showline=True, mirror=True)
    fig.update_yaxes(title="<span dir='rtl'>ציר Y (מילימטר)</span>", scaleanchor="x", scaleratio=1, showline=True, mirror=True)
    fig.update_layout(width=900, height=850, template="plotly_white", showlegend=False)
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

# Sidebar
st.sidebar.title("🛠️ ממשק דרוויש 41.4")
sel_m = st.sidebar.selectbox("בחר מכונה:", list(st.session_state.profiles.keys()))
cfg = st.session_state.profiles[sel_m]

with st.sidebar.expander("🔗 מפת כלים (MPR ➔ מכונה)", expanded=True):
    mpr_list = ["142", "15.0000", "10.0000", "8.0000", "5.0000"]
    t_map = {}
    for t_id in mpr_list:
        # ברירת מחדל חכמה: 15.0000 הולך ל-T44 (קבינאו)
        d_idx = 0
        if t_id == "15.0000": d_idx = 4
        elif t_id == "10.0000": d_idx = 2
        elif t_id == "8.0000": d_idx = 1
        
        t_map[t_id] = st.selectbox(f"כלי MPR {t_id}:", [t['T_CNC'] for t in cfg['tools']], index=d_idx, key=f"v414_{t_id}")

st.sidebar.markdown("---")
nest, rot = st.sidebar.checkbox("Nesting", value=True), st.sidebar.checkbox("Portrait 90°", value=True)
gz_off = st.sidebar.slider("כיול Z גלובלי (מילימטר)", -5.0, 5.0, 0.0, 0.1)
mx, my = st.sidebar.number_input("מרג'ין X", value=0.0), st.sidebar.number_input("מרג'ין Y", value=0.0)

uploaded = st.file_uploader("טען קבצי MPR", accept_multiple_files=True)
if uploaded:
    for f in uploaded:
        mpr_c = f.getvalue().decode('utf-8', errors='ignore')
        # כאן מתוקן ה-Unpacking: מקבלים 7 ערכים
        nc, drls, geos, thick, dx, dy, c_inf = convert_logic(mpr_c, cfg, rot, nest, mx, my, gz_off, t_map)
        plot_2d_pro(drls, geos, thick, dx, dy, c_inf, f.name)
        st.download_button(f"📂 הורד NC עבור {f.name}", nc, f.name.replace(".mpr", ".nc"))
