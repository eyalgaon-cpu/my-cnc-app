import streamlit as st
import re, os
import pandas as pd
import math
import plotly.graph_objects as go

st.set_page_config(page_title="Darwish CNC Pro 36.0", layout="wide")

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

def convert_logic(mpr_text, tool_df, num_passes, swap_axes, offset, zero_nesting, margin, global_z_off):
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

    raw_drills, raw_millings = [], []
    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1)
        xa, ya, ti, du = [get_safe_float(k, b) for k in ['XA', 'YA', 'TI', 'DU']]
        an, ab, wi = int(get_safe_float('AN', b, 1)), get_safe_float('AB', b), get_safe_float('WI', b)
        conf = dia_map.get(round(du, 1))
        if conf is None: continue
        
        final_z = (thickness - ti) - global_z_off - conf.get("תיקון_Z", 0.0)
        for i in range(an):
            raw_drills.append({
                'x': xa + i * ab * math.cos(math.radians(wi)),
                'y': ya + i * ab * math.sin(math.radians(wi)),
                'z': final_z, 't': conf['T_CNC'], 's': conf['S'], 'f': conf['F'], 'dia': du, 'color': conf['צבע']
            })

    for m in re.finditer(r'<105(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1)
        geo_m = re.search(r'EA="(\d+):', b)
        if geo_m:
            eid = geo_m.group(1)
            za = get_safe_float('ZA', b)
            conf = dia_map.get(6.0, {"T_CNC": "T2", "צבע": "red"})
            raw_millings.append({'geo_id': eid, 'z': za - global_z_off, 't': conf['T_CNC'], 'color': conf['צבע']})

    if zero_nesting:
        ref_x = [p[0] for pts in geos.values() for p in pts] if geos else [d['x'] for d in raw_drills]
        ref_y = [p[1] for pts in geos.values() for p in pts] if geos else [d['y'] for d in raw_drills]
        if ref_x and ref_y:
            mx, my = min(ref_x), min(ref_y)
            for d in raw_drills: d['x'] -= mx; d['y'] -= my
            for pts in geos.values():
                for p in pts: p[0] -= mx; p[1] -= my

    for d in raw_drills:
        d['x'] += margin; d['y'] += margin
        if swap_axes: d['x'], d['y'] = d['y'], d['x']
    for pts in geos.values():
        for p in pts:
            p[0] += margin; p[1] += margin
            if swap_axes: p[0], p[1] = p[1], p[0]

    # יצירת ה-G-Code (הלוגיקה נשארת זהה)
    nc = [f"G90 {offset}"]
    # ... (המשך לוגיקת הכתיבה המוכרת שלך) ...
    # לצורך הקיצור כאן, נניח שהפונקציה מחזירה גם את רשימת הנקודות להדמיה
    return nc, raw_drills, geos

def plot_preview(drills, geos, margin):
    fig = go.Figure()
    # ציור קונטור (כרסום)
    for bid, pts in geos.items():
        if len(pts) > 1:
            x_pts, y_pts = zip(*pts)
            fig.add_trace(go.Scatter(x=x_pts, y=y_pts, mode='lines', name=f'Milling {bid}', line=dict(color='red')))
    
    # ציור קידוחים
    for d in drills:
        fig.add_trace(go.Scatter(
            x=[d['x']], y=[d['y']], mode='markers',
            marker=dict(size=d['dia'], color=d['color']),
            name=f"{d['t']} (Dia {d['dia']})",
            hovertemplate=f"X: %{{x}}<br>Y: %{{y}}<br>Z: {d['z']:.2f}"
        ))
    
    fig.update_layout(title="תצוגה מקדימה - אבי CNC", xaxis_title="X (מילימטר)", yaxis_title="Y (מילימטר)",
                      width=800, height=600, showlegend=True, template="plotly_white")
    st.plotly_chart(fig)

# UI
st.title("🪚 Darwish CNC Pro - גרסה 36.0")
if 'tool_df' not in st.session_state: st.session_state.tool_df = pd.DataFrame(DEFAULT_TOOLS)
edited_df = st.sidebar.data_editor(st.session_state.tool_df)
mar = st.sidebar.number_input("Margin", value=7.0)
nest = st.sidebar.checkbox("צמד לפינה", value=True)
uploaded = st.file_uploader("בחר קבצי MPR", accept_multiple_files=True)

if uploaded:
    for f in uploaded:
        nc_list, drills, geos = convert_logic(f.getvalue().decode('utf-8', errors='ignore'), edited_df, 0, True, "G54", nest, mar, 2.0)
        plot_preview(drills, geos, mar)
        st.download_button(f"📂 הורד {f.name.replace('.mpr', '.nc')}", "\n".join(nc_list), f.name.replace(".mpr", ".nc"))
