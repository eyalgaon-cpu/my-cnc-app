import streamlit as st
import re, os
import pandas as pd
import math
import plotly.graph_objects as go

# הגדרות דף
st.set_page_config(page_title="Darwish CNC Pro 41.15 - Avi Edition", layout="wide")

# אתחול פרופיל אבי המלא - מעודכן לפי הטבלה האחרונה
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
                {"T_CNC": "T47", "קוטר": 8.0, "תיאור": "מקדח 8", "צבע": "darkgreen"},
                {"T_CNC": "T46", "קוטר": 10.0, "תיאור": "מקדח 10", "צבע": "blue"},
                {"T_CNC": "T49", "קוטר": 15.0, "תיאור": "מקדח 15 (קבינאו)", "צבע": "yellow"},
                {"T_CNC": "T6", "קוטר": 35.0, "תיאור": "מקדח 35 (צירים)", "צבע": "orange"}
            ]
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
    tools_list = machine_config['tools']
    raw_drills = []
    nc = [f"% ", f"(FILENAME: CONVERTED BY DARWISH)", f"G90 G54 G21"]
    
    # 1. חילוץ גאומטריות (]2, ]3 וכו')
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

    # 2. עיבוד קידוחים (<102)
    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1)
        xa, ya, ti = [get_safe_float(k, b) for k in ['XA', 'YA', 'TI']]
        t_mpr = re.search(r'DU="([^"]*)"', b).group(1)
        target_t = tool_map.get(t_mpr, "T44")
        
        # בקידוח: Z ב-NC הוא עובי פחות עומק (TI)
        f_z = (thickness - ti) + global_z_off
        raw_drills.append({'x': xa, 'y': ya, 'z': f_z, 't': target_t, 'dia': float(t_mpr), 'mpr_id': t_mpr})

    # 3. עיבוד כרסומים (<105 / <130)
    milling_ops = []
    for m in re.finditer(r'<(105|130)(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        block_content = m.group(2)
        tno = re.search(r'TNO="([^"]*)"', block_content)
        tno = tno.group(1) if tno else "142"
        za = get_safe_float('ZA', block_content) # ZA הוא הגובה מהשולחן
        
        # זיהוי איזה גאומטריה משויכת (לפי סדר הופעה בדרך כלל)
        ea_match = re.search(r'EA="(\d+):', block_content)
        geo_id = ea_match.group(1) if ea_match else None
        
        if geo_id in geos:
            milling_ops.append({'geo_id': geo_id, 'tno': tno, 'z': za, 'pts': geos[geo_id]})

    # החלת טרנספורמציות (סיבוב/צמידה)
    if rotate_90:
        for d in raw_drills: d['x'], d['y'] = -d['y'], d['x']
        for op in milling_ops:
            for p in op['pts']: p[0], p[1] = -p[1], p[0]

    if zero_nesting:
        all_x = [d['x'] for d in raw_drills] + [p[0] for op in milling_ops for p in op['pts']]
        all_y = [d['y'] for d in raw_drills] + [p[1] for op in milling_ops for p in op['pts']]
        if all_x:
            mx_p, my_p = min(all_x), min(all_y)
            for d in raw_drills: d['x'] -= mx_p; d['y'] -= my_p
            for op in milling_ops:
                for p in op['pts']: p[0] -= mx_p; p[1] -= my_p
            dx, dy = max(all_x)-min(all_x), max(all_y)-min(all_y)
        else: dx, dy = 0, 0
    else: dx, dy = 860.0, 477.0 # ברירת מחדל

    # כתיבת קוד NC
    last_t = ""
    # קודם קידוחים
    for d in raw_drills:
        if d['t'] != last_t:
            nc.append(f"M6 {d['t']} (DRILL {d['dia']}mm)")
            nc.append("M3 S18000")
            last_t = d['t']
        nc.extend([f"G0 X{d['x']:.3f} Y{d['y']:.3f}", f"G1 Z{d['z']:.3f} F1000", f"G0 Z{thickness+10}"])

    # אחר כך כרסומים
    for op in milling_ops:
        target_t = tool_map.get(op['tno'], "T2")
        if target_t != last_t:
            nc.append(f"M6 {target_t} (MILL TNO {op['tno']})")
            nc.append("M3 S16000")
            last_t = target_t
        
        pts = op['pts']
        nc.append(f"G0 X{pts[0][0]:.3f} Y{pts[0][1]:.3f}")
        nc.append(f"G1 Z{op['z']:.3f} F2000") # ZA נכנס ישירות ל-Z
        for p in pts[1:]:
            nc.append(f"G1 X{p[0]:.3f} Y{p[1]:.3f} F3000")
        nc.append(f"G0 Z{thickness+10}")

    nc.append("M30\n%")
    return "\n".join(nc), raw_drills, geos, thickness, dx, dy

# פונקציית שרטוט (Plotly)
def plot_2d_pro(drills, geos, thickness, dx, dy, filename):
    st.info(f"📐 לוח: {dx:.1f}x{dy:.1f} מילימטר | עובי: {thickness:.1f} מילימטר")
    fig = go.Figure()
    
    # שרטוט גאומטריות
    for bid, pts in geos.items():
        x_p, y_p = zip(*pts)
        fig.add_trace(go.Scatter(x=x_p, y=y_p, mode='lines', line=dict(color='blue', width=1), name=f"Geo {bid}"))
    
    # שרטוט קדחים
    for d in drills:
        fig.add_trace(go.Scatter(x=[d['x']], y=[d['y']], mode='markers', 
                                 marker=dict(size=d['dia'], color='red', line=dict(width=1, color='black')),
                                 name=f"Drill {d['dia']}"))

    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    fig.update_layout(width=800, height=600, template="plotly_white", title=f"תצוגה מקדימה: {filename}")
    st.plotly_chart(fig, use_container_width=True)

# ממשק משתמש (Sidebar)
st.sidebar.title("🛠️ Darwish PRO 41.15")
sel_m = st.sidebar.selectbox("מכונה:", list(st.session_state.profiles.keys()))
cfg = st.session_state.profiles[sel_m]

st.sidebar.markdown("---")
nest = st.sidebar.checkbox("צמד לפינה (Nesting)", value=True)
rot = st.sidebar.checkbox("סובב ב-90°", value=False)
gz_off = st.sidebar.slider("כיול Z (מ\"מ)", -2.0, 2.0, 0.0, 0.1)

uploaded = st.file_uploader("טען קבצי MPR", accept_multiple_files=True)
if uploaded:
    for f in uploaded:
        mpr_c = f.getvalue().decode('utf-8', errors='ignore')
        
        # זיהוי כלים אוטומטי מהקובץ
        raw_t = re.findall(r'(?:DU|TNO)="([^"]*)"', mpr_c)
        detected = sorted(list(set(raw_t)))
        
        with st.sidebar.expander(f"מיפוי: {f.name}", expanded=True):
            t_map = {}
            for t_id in detected:
                # לוגיקת בחירה אוטומטית לפי הטבלה של אבי
                d_idx = 1 # T2 (ברירת מחדל)
                if t_id == "130": d_idx = 6  # T13
                elif t_id == "128": d_idx = 3 # T4
                elif t_id == "8.0000" or t_id == "8": d_idx = 11 # T47
                elif t_id == "35.0000" or t_id == "35": d_idx = 14 # T6
                
                t_map[t_id] = st.selectbox(f"MPR {t_id} -> CNC:", [t['T_CNC'] for t in cfg['tools']], 
                                          index=min(d_idx, len(cfg['tools'])-1), key=f"{f.name}_{t_id}")

        nc_res, drls, geos, thick, dx, dy = convert_logic(mpr_c, cfg, rot, nest, 0.0, 0.0, gz_off, t_map)
        plot_2d_pro(drls, geos, thick, dx, dy, f.name)
        st.download_button(f"📥 הורד NC: {f.name}", nc_res, f.name.replace(".mpr", ".nc"))
