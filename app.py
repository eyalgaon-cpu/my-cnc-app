import streamlit as st
import re, os
import pandas as pd
import math
import plotly.graph_objects as go

# Darwish CNC Pro 41.50 - Manual Pass Control & Grouping
st.set_page_config(page_title="Darwish CNC Pro 41.50", layout="wide")

if 'profiles' not in st.session_state:
    st.session_state.profiles = {
        "אבי": {
            "tools": [
                {"T_CNC": "T1", "קוטר": 40.0, "תיאור": "כרסום 40 (ניקוי פוקט)", "צבע": "brown"},
                {"T_CNC": "T2", "קוטר": 6.0, "תיאור": "כרסום 6 (קונטור חיצוני)", "צבע": "red"},
                {"T_CNC": "T3", "קוטר": 8.0, "תיאור": "כרסום 8", "צבע": "green"},
                {"T_CNC": "T4", "קוטר": 12.0, "תיאור": "כרסום 12", "צבע": "purple"},
                {"T_CNC": "T8", "קוטר": 19.0, "תיאור": "כרסום 19/20", "צבע": "darkblue"},
                {"T_CNC": "T11", "קוטר": 3.0, "תיאור": "כרסום 3", "צבע": "pink"},
                {"T_CNC": "T13", "קוטר": 0.2, "תיאור": "כרסום 90/45 (גירונג)", "צבע": "gold"},
                {"T_CNC": "T15", "קוטר": 5.0, "תיאור": "כרסום 5", "צבע": "lightgreen"},
                {"T_CNC": "T45", "קוטר": 5.0, "תיאור": "מקדח 5 (עובר)", "צבע": "white"},
                {"T_CNC": "T44", "קוטר": 5.0, "תיאור": "מקדח 5 (רגיל)", "צבע": "gray"},
                {"T_CNC": "T47", "קוטר": 8.0, "תיאור": "מקדח 8", "צבע": "darkgreen"},
                {"T_CNC": "T49", "קוטר": 15.0, "תיאור": "מקדח 15 (קבינאו)", "צבע": "yellow"},
                {"T_CNC": "T6", "קוטר": 35.0, "תיאור": "מקדח 35 (צירים)", "צבע": "orange"}
            ],
            "bed_x": 1300, "bed_y": 3050
        }
    }

def get_dist(p1, p2): return math.sqrt((p1['x'] - p2['x'])**2 + (p1['y'] - p2['y'])**2)

def optimize_path(points):
    if not points: return []
    optimized = []; curr = {'x': 0, 'y': 0}; rem = points[:]
    while rem:
        nxt = min(rem, key=lambda p: get_dist(curr, p))
        optimized.append(nxt); rem.remove(nxt); curr = nxt
    return optimized

def get_safe_float(key, block, default=0.0):
    match = re.search(f'{key}="([^"]*)"', block)
    if not match: return default
    try: return float(match.group(1))
    except: return default

