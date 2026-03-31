import streamlit as st
import re, os
import pandas as pd
import math
import plotly.graph_objects as go

# הגדרות דף
st.set_page_config(page_title="Darwish CNC Pro 40.4", layout="wide")

# טבלת כלים
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

def convert_logic(mpr_text, tool_df, rotate_90, zero_nesting, margin_x, margin_y, global_z_off):
    dia_map = {round(float(row['קוטר']), 1): row for _, row in tool_df.iterrows()}
    thickness = get_safe_float('t', mpr_text, 19.0)
    
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
        for d in raw_drills: d['x'], d['y'] = -d['y'], d['x']
        for pts in geos.values():
            for p in pts: p[0], p[1] = -p[1], p[0]

    all_x = [d['x'] for d in raw_drills] + [p[0] for pts in geos.values() for p in pts]
    all_y = [d['y'] for d in raw_drills] + [p[1] for pts in geos.values() for p in pts]
    if all_x and all_y:
        min_x, min_y = min(all_x), min(all_y)
        if zero_nesting:
            for d in raw_drills: d['x'] -= min_x; d['y'] -= min_y
            for pts in geos.values():
                for p in pts: p[0] -= min_x; p[1] -= min_y
        else:
            shift_x = abs(min_x) if min_x < 0 else 0
            shift_y = abs(min_y) if min_y < 0 else 0
            for d in raw_drills: d['x'] += shift_x; d['y'] += shift_y
            for pts in geos.values():
                for p in pts: p[0] += shift_x; p[1] += shift_y

    for d in raw_drills:
        d['x'] += margin_x
        d['y'] += margin_y
    for pts in geos.values():
        for p in pts:
            p[0] += margin_x
            p[1] += margin_y

    nc, ln, last_t = [f"G90 G54"], 10, ""
    for t_name in sorted(list(set(d['t'] for d in raw_drills))):
        subset = sorted([dr for dr in raw_drills if dr['t']==t_name], key=lambda k: (k['group'], k['x']))
        for d in subset:
            if d['t'] != last_t:
                nc.extend([f"N{ln} {d['t']} M06", f"N{ln+5} G43 H{d['t'][1:]} S4000 M03"])
                ln, last_t = ln + 10, d['t']
            nc.extend([f"N{ln} G00 X{d['x']:.3f} Y{d['y']:.3f}", f"N{ln+5} G01 Z{d['z']:.3f} F2000", f"N{ln+10} G00 Z{thickness+10:.3f}"])
            ln += 15
    return "\n".join(nc), raw_drills, geos, thickness

def plot_2d_pro(drills, geos, thickness):
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=1300, y1=3050, fillcolor="whitesmoke", line=dict(color="black", width=2), layer="below")
    
    for bid, pts in geos.items():
        if len(pts) > 1:
            x_p, y_p = zip(*pts)
            fig.add_trace(go.Scatter(x=x_p, y=y_p, mode='lines', line=dict(color='red', width=2), hoverinfo='skip'))

    for d in drills:
        actual_depth = thickness - d['z']
        fig.add_trace(go.Scatter(
            x=[d['x']], y=[d['y']], mode='markers',
            marker=dict(size=d['dia'], color=d['color'], line=dict(width=1, color='black')),
            text=d['desc'],
            customdata=[[d['t'], actual_depth]],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "תיאור כלי: %{text}<br>"
                "עומק חדירה: %{customdata[1]:.2f} מילימטר<br>"
                "מיקום: X=%{x:.2f}, Y=%{y:.2f}<extra></extra>"
            )
        ))

    fig.update_xaxes(title="ציר X (מילימטר)", range=[-50, 1350], gridcolor='rgba(0,0,0,0.1)', minor=dict(ticklen=4, showgrid=True))
    fig.update_yaxes(title="ציר Y (מילימטר)", range=[-50, 3100], gridcolor='rgba(0,0,0,0.1)', scaleanchor="x", scaleratio=1, minor=dict(ticklen=4, showgrid=True))
    
    fig.update_layout(
        title="Darwish CNC 40.4 - RTL & Border Fix",
        width=950, height=900,
        template="plotly_white",
        showlegend=False,
        hoverlabel=dict(
            bgcolor="white", 
            bordercolor="black", 
            font_size=14, 
            align="right"
        )
    )
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

st.sidebar.title("🛠️ ממשק אבי CNC 40.4")
nest = st.sidebar.checkbox("צמד לפינה (Nesting)", value=True)
rot = st.sidebar.checkbox("סובב Portrait (90°)", value=True)
st.sidebar.markdown("**מרווח הגנה (Margin):**")
mx = st.sidebar.number_input("ציר X (מילימטר)", value=0.0)
my = st.sidebar.number_input("ציר Y (מילימטר)", value=0.0)

uploaded = st.file_uploader("טען MPR", accept_multiple_files=True)
if uploaded:
    for f in uploaded:
        nc, drills, geos, thick = convert_logic(f.getvalue().decode('utf-8', errors='ignore'), pd.DataFrame(DEFAULT_TOOLS), rot, nest, mx, my, 2.0)
        plot_2d_pro(drills, geos, thick)
        st.download_button(f"📂 הורד קובץ NC: {f.name.split('.')[0]}", nc, f.name.replace(".mpr", ".nc"))
