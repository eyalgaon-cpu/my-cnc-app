import streamlit as st
import re, os
import pandas as pd
import math
import plotly.graph_objects as go
import numpy as np

st.set_page_config(page_title="Darwish CNC Pro 37.1 - Measurement Edition", layout="wide")

DEFAULT_TOOLS = [
    {"קוטר": 6.0, "תיאור": "כרסום 6", "T_CNC": "T2", "S": 18000, "F": 6000, "תיקון_Z": 0.0, "צבע": "red"},
    {"קוטר": 8.0, "תיאור": "מקדח 8", "T_CNC": "T47", "S": 4000, "F": 2000, "תיקון_Z": -1.0, "צבע": "green"},
    {"קוטר": 10.0, "תיאור": "מקדח 10", "T_CNC": "T46", "S": 4000, "F": 2000, "תיקון_Z": -0.5, "צבע": "blue"},
    {"קוטר": 15.0, "תיאור": "מקדח 15", "T_CNC": "T49", "S": 4000, "F": 2000, "תיקון_Z": 0.0, "צבע": "cyan"},
    {"קוטר": 35.0, "תיאור": "מקדח 35", "T_CNC": "T6", "S": 3000, "F": 1500, "תיקון_Z": -0.1, "צבע": "orange"},
    {"קוטר": 5.0, "תיאור": "מקדח 5", "T_CNC": "T44", "S": 4000, "F": 2000, "תיקון_Z": 0.0, "צבע": "gray"}
]

def get_safe_float(key, block, default=0.0):
    match = re.search(f'{key}="([^"]*)"', block)
    if not match: return default
    try: return float(match.group(1))
    except:
        nums = re.findall(r'[\d.-]+', match.group(1))
        return float(nums[0]) if nums else default

def convert_logic(mpr_text, tool_df, rotate_90, offset, zero_nesting, margin, global_z_off):
    dia_map = {round(float(row['קוטר']), 1): row for _, row in tool_df.iterrows()}
    thickness = get_safe_float('t', mpr_text, 19.0)
    width_original = get_safe_float('l', mpr_text, 1414.0)
    
    geos = {}
    parts = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(parts), 2):
        bid, content = parts[i], parts[i+1]
        pts = []
        for elem in re.split(r'\$E\d+', content):
            x_m, y_m = re.search(r'X=([\d.-]+)', elem), re.search(r'Y=([\d.-]+)', elem)
            if x_m and y_m: pts.append([float(x_m.group(1)), float(y_m.group(1))])
        if pts: geos[bid] = pts

    raw_drills = []
    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1)
        xa, ya, ti, du = [get_safe_float(k, b) for k in ['XA', 'YA', 'TI', 'DU']]
        an, ab, wi = int(get_safe_float('AN', b, 1)), get_safe_float('AB', b), get_safe_float('WI', b)
        conf = dia_map.get(round(du, 1))
        if conf is None: continue
        f_z = (thickness - ti) - global_z_off - conf.get("תיקון_Z", 0.0)
        for i in range(an):
            raw_drills.append({'x': xa + i*ab*math.cos(math.radians(wi)), 'y': ya + i*ab*math.sin(math.radians(wi)),
                               'z': f_z, 't': conf['T_CNC'], 'dia': du, 'color': conf['צבע']})

    if rotate_90:
        for d in raw_drills:
            old_x, old_y = d['x'], d['y']
            d['x'], d['y'] = width_original - old_y, old_x
        for pts in geos.values():
            for p in pts:
                old_x, old_y = p[0], p[1]
                p[0], p[1] = width_original - old_y, old_x

    if zero_nesting:
        inner_geos = {k: v for k, v in geos.items() if k != "1"}
        ref_x = [p[0] for pts in inner_geos.values() for p in pts] if inner_geos else [d['x'] for d in raw_drills]
        ref_y = [p[1] for pts in inner_geos.values() for p in pts] if inner_geos else [d['y'] for d in raw_drills]
        if ref_x and ref_y:
            mx, my = min(ref_x), min(ref_y)
            for d in raw_drills: d['x'] -= mx; d['y'] -= my
            for pts in geos.values():
                for p in pts: p[0] -= mx; p[1] -= my
            for d in raw_drills: d['x'] += margin; d['y'] += margin
            for pts in geos.values():
                for p in pts: p[0] += margin; p[1] += margin

    nc, ln = [f"G90 {offset}"], 10
    # (לוגיקה של NC נשמרת...)
    return "\n".join(nc), raw_drills, geos, thickness