def convert_logic_v415(mpr_text, rotate_90, zero_nesting, global_z_off, tool_map, local_offsets, custom_order, manual_passes):
    thickness = get_safe_float('t', mpr_text, 16.0)
    raw_drills = []
    geos = {}
    
    parts = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(parts), 2):
        if parts[i] == "1": continue 
        pts = []
        for elem in re.split(r'\$E\d+', parts[i+1]):
            x_m = re.search(r'X=([\d.-]+)', elem); y_m = re.search(r'Y=([\d.-]+)', elem)
            if x_m and y_m: pts.append([float(x_m.group(1)), float(y_m.group(1))])
        if pts: geos[parts[i]] = pts

    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1); xa, ya, ti = [get_safe_float(k, b) for k in ['XA', 'YA', 'TI']]
        t_mpr = (re.search(r'DU="([^"]*)"', b).group(1) if re.search(r'DU="([^"]*)"', b) else "5")
        t_cnc = tool_map.get(t_mpr, "T44"); l_off = local_offsets.get(t_mpr, 0.0)
        f_z = (thickness - ti) + global_z_off + l_off
        raw_drills.append({'x': xa, 'y': ya, 'z': f_z, 't': t_cnc, 'dia': 5.0})

    milling_ops = []
    for m in re.finditer(r'<(105|130)(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        bc = m.group(2); tno = re.search(r'TNO="([^"]*)"', bc).group(1) if re.search(r'TNO="([^"]*)"', bc) else "142"
        l_off = local_offsets.get(tno, 0.0)
        za = get_safe_float('ZA', bc) + global_z_off + l_off
        ea = re.search(r'EA="(\d+):', bc); geo_id = ea.group(1) if ea else None
        if geo_id in geos:
            milling_ops.append({'geo_id': geo_id, 'tno': tno, 'z_final': round(za, 3), 'pts': [p[:] for p in geos[geo_id]]})

    if rotate_90:
        for d in raw_drills: d['x'], d['y'] = -d['y'], d['x']
        for op in milling_ops:
            for p in op['pts']: p[0], p[1] = -p[1], p[0]

    all_x = [d['x'] for d in raw_drills] + [p[0] for op in milling_ops for p in op['pts']]
    all_y = [d['y'] for d in raw_drills] + [p[1] for op in milling_ops for p in op['pts']]
    mx, my = (min(all_x), min(all_y)) if zero_nesting and all_x else (0,0)
    for d in raw_drills: d['x'] -= mx; d['y'] -= my
    for op in milling_ops:
        for p in op['pts']: p[0] -= mx; p[1] -= my

    nc = ["%", "(NC DARWISH 41.5)", "G90 G54 G21"]; timeline = []; op_idx = 1
    
    # עיבוד קידוחים
    dr_tools = {}
    for d in raw_drills: dr_tools.setdefault(d['t'], []).append(d)
    for t_id in sorted(dr_tools.keys()):
        nc.append(f"M6 {t_id}"); timeline.append({"op": op_idx, "tool": t_id, "type": "Drill"})
        for d in optimize_path(dr_tools[t_id]):
            d['op_num'] = op_idx
            nc.extend([f"G0 X{d['x']:.3f} Y{d['y']:.3f}", f"G1 Z{d['z']:.3f} F1000", f"G0 Z{thickness+20}"])
        op_idx += 1

    # עיבוד כרסומים לפי קבוצות (Tool + Depth)
    mill_by_tool = {}
    for op in milling_ops:
        t_cnc = tool_map.get(op['tno'], "T2")
        mill_by_tool.setdefault(t_cnc, {}).setdefault(op['z_final'], []).append(op)
    
    f_order = [t for t in custom_order if t in mill_by_tool and t != "T2"]
    f_order += [t for t in sorted(mill_by_tool.keys()) if t not in f_order and t != "T2"]
    if "T2" in mill_by_tool: f_order.append("T2")

    for t_id in f_order:
        nc.append(f"M6 {t_id}")
        for z_fin, ops_list in mill_by_tool[t_id].items():
            timeline.append({"op": op_idx, "tool": t_id, "type": f"Mill (Z={z_fin})"})
            # שליפת עומקי פסיעות ידניות
            group_key = f"{t_id}_{z_fin}"
            pass_depths = manual_passes.get(group_key, [z_fin])
            
            for op in ops_list:
                op['op_num'] = op_idx
                op['pass_list'] = pass_depths
                for z_depth in pass_depths:
                    nc.append(f"(PASS Z={z_depth})")
                    nc.append(f"G0 X{op['pts'][0][0]:.3f} Y{op['pts'][0][1]:.3f}")
                    nc.append(f"G1 Z{z_depth:.3f} F2000")
                    for p in op['pts'][1:]: nc.append(f"G1 X{p[0]:.3f} Y{p[1]:.3f} F3000")
                    nc.append(f"G0 Z{thickness+20}")
            op_idx += 1

    nc.append("M30\n%")
    return "\n".join(nc), raw_drills, milling_ops, thickness, timeline

def plot_v415(drills, milling_ops, cfg, tool_map):
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=3050, y1=1300, line=dict(color="black", width=2), layer="below")
    for op in milling_ops:
        t_cnc = tool_map.get(op['tno'], "T2")
        t_info = next((t for t in cfg['tools'] if t['T_CNC'] == t_cnc), {"צבע": "red"})
        xp, yp = zip(*op['pts'])
        fig.add_trace(go.Scatter(
            x=xp, y=yp, mode='lines', line=dict(color=t_info['צבע'], width=2),
            name=f"Op {op['op_num']}",
            hovertemplate=f"<b>פעולה {op['op_num']}</b><br>כלי: {op['tno']}<br>עומק סופי: {op['z_final']} מילימטר<br>פסיעות: {len(op.get('pass_list', []))}<br>עומקים: {op.get('pass_list', [])}<extra></extra>"
        ))
    for d in drills:
        fig.add_trace(go.Scatter(x=[d['x']], y=[d['y']], mode='markers', marker=dict(size=8, color='blue'),
            hovertemplate=f"קידוח {d['t']}<br>Z: {d['z']:.2f} מילימטר<extra></extra>"))
    fig.update_layout(width=900, height=500, dragmode='pan', showlegend=False)
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

# --- UI ---
st.sidebar.title("🛠️ Darwish PRO 41.50")
cfg = st.session_state.profiles["אבי"]
nest = st.sidebar.checkbox("Nesting", value=True)
rot = st.sidebar.checkbox("סובב 90°", value=False)
gz_off = st.sidebar.slider("כיול Z גלובלי (מילימטר)", -3.0, 3.0, 0.0, 0.1)

uploaded = st.file_uploader("טען קבצי MPR", accept_multiple_files=True)
if uploaded:
    for f in uploaded:
        mpr_c = f.getvalue().decode('utf-8', errors='ignore')
        detected = sorted(list(set(re.findall(r'(?:DU|TNO)="([^"]*)"', mpr_c))))
        
        with st.sidebar.expander(f"⚙️ הגדרות: {f.name}", expanded=True):
            t_map = {}; l_offsets = {}
            for t_id in detected:
                col1, col2 = st.columns([2, 1])
                t_map[t_id] = col1.selectbox(f"MPR {t_id}:", [t['T_CNC'] for t in cfg['tools']], key=f"t_{f.name}_{t_id}")
                l_offsets[t_id] = col2.number_input("Z+/-", value=0.0, step=0.1, key=f"z_{f.name}_{t_id}")
            
            # ניתוח מקדים לקבוצות עומקים
            _, _, temp_ops, thick, _ = convert_logic_v415(mpr_c, rot, nest, gz_off, t_map, l_offsets, [], {})
            groups = {}
            for op in temp_ops:
                key = (t_map.get(op['tno'], "T2"), op['z_final'])
                groups.setdefault(key[0], []).append(op['z_final'])
            
            st.markdown("---")
            st.markdown("### 📏 שליטה בפסיעות")
            manual_passes = {}
            processed_keys = set()
            
            for t_cnc, depths in groups.items():
                unique_depths = sorted(list(set(depths)))
                if len(unique_depths) > 1:
                    st.warning(f"⚠️ כלי {t_cnc}: זוהו {len(unique_depths)} עומקים שונים")
                
                for z_val in unique_depths:
                    g_key = f"{t_cnc}_{z_val}"
                    st.markdown(f"**כלי {t_cnc} בעומק {z_val} מילימטר**")
                    num = st.number_input(f"כמות פסיעות:", 1, 10, 1, key=f"num_{f.name}_{g_key}")
                    
                    p_list = []
                    if num > 1:
                        for p_i in range(num - 1):
                            # הצעה אוטומטית לחלוקה שווה
                            suggested = round(thick - ((thick - z_val) / num) * (p_i + 1), 2)
                            p_val = st.number_input(f"עומק פסיעה {p_i+1}:", 0.0, 30.0, suggested, 0.1, key=f"pv_{f.name}_{g_key}_{p_i}")
                            p_list.append(p_val)
                    p_list.append(z_val) # פסיעה אחרונה תמיד העומק הסופי
                    manual_passes[g_key] = p_list
            
            m_order = st.multiselect("סדר כרסומים:", list(groups.keys()), key=f"ord_{f.name}")

        nc, drls, ops, thick, tm = convert_logic_v415(mpr_c, rot, nest, gz_off, t_map, l_offsets, m_order, manual_passes)
        st.subheader(f"📋 Timeline: {f.name}")
        tcols = st.columns(min(len(tm), 8))
        for idx, step in enumerate(tm[:8]):
            tcols[idx].info(f"#{step['op']}\n{step['tool']}")
        
        plot_v415(drls, ops, cfg, t_map)
        st.download_button(f"📥 הורד קוד NC", nc, f.name.replace(".mpr", ".nc"))
