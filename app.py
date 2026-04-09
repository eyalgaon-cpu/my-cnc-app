import streamlit as st
import re, os
import pandas as pd
import math
import plotly.graph_objects as go

# הגדרות דף
st.set_page_config(page_title="Darwish CNC Pro 41.22 - Avi Edition", layout="wide")

# אתחול פרופיל אבי המלא - הגרסה המורחבת (200 שורות)
if 'profiles' not in st.session_state:
    st.session_state.profiles = {
        "אבי": {
            "tools": [
                {"T_CNC": "T1", "קוטר": 40.0, "תיאור": "כרסום 40 (ניקוי פוקט)", "צבע": "brown"},
                {"T_CNC": "T2", "קוטר": 6.0, "תיאור": "כרסום 6", "צבע": "red"},
                {"T_CNC": "T3", "קוטר": 8.0, "תיאור": "כרסום 8", "צבע": "green"},
                {"T_CNC": "T4", "קוטר": 12.0, "תיאור": "כרסום 12", "צבע": "purple"},
                {"T_CNC": "T8", "קוטר": 19.0, "תיאור": "כרסום 19/20", "צבע": "darkblue"},
                {"T_CNC": "T11", "קוטר": 3.0, "תיאור": "כרסום 3", "צבע": "pink"},
                {"T_CNC": "T13", "קוטר": 0.2, "תיאור": "כרסום 90/45 (גירונג)", "צבע": "gold"},
                {"T_CNC": "T15", "קוטר": 5.0, "תיאור": "כרסום 5", "צבע": "lightgreen"},
                {"T_CNC": "T48", "קוטר": 3.0, "תיאור": "מקדח 3", "צבע": "gray"},
                {"T_CNC": "T45", "קוטר": 5.0, "תיאור": "מקדח 5 (עובר)", "צבע": "white"},
                {"T_CNC": "T44", "קוטר": 5.0, "תיאור": "מקדח 5 (רגיל)", "צבע": "gray"},
                {"T_CNC": "T42", "קוטר": 5.0, "תיאור": "מקדח 5 (שלישייה)", "צבע": "lightgray"},
                {"T_CNC": "T47", "קוטר": 8.0, "תיאור": "מקדח 8", "צבע": "darkgreen"},
                {"T_CNC": "T46", "קוטר": 10.0, "תיאור": "מקדח 10", "צבע": "blue"},
                {"T_CNC": "T49", "קוטר": 15.0, "תיאור": "מקדח 15 (קבינאו)", "צבע": "yellow"},
                {"T_CNC": "T6", "קוטר": 35.0, "תיאור": "מקדח 35 (צירים)", "צבע": "orange"}
            ],
            "bed_x": 1300, "bed_y": 3050
        }
    }

def get_safe_float(key, block, default=0.0):
    match = re.search(f'{key}="([^"]*)"', block)
    if not match: return default
    try: return float(match.group(1))
    except:
        nums = re.findall(r'[\d.-]+', match.group(1))
        return float(nums[0]) if nums else default

