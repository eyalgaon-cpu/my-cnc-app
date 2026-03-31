import streamlit as st
import re, os
import pandas as pd
import math
import plotly.graph_objects as go

# הגדרות דף
st.set_page_config(page_title="Darwish CNC Pro 41.8", layout="wide")

if 'profiles' not in st.session_state:
    st.session_state.profiles = {
        "אבי": {
            "tools": [
                {"T_CNC": "T1", "קוטר": 40.0, "תיאור": "כרסום 40 (ניקוי פוקט)", "צבע": "brown", "תיקון_Z": 0.0},
                {"T_CNC": "T2", "קוטר": 6.0, "תיאור": "כרסום 6 (B-20)", "צבע": "red", "תיקון_Z": 0.0},
                {"T_CNC": "T3", "קוטר": 8.0, "תיאור": "כרסום 8 (B-30)", "צבע": "green", "תיקון_Z": 0.0},
                {"T_CNC": "T4", "קוטר": 12.0, "תיאור": "כרסום 12 (B-30)", "צבע": "purple", "תיקון_Z": 0.0},
                {"T_CNC": "T8", "קוטר": 19.0, "תיאור": "כרסום 19", "צבע": "darkblue", "תיקון_Z": 0.0},
                {"T_CNC": "T11", "קוטר": 3.0, "תיאור": "כרסום 3 (B-15)", "צבע": "pink", "תיקון_Z": 0.0},
                {"T_CNC": "T15", "קוטר": 5.0, "תיאור": "כרסום 5 (B-15)", "צבע": "lightgreen", "תיקון_Z": 0.0},
                {"T_CNC": "T23", "קוטר": 12.7, "תיאור": "כרסום 12.7 (ארוך)", "צבע": "darkred", "תיקון_Z": 0.0},
                {"T_CNC": "T48", "קוטר": 3.0, "תיאור": "מקדח 3", "צבע": "gray", "תיקון_Z": 0.0},
                {"T_CNC": "T45", "קוטר": 5.0, "תיאור": "מקדח 5 (עובר)", "צבע": "white", "תיקון_Z": 0.0},
                {"T_CNC": "T44", "קוטר": 5.0, "תיאור": "מקדח 5", "צבע": "gray", "תיקון_Z": 0.0},
                {"T_CNC": "T42", "קוטר": 5.0, "תיאור": "מקדח 5 (שלישייה)", "צבע": "lightgray", "תיקון_Z": 0.0},
                {"T_CNC": "T47", "קוטר": 8.0, "תיאור": "מקדח 8", "צבע": "darkgreen", "תיקון_Z": -1.0},
                {"T_CNC": "T46", "קוטר": 10.0, "תיאור": "מקדח 10", "צבע": "blue", "תיקון_Z": -0.5},
                {"T_CNC": "T49", "קוטר": 15.0, "תיאור": "מקדח 15 (קבינאו)", "צבע": "yellow", "תיקון_Z": 0.0},
                {"T_CNC": "T6", "קוטר": 35.0, "תיאור": "מקדח 35", "צבע": "orange", "תיקון_Z": -0.1}
            ],
            "z_off": 0.0, "mx": 0.0, "my": 0.0
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
    thickness = get_safe_float('t', mpr_text, 19.0)
    tools_list = machine_config['tools']
    raw_drills = []
    
    # 1. עיבוד קידוחים
    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1)
        xa, ya, ti = [get_safe_float(k, b) for k in ['XA', 'YA', 'TI']]
        an, ab, wi = int(get_safe_float('AN', b, 1)), get_safe_float('AB', b), get_safe_float('WI', b)
        t_mpr = re.search(r'DU="([^"]*)"', b).group(1)
        target_t = tool_map.get(t_mpr)
        conf = next((t for t in tools_list if t['T_CNC'] == target_t), None)
        if conf:
            f_z = (thickness - ti) + global_z_off - conf.get("תיקון_Z", 0.0)
            for i in range(an):
                cur_x = xa + i * ab * math.cos(math.radians(wi))
                cur_y = ya + i * ab * math.sin(math.radians(wi))
                raw_drills.append({'x': cur_x, 'y': cur_y, 'z': f_z, 't': conf['T_CNC'], 'desc': conf['תיאור'], 'dia': conf['קוטר'], 'color': conf['צבע'], 'mpr_id': t_mpr})

    # 2. עיבוד גאומטריה (קונטור)
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
        mx_p, my_p = min(all_x), min(all_y)
        for d in raw_drills: d['x'] -= mx_p; d['y'] -= my_p
        for pts in geos.values():
            for p in pts: p[0] -= mx_p; p[1] -= my_p

    for d in raw_drills: d['x'] += margin_x; d['y'] += margin_y
    for pts in geos.values():
        for p in pts: p[0] += margin_x; p[1] += margin_y

    # 3. יצירת קובץ NC - קידוחים ואז כרסום
    nc = [f"G90 G54"]
    for d in raw_drills:
        nc.extend([f"T{d['t']} M06", f"G00 X{d['x']:.3f} Y{d['y']:.3f}", f"G01 Z{d['z']:.3f} F2000", f"G00 Z{thickness+10:.3f}"])

    # הוספת שלב הכרסום ב-NC
    c_match = re.search(r'<(105|130)(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL)
    if c_match:
        t_mpr = re.search(r'(TNO|T_CNC|DU)="([^"]*)"', c_match.group(2)).group(2)
        target_t = tool_map.get(t_mpr)
        conf = next((t for t in tools_list if t['T_CNC'] == target_t), None)
        
        if conf and geos:
            nc.append(f"(CONTOUR MILLING - TOOL {conf['T_CNC']})")
            nc.append(f"T{conf['T_CNC']} M06")
            
            # פסיעות: 18.70 ו-19.20 (לפי עובי 19)
            z_passes = [thickness - 0.3 + global_z_off, thickness + 0.2 + global_z_off]
            
            for z_val in z_passes:
                nc.append(f"(PASS AT Z {z_val:.2f})")
                for bid, pts in geos.items():
                    # תנועה לנקודת התחלה
                    nc.append(f"G00 X{pts[0][0]:.3f} Y{pts[0][1]:.3f}")
                    nc.append(f"G01 Z{z_val:.3f} F1500")
                    # כרסום הקונטור
                    for p in pts[1:]:
                        nc.append(f"G01 X{p[0]:.3f} Y{p[1]:.3f} F3000")
                    nc.append(f"G00 Z{thickness+10:.3f}")

    contour_info = {"tool": "לא זוהה", "passes": [f"{thickness - 0.3:.2f} מילימטר", f"{thickness + 0.2:.2f} מילימטר"]}
    if c_match and conf: contour_info["tool"] = f"{conf['תיאור']} ({conf['T_CNC']})"

    return "\n".join(nc), raw_drills, geos, thickness, dx, dy, contour_info

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
        fig.add_trace(go.Scatter(x=[d['x']], y=[d['y']], mode='markers', marker=dict(size=d['dia'], color=d['color'], line=dict(width=1, color='black')), name=f"MPR: {d['mpr_id']}", customdata=[[d['t'], d['desc'], thickness - d['z'], d['mpr_id']]], hovertemplate="<b>%{customdata[0]}</b> (MPR: %{customdata[3]})<br>כלי: %{customdata[1]}<br>עומק: %{customdata[2]:.2f} מילימטר<extra></extra>"))
    fig.update_layout(width=900, height=850, template="plotly_white", showlegend=False)
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

# Sidebar
st.sidebar.title("🛠️ ממשק דרוויש 41.8")
sel_m = st.sidebar.selectbox("בחר מכונה:", list(st.session_state.profiles.keys()))
cfg = st.session_state.profiles[sel_m]

with st.expander("📦 ניהול כלי עבודה", expanded=False):
    edited_tools = st.data_editor(pd.DataFrame(cfg['tools']), num_rows="dynamic")
    if st.button("שמור שינויים"):
        st.session_state.profiles[sel_m]['tools'] = edited_tools.to_dict('records')

uploaded = st.file_uploader("טען קבצי MPR", accept_multiple_files=True)
if uploaded:
    for f in uploaded:
        mpr_c = f.getvalue().decode('utf-8', errors='ignore')
        detected = sorted(list(set(re.findall(r'(?:DU|TNO|T_CNC|DI|D)="([^"]*)"', mpr_c))))
        with st.sidebar.expander(f"🔗 מיפוי כלים: {f.name}", expanded=True):
            t_map = {}
            for t_id in detected:
                d_idx = 0
                if "15" in t_id: d_idx = 14
                elif "35" in t_id: d_idx = 15
                elif "142" in t_id: d_idx = 1
                t_map[t_id] = st.selectbox(f"כלי MPR {t_id}:", [t['T_CNC'] for t in cfg['tools']], index=d_idx, key=f"v418_{f.name}_{t_id}")

        nc_res, drls, geos, thick, dx, dy, c_inf = convert_logic(mpr_c, cfg, True, True, 0.0, 0.0, 0.0, t_map)
        plot_2d_pro(drls, geos, thick, dx, dy, c_inf, f.name)
        st.download_button(f"📂 הורד NC עבור {f.name}", nc_res, f.name.replace(".mpr", ".nc"))
