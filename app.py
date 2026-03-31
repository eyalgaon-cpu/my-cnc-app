import streamlit as st
import re, os
import pandas as pd
import math
import plotly.graph_objects as go

# הגדרות דף
st.set_page_config(page_title="Darwish CNC Pro 41.2", layout="wide")

# ניהול פרופילים הכולל כיולים ומרג'ין
if 'profiles' not in st.session_state:
    st.session_state.profiles = {
        "אבי": {
            "tools": [
                {"T_CNC": "T2", "קוטר": 6.0, "תיאור": "כרסום 6", "צבע": "red", "תיקון_Z": 0.0},
                {"T_CNC": "T47", "קוטר": 8.0, "תיאור": "מקדח 8", "צבע": "green", "תיקון_Z": -1.0},
                {"T_CNC": "T46", "קוטר": 10.0, "תיאור": "מקדח 10", "צבע": "blue", "תיקון_Z": -0.5},
                {"T_CNC": "T6", "קוטר": 35.0, "תיאור": "מקדח 35", "צבע": "orange", "תיקון_Z": -0.1},
                {"T_CNC": "T44", "קוטר": 5.0, "תיאור": "קבינאו 5", "צבע": "yellow", "תיקון_Z": 0.0}
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
    
    # שליפת כל הכלים מה-MPR (102, 105, 130)
    detected_mpr_tools = []
    for m in re.finditer(r'<(102|105|130)(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        content = m.group(2)
        t_id = re.search(r'(DU|TNO|T_CNC)="([^"]*)"', content)
        if t_id: detected_mpr_tools.append(t_id.group(2))
    unique_mpr = sorted(list(set(detected_mpr_tools)))

    raw_drills = []
    # סריקת קדחים (כולל קבינאו 5.0)
    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1)
        xa, ya, ti = [get_safe_float(k, b) for k in ['XA', 'YA', 'TI']]
        t_mpr = re.search(r'DU="([^"]*)"', b).group(1)
        
        # שימוש במפה או קוטר ישיר
        target_t = tool_map.get(t_mpr, t_mpr)
        conf = next((t for t in tools_list if t['T_CNC'] == target_t or str(t['קוטר']) == target_t), None)
        
        if conf:
            f_z = (thickness - ti) + global_z_off - conf.get("תיקון_Z", 0.0)
            raw_drills.append({'x': xa, 'y': ya, 'z': f_z, 't': conf['T_CNC'], 'desc': conf['תיאור'], 'dia': conf['קוטר'], 'color': conf['צבע']})

    # זיהוי כרסום קונטור (105/130) לטובת כותרת וריחוף
    contour_info = {"tool": "לא זוהה", "passes": []}
    c_match = re.search(r'<(105|130)(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL)
    if c_match:
        c_block = c_match.group(2)
        t_mpr = re.search(r'(TNO|T_CNC|DU)="([^"]*)"', c_block).group(2)
        target_t = tool_map.get(t_mpr, t_mpr)
        conf = next((t for t in tools_list if t['T_CNC'] == target_t or str(t['קוטר']) == target_t), None)
        if conf:
            contour_info["tool"] = f"{conf['תיאור']} ({conf['T_CNC']})"
            contour_info["passes"] = [f"{thickness/2:.2f} מילימטר", f"{thickness + 2.0:.2f} מילימטר"]

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

    nc = [f"G90 G54"]
    for d in raw_drills:
        nc.extend([f"T{d['t']} M06", f"G00 X{d['x']:.3f} Y{d['y']:.3f}", f"G01 Z{d['z']:.3f} F2000", f"G00 Z{thickness+10:.3f}"])
    
    return "\n".join(nc), raw_drills, geos, thickness, dx, dy, unique_mpr, contour_info

def plot_2d_pro(drills, geos, thickness, dx, dy, c_info, filename):
    st.markdown(f"### <div dir='rtl'>קובץ: {filename}</div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.info(f"📏 מידות: {dx:.2f} × {dy:.2f} מילימטר | עובי: {thickness:.2f} מילימטר")
    c2.warning(f"🪚 קונטור: {c_info['tool']} | פסיעות: {' ← '.join(c_info['passes']) if c_info['passes'] else 'לא זוהה'}")
    
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=1300, y1=3050, fillcolor="whitesmoke", line=dict(color="black", width=2), layer="below")
    
    for bid, pts in geos.items():
        if len(pts) > 1:
            x_p, y_p = zip(*pts)
            fig.add_trace(go.Scatter(x=x_p, y=y_p, mode='lines', line=dict(color='red', width=2), name=f"קונטור {bid}", 
                                     text=f"כלי: {c_info['tool']}", hoverinfo="text+name"))

    for d in drills:
        fig.add_trace(go.Scatter(x=[d['x']], y=[d['y']], mode='markers', marker=dict(size=d['dia'], color=d['color'], line=dict(width=1, color='black')),
                                 text=[d['desc']], customdata=[[d['t'], thickness - d['z']]],
                                 hovertemplate="<b>%{customdata[0]}</b><br>כלי: %{text}<br>עומק: %{customdata[1]:.2f} מילימטר<extra></extra>"))

    fig.update_xaxes(title="ציר X (מילימטר)", showline=True, mirror=True, side="bottom")
    fig.update_yaxes(title="ציר Y (מילימטר)", scaleanchor="x", scaleratio=1, showline=True, mirror=True)
    fig.update_layout(width=900, height=850, template="plotly_white", showlegend=False, hoverlabel=dict(bgcolor="white", font_color="black"))
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

# Sidebar
st.sidebar.title("🛠️ ממשק דרוויש 41.2")
m_names = list(st.session_state.profiles.keys())
sel_m = st.sidebar.selectbox("בחר מכונה:", m_names, index=m_names.index(st.session_state.current_machine))
st.session_state.current_machine = sel_m
cfg = st.session_state.profiles[sel_m]

st.sidebar.markdown("---")
nest, rot = st.sidebar.checkbox("Nesting", value=True), st.sidebar.checkbox("Portrait 90°", value=True)
gz_off = st.sidebar.slider("כיול Z (מילימטר)", -5.0, 5.0, cfg['z_off'], 0.1)
mx = st.sidebar.number_input("מרג'ין X", value=cfg['mx'])
my = st.sidebar.number_input("מרג'ין Y", value=cfg['my'])

if st.sidebar.button("שמור הגדרות למכונה זו"):
    st.session_state.profiles[sel_m].update({"z_off": gz_off, "mx": mx, "my": my})
    st.sidebar.success("נשמר.")

# מפת כלים ידנית
st.markdown(f"### 🧰 ניהול מכונה: {sel_m}")
uploaded = st.file_uploader("טען קבצי MPR", accept_multiple_files=True)

if uploaded:
    for f in uploaded:
        mpr_c = f.getvalue().decode('utf-8', errors='ignore')
        # שליפת כלים לטובת מיפוי
        detected = sorted(list(set(re.findall(r'(?:DU|TNO|T_CNC)="([^"]*)"', mpr_c))))
        
        st.write("🔗 **מפת כלים (MPR ➔ מכונה):**")
        cols = st.columns(len(detected))
        t_map = {}
        for i, t_id in enumerate(detected):
            t_map[t_id] = cols[i].selectbox(f"כלי {t_id}:", [t['T_CNC'] for t in cfg['tools']], key=f"{f.name}_{t_id}")
        
        nc, drls, geos, thick, dx, dy, _, c_inf = convert_logic(mpr_c, cfg, rot, nest, mx, my, gz_off, t_map)
        plot_2d_pro(drls, geos, thick, dx, dy, c_inf, f.name)
        st.download_button(f"📂 הורד NC עבור {f.name}", nc, f.name.replace(".mpr", ".nc"))