def convert_logic(mpr_text, machine_config, rotate_90, zero_nesting, margin_x, margin_y, global_z_off, tool_map):
    thickness = get_safe_float('t', mpr_text, 16.0)
    raw_drills = []
    nc = ["% ", "(CONVERTED BY DARWISH PRO 2026)", "G90 G54 G21"]
    
    geos = {}
    parts = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(parts), 2):
        if parts[i] == "1": continue 
        pts = []
        for elem in re.split(r'\$E\d+', parts[i+1]):
            x_m = re.search(r'X=([\d.-]+)', elem)
            y_m = re.search(r'Y=([\d.-]+)', elem)
            if x_m and y_m: pts.append([float(x_m.group(1)), float(y_m.group(1))])
        if pts: geos[parts[i]] = pts

    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1)
        xa, ya, ti = [get_safe_float(k, b) for k in ['XA', 'YA', 'TI']]
        t_mpr = re.search(r'DU="([^"]*)"', b).group(1)
        target_t = tool_map.get(t_mpr, "T44")
        f_z = (thickness - ti) + global_z_off
        raw_drills.append({'x': xa, 'y': ya, 'z': f_z, 't': target_t, 'dia': float(t_mpr), 'mpr_id': t_mpr})

    milling_ops = []
    for m in re.finditer(r'<(105|130)(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        block_content = m.group(2)
        tno_match = re.search(r'TNO="([^"]*)"', block_content)
        tno = tno_match.group(1) if tno_match else "142"
        za = get_safe_float('ZA', block_content) 
        ea_match = re.search(r'EA="(\d+):', block_content)
        geo_id = ea_match.group(1) if ea_match else None
        if geo_id in geos:
            milling_ops.append({'geo_id': geo_id, 'tno': tno, 'z': za, 'pts': [p[:] for p in geos[geo_id]]})

    if rotate_90:
        for d in raw_drills: d['x'], d['y'] = -d['y'], d['x']
        for op in milling_ops:
            for p in op['pts']: p[0], p[1] = -p[1], p[0]

    if zero_nesting:
        all_coords_x = [d['x'] for d in raw_drills] + [p[0] for op in milling_ops for p in op['pts']]
        all_coords_y = [d['y'] for d in raw_drills] + [p[1] for op in milling_ops for p in op['pts']]
        if all_coords_x:
            min_x, min_y = min(all_coords_x), min(all_coords_y)
            for d in raw_drills: d['x'] -= min_x; d['y'] -= min_y
            for op in milling_ops:
                for p in op['pts']: p[0] -= min_x; p[1] -= min_y
            dx, dy = max(all_coords_x)-min_x, max(all_coords_y)-min_y
        else: dx, dy = 0, 0
    else: dx, dy = 0, 0

    last_t = ""
    for d in raw_drills:
        if d['t'] != last_t:
            nc.append(f"M6 {d['t']} (DRILL {d['dia']}mm)")
            nc.append("M3 S18000")
            last_t = d['t']
        nc.extend([f"G0 X{d['x'] + margin_x:.3f} Y{d['y'] + margin_y:.3f}", f"G1 Z{d['z']:.3f} F1000", f"G0 Z{thickness+20}"])

    for op in milling_ops:
        target_t = tool_map.get(op['tno'], "T2")
        if target_t != last_t:
            nc.append(f"M6 {target_t} (MILL TNO {op['tno']})")
            nc.append("M3 S16000")
            last_t = target_t
        pts = op['pts']
        nc.append(f"G0 X{pts[0][0] + margin_x:.3f} Y{pts[0][1] + margin_y:.3f}")
        nc.append(f"G1 Z{op['z']:.3f} F2000")
        for p in pts[1:]: nc.append(f"G1 X{p[0] + margin_x:.3f} Y{p[1] + margin_y:.3f} F3000")
        nc.append(f"G0 Z{thickness+20}")

    nc.append("M30\n%")
    return "\n".join(nc), raw_drills, milling_ops, thickness, dx, dy

def plot_2d_pro(drills, milling_ops, thickness, dx, dy, filename):
    st.info(f"📏 מידות חלק: {dx:.2f} × {dy:.2f} מילימטר | עובי: {thickness:.2f} מילימטר")
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=1300, y1=3050, fillcolor="whitesmoke", line=dict(color="black", width=2), layer="below")
    
    for op in milling_ops:
        x_p, y_p = zip(*op['pts'])
        fig.add_trace(go.Scatter(x=x_p, y=y_p, mode='lines', line=dict(color='red', width=2), name=f"כלי {op['tno']}"))
    
    for d in drills:
        fig.add_trace(go.Scatter(x=[d['x']], y=[d['y']], mode='markers',
                                marker=dict(size=d['dia'], sizemode='diameter', color='blue', line=dict(width=1, color='black'))))

    fig.update_xaxes(title="ציר X (מילימטר)", range=[-50, 1400], showline=True, mirror=True)
    fig.update_yaxes(title="ציר Y (מילימטר)", range=[-50, 3200], scaleanchor="x", scaleratio=1, showline=True, mirror=True)
    
    # התיקון: הפעלת Pan וזום עם הגלגלת
    fig.update_layout(width=850, height=1000, template="plotly_white", dragmode='pan', showlegend=False)
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

# --- UI Sidebar ---
st.sidebar.title("🛠️ Darwish PRO 41.22")
cfg = st.session_state.profiles["אבי"]

nest = st.sidebar.checkbox("צמד לפינה (Nesting)", value=True)
rot = st.sidebar.checkbox("סובב ב-90°", value=False)
m_x = st.sidebar.number_input("מרווח X (מילימטר)", value=0.0)
m_y = st.sidebar.number_input("מרווח Y (מילימטר)", value=0.0)
gz_off = st.sidebar.slider("כיול Z (מילימטר)", -3.0, 3.0, 0.0, 0.1)

uploaded = st.file_uploader("טען קבצי MPR להמרה", accept_multiple_files=True)

if uploaded:
    for f in uploaded:
        mpr_content = f.getvalue().decode('utf-8', errors='ignore')
        raw_tools = re.findall(r'(?:DU|TNO)="([^"]*)"', mpr_content)
        detected_tools = sorted(list(set(raw_tools)))
        
        with st.sidebar.expander(f"🔗 מיפוי כלים: {f.name}", expanded=True):
            current_tool_map = {}
            for t_id in detected_tools:
                auto_idx = 1
                if t_id == "130": auto_idx = 6 
                elif t_id == "128": auto_idx = 3 
                elif t_id == "158": auto_idx = 2 
                elif t_id in ["8.0000", "8"]: auto_idx = 12 
                elif t_id in ["35.0000", "35"]: auto_idx = 15 
                elif t_id in ["15.0000", "15"]: auto_idx = 14 
                elif t_id in ["3.0000", "3"]: auto_idx = 8 
                
                current_tool_map[t_id] = st.selectbox(
                    f"MPR {t_id} -> אבי:", [t['T_CNC'] for t in cfg['tools']], 
                    index=min(auto_idx, len(cfg['tools'])-1), key=f"m_{f.name}_{t_id}"
                )

        nc_res, drls, ops, thick, dx, dy = convert_logic(mpr_content, cfg, rot, nest, m_x, m_y, gz_off, current_tool_map)
        plot_2d_pro(drls, ops, thick, dx, dy, f.name)
        st.download_button(f"📥 הורד NC עבור {f.name}", nc_res, f.name.replace(".mpr", ".nc"))
