import streamlit as st
import re, os
import pandas as pd
import math
import plotly.graph_objects as go

st.set_page_config(page_title="Darwish CNC Pro 37.7", layout="wide")

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

def convert_logic(mpr_text, tool_df, rotate_90, zero_nesting, margin, global_z_off):
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
            raw_drills.append({
                'x': xa + i*ab*math.cos(math.radians(wi)), 'y': ya + i*ab*math.sin(math.radians(wi)),
                'z': f_z, 't': conf['T_CNC'], 'desc': conf['תיאור'], 'dia': du, 'color': conf['צבע'], 'group': m.start()
            })

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

    nc = [f"G90 G54"]
    # (לוגיקה של ייצור NC נשמרת...)
    return "\n".join(nc), raw_drills, geos, thickness

def plot_master_3d(drills, geos, thickness, top_view, m1, m2):
    fig = go.Figure()
    
    # 1. שולחן מכונה
    fig.add_trace(go.Mesh3d(
        x=[0, 0, 2000, 2000, 0, 0, 2000, 2000], y=[0, 1500, 1500, 0, 0, 1500, 1500, 0],
        z=[-1, -1, -1, -1, 0, 0, 0, 0],
        opacity=0.03, color='gray', hoverinfo='skip'
    ))

    # 2. קידוחים
    for i, d in enumerate(drills):
        actual_depth = thickness - d['z']
        fig.add_trace(go.Scatter3d(
            x=[d['x'], d['x']], y=[d['y'], d['y']], z=[thickness, d['z']],
            mode='lines+markers',
            marker=dict(size=[d['dia']*1.5, 0], color=d['color']),
            line=dict(color=d['color'], width=7),
            name=f"#{i}: {d['desc']}",
            hovertemplate=(
                f"<b>{d['desc']}</b><br>"
                f"מספר כלי: {d['t']}<br>"
                f"עומק חדירה (בפועל): {actual_depth:.2f} ממ<br>"
                f"X: %{{x:.2f}} | Y: %{{y:.2f}}<extra></extra>"
            )
        ))

    # 3. מדידה בין נקודות שנבחרו בסידבר
    if m1 < len(drills) and m2 < len(drills):
        p1, p2 = drills[m1], drills[m2]
        dist = math.sqrt((p1['x']-p2['x'])**2 + (p1['y']-p2['y'])**2)
        fig.add_trace(go.Scatter3d(
            x=[p1['x'], p2['x']], y=[p1['y'], p2['y']], z=[thickness+5, thickness+5],
            mode='lines+text', line=dict(color='lime', width=12),
            text=["", f"📏 {dist:.2f} ממ"], textposition="top center"
        ))

    camera = dict(eye=dict(x=0, y=0, z=2.5), up=dict(x=0, y=1, z=0)) if top_view else dict(eye=dict(x=1.2, y=1.2, z=1.2))
    fig.update_layout(scene=dict(camera=camera, aspectmode='data', 
                                 xaxis=dict(range=[0, 2000]), yaxis=dict(range=[0, 1500])),
                      margin=dict(l=0, r=0, b=0, t=0), height=850)
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

# UI
st.sidebar.title("🛠️ CNC 37.7")
v_2d = st.sidebar.toggle("מבט על (2D)", value=False)
st.sidebar.markdown("---")
n_v = st.sidebar.checkbox("צמד לפינה", value=True)
r_v = st.sidebar.checkbox("Portrait", value=True)
m_v = st.sidebar.number_input("Margin", value=7.0)

st.sidebar.markdown("---")
st.sidebar.header("📏 מדידה")
drill_1 = st.sidebar.number_input("מקדח ראשון (#)", value=0, min_value=0)
drill_2 = st.sidebar.number_input("מקדח שני (#)", value=1, min_value=0)

uploaded = st.file_uploader("טען MPR", accept_multiple_files=True)
if uploaded:
    for f in uploaded:
        nc, drills, geos, thick = convert_logic(f.getvalue().decode('utf-8', errors='ignore'), pd.DataFrame(DEFAULT_TOOLS), r_v, n_v, m_v, 2.0)
        plot_master_3d(drills, geos, thick, v_2d, drill_1, drill_2)