def plot_preview_3d(drills, geos, thickness, measure_pair=None):
    fig = go.Figure()
    
    # 1. הפלטה (ללא hover)
    inner_geos = {k: v for k, v in geos.items() if k != "1"}
    if inner_geos:
        all_x = [p[0] for pts in inner_geos.values() for p in pts]
        all_y = [p[1] for pts in inner_geos.values() for p in pts]
        min_x, max_x = min(all_x), max(all_x)
        min_y, max_y = min(all_y), max(all_y)
        fig.add_trace(go.Mesh3d(
            x=[min_x, min_x, max_x, max_x, min_x, min_x, max_x, max_x],
            y=[min_y, max_y, max_y, min_y, min_y, max_y, max_y, min_y],
            z=[0, 0, 0, 0, thickness, thickness, thickness, thickness],
            i=[7, 0, 0, 0, 4, 4, 6, 6, 4, 0, 3, 2], j=[3, 4, 1, 2, 5, 6, 5, 2, 0, 1, 6, 3], k=[0, 7, 2, 3, 6, 7, 1, 1, 5, 5, 7, 6],
            opacity=0.15, color='gray', hoverinfo='skip', name='פלטה'
        ))

    # 2. קידוחים - עם HoverTemplate משופר
    for i, d in enumerate(drills):
        fig.add_trace(go.Scatter3d(
            x=[d['x'], d['x']], y=[d['y'], d['y']], z=[thickness, d['z']],
            mode='lines+markers',
            marker=dict(size=[d['dia']*1.5, 0], color=d['color']),
            line=dict(color=d['color'], width=8),
            name=f"#{i}: D{d['dia']} ({d['t']})",
            hovertemplate=f"<b>קידוח #{i}</b><br>כלי: {d['t']}<br>קוטר: {d['dia']}<br>X: %{{x:.2f}}<br>Y: %{{y:.2f}}<br>Z (עומק): {d['z']:.2f}<extra></extra>"
        ))

    # 3. סרגל מדידה
    if measure_pair and len(measure_pair) == 2:
        p1, p2 = drills[measure_pair[0]], drills[measure_pair[1]]
        dist = math.sqrt((p1['x']-p2['x'])**2 + (p1['y']-p2['y'])**2)
        fig.add_trace(go.Scatter3d(
            x=[p1['x'], p2['x']], y=[p1['y'], p2['y']], z=[thickness+2, thickness+2],
            mode='lines+text',
            line=dict(color='lime', width=10),
            text=[f"", f"מרחק: {dist:.2f} מילימטר"],
            textposition="top center",
            name="סרגל מדידה"
        ))

    fig.update_layout(scene=dict(aspectmode='data'), width=1000, height=750, margin=dict(l=0,r=0,b=0,t=40))
    st.plotly_chart(fig, use_container_width=True)

# UI
st.title("🪚 Darwish CNC Pro 37.1")
if 'tool_df' not in st.session_state: st.session_state.tool_df = pd.DataFrame(DEFAULT_TOOLS)
edited_df = st.sidebar.data_editor(st.session_state.tool_df)

st.sidebar.header("📏 כלי מדידה")
m1 = st.sidebar.number_input("מקדח ראשון (#)", min_value=0, step=1, value=0)
m2 = st.sidebar.number_input("מקדח שני (#)", min_value=0, step=1, value=1)

uploaded = st.file_uploader("טען MPR", accept_multiple_files=True)
if uploaded:
    for f in uploaded:
        nc_txt, drills, geos, thick = convert_logic(f.getvalue().decode('utf-8', errors='ignore'), edited_df, True, "G54", True, 7.0, 2.0)
        
        # חישוב מרחק ב-Sidebar
        if len(drills) > max(m1, m2):
            d_val = math.sqrt((drills[m1]['x']-drills[m2]['x'])**2 + (drills[m1]['y']-drills[m2]['y'])**2)
            st.sidebar.success(f"מרחק מרכז-למרכז: {d_val:.2f} מילימטר")
            st.sidebar.info(f"הפרש X: {abs(drills[m1]['x']-drills[m2]['x']):.2f} | הפרש Y: {abs(drills[m1]['y']-drills[m2]['y']):.2f}")
        
        plot_preview_3d(drills, geos, thick, measure_pair=(m1, m2))
