import streamlit as st
import re, os
import pandas as pd
import math
import plotly.graph_objects as go

# Darwish CNC Pro 42.00 - Robust Hierarchical Control
st.set_page_config(page_title="Darwish CNC Pro 42.00", layout="wide")

# אתחול פרופיל אבי (Ground Truth - Tool Mapping Final V2)
if 'profiles' not in st.session_state:
    st.session_state.profiles = {
        "אבי": {
            "tools": [
                {"T_CNC": "T1", "קוטר": 40.0, "תיאור": "כרסום 40 מילימטר (ניקוי פוקט)", "צבע": "brown"},
                {"T_CNC": "T2", "קוטר": 6.0, "תיאור": "כרסום 6 מילימטר (קונטור חיצוני)", "צבע": "red"},
                {"T_CNC": "T3", "קוטר": 8.0, "תיאור": "כרסום 8 מילימטר", "צבע": "green"},
                {"T_CNC": "T4", "קוטר": 12.0, "תיאור": "כרסום 12 מילימטר", "צבע": "purple"},
                {"T_CNC": "T8", "קוטר": 19.0, "תיאור": "כרסום 20 מילימטר (19 במכונה)", "צבע": "darkblue"},
                {"T_CNC": "T11", "קוטר": 3.0, "תיאור": "כרסום 3 מילימטר", "צבע": "pink"},
                {"T_CNC": "T13", "קוטר": 0.2, "תיאור": "כרסום 90/45 מעלות (גירונג)", "צבע": "gold"},
                {"T_CNC": "T6", "קוטר": 35.0, "תיאור": "מקדח 35 מילימטר (צירים)", "צבע": "orange"},
                {"T_CNC": "T49", "קוטר": 15.0, "תיאור": "מקדח 15 מילימטר (קבינאו)", "צבע": "yellow"},
                {"T_CNC": "T47", "קוטר": 8.0, "תיאור": "מקדח 8 מילימטר", "צבע": "darkgreen"},
                {"T_CNC": "T44", "קוטר": 5.0, "תיאור": "מקדח 5 מילימטר רגיל", "צבע": "gray"},
                {"T_CNC": "T45", "קוטר": 5.0, "תיאור": "מקדח 5 מילימטר עובר", "צבע": "white"}
            ],
            "bed_x": 3050, "bed_y": 1300
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

def convert_logic_v42(mpr_text, rotate_90, zero_nesting, global_z_off, tool_map, local_offsets, custom_passes):
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
        l_off = local_offsets.get(t_mpr, 0.0)
        f_z = (thickness - ti) + global_z_off + l_off
        t_cnc = tool_map.get(t_mpr, "T44")
        if t_mpr in ["BV5", "5"]: t_cnc = "T45" if f_z <= 0.2 else "T44"
        raw_drills.append({'x': xa, 'y': ya, 'z': f_z, 't': t_cnc})

    milling_groups = {} 
    for m in re.finditer(r'<(105|130)(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        bc = m.group(2); tno = re.search(r'TNO="([^"]*)"', bc).group(1) if re.search(r'TNO="([^"]*)"', bc) else "142"
        l_off = local_offsets.get(tno, 0.0)
        za = get_safe_float('ZA', bc) + global_z_off + l_off
        ea = re.search(r'EA="(\d+):', bc); geo_id = ea.group(1) if ea else None
        
        if geo_id and geo_id in geos:
            t_cnc = tool_map.get(tno, "T2")
            key = (geo_id, t_cnc)
            if key not in milling_groups:
                milling_groups[key] = {'tno': tno, 't_cnc': t_cnc, 'passes': [], 'pts': [p[:] for p in geos[geo_id]], 'geo_id': geo_id}
            milling_groups[key]['passes'].append(round(za, 3))

    if rotate_90:
        for d in raw_drills: d['x'], d['y'] = -d['y'], d['x']
        for g in milling_groups.values():
            for p in g['pts']: p[0], p[1] = -p[1], p[0]

    mx, my = (0,0)
    if zero_nesting:
        coords = [(d['x'], d['y']) for d in raw_drills] + [(p[0], p[1]) for g in milling_groups.values() for p in g['pts']]
        if coords: mx, my = min(x for x,y in coords), min(y for x,y in coords)
    
    for d in raw_drills: d['x'] -= mx; d['y'] -= my
    for g in milling_groups.values():
        for p in g['pts']: p[0] -= mx; p[1] -= my

    nc = ["%", "(NC DARWISH 42.0)", "G90 G54 G21"]; timeline = []; out_idx = 1
    
    dr_tools = {}
    for d in raw_drills: dr_tools.setdefault(d['t'], []).append(d)
    for t_id in sorted(dr_tools.keys()):
        nc.append(f"M6 {t_id}"); timeline.append({"op": out_idx, "tool": t_id, "type": "Drill"})
        for d in optimize_path(dr_tools[t_id]):
            d['disp_num'] = out_idx
            nc.extend([f"G0 X{d['x']:.3f} Y{d['y']:.3f}", f"G1 Z{d['z']:.3f} F1000", f"G0 Z{thickness+20}"])
        out_idx += 1

    mill_by_tool = {}
    for data in milling_groups.values():
        mill_by_tool.setdefault(data['t_cnc'], []).append(data)
    
    sorted_tools = [t for t in sorted(mill_by_tool.keys()) if t != "T2"]
    if "T2" in mill_by_tool: sorted_tools.append("T2")

    for t_id in sorted_tools:
        nc.append(f"M6 {t_id}")
        for group in mill_by_tool[t_id]:
            group['disp_num'] = out_idx
            g_key = f"{group['t_cnc']}_{group['tno']}_{group['geo_id']}"
            active_passes = sorted(custom_passes.get(g_key, group['passes']), reverse=True)
            group['active_passes'] = active_passes
            
            timeline.append({"op": out_idx, "tool": t_id, "type": "Mill"})
            for z_depth in active_passes:
                nc.append(f"(PASS Z={z_depth})")
                nc.append(f"G0 X{group['pts'][0][0]:.3f} Y{group['pts'][0][1]:.3f}")
                nc.append(f"G1 Z{z_depth:.3f} F2000")
                for p in group['pts'][1:]: nc.append(f"G1 X{p[0]:.3f} Y{p[1]:.3f} F3000")
                nc.append(f"G0 Z{thickness+20}")
            out_idx += 1

    nc.append("M30\n%")
    return "\n".join(nc), raw_drills, list(milling_groups.values()), thickness, timeline

def plot_v42(drills, milling_list, thickness, cfg, tool_map):
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=3050, y1=1300, line=dict(color="black", width=2), layer="below")
    
    for g in milling_list:
        t_info = next((t for t in cfg['tools'] if t['T_CNC'] == g['t_cnc']), {"צבע": "red", "תיאור": "כרסום"})
        xp, yp = zip(*g['pts'])
        p_list = sorted(g.get('active_passes', g['passes']), reverse=True)
        
        if len(p_list) > 1:
            pass_info = "".join([f"<br>פסיעה {'ראשונה' if i==0 else 'שנייה' if i==1 else f'מספר {i+1}'} - {round(thickness - p, 2)} מילימטר (מהחלק העליון)" for i, p in enumerate(p_list)])
        else:
            pass_info = f"<br>עומק כרסום: {round(thickness - p_list[0], 2)} מילימטר (מהחלק העליון)"

        fig.add_trace(go.Scatter(
            x=xp, y=yp, mode='lines', line=dict(color=t_info['צבע'], width=2),
            name=f"Op {g.get('disp_num', '?')}",
            hovertemplate=f"<b>פעולה {g.get('disp_num', '?')}</b><br>כלי: {g['t_cnc']} ({t_info['תיאור']}){pass_info}<extra></extra>"
        ))
    
    for d in drills:
        fig.add_trace(go.Scatter(x=[d['x']], y=[d['y']], mode='markers', marker=dict(size=8, color='blue'),
            hovertemplate=f"קידוח {d['t']}<br>Z סופי: {d['z']:.2f} מילימטר<extra></extra>"))
            
    fig.update_layout(width=1000, height=500, dragmode='pan', xaxis=dict(range=[0, 3050]), yaxis=dict(range=[0, 1300]))
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

# --- UI ---
st.sidebar.title("🛠️ Darwish PRO 42.00")
cfg = st.session_state.profiles["אבי"]
nest = st.sidebar.checkbox("Nesting (יישור ל-0,0)", value=False)
rot = st.sidebar.checkbox("סובב 90°", value=False)
gz_off = st.sidebar.slider("כיול Z גלובלי (מילימטר)", -3.0, 3.0, 0.0, 0.1)

uploaded = st.file_uploader("טען קבצי MPR", accept_multiple_files=True)
if uploaded:
    for f in uploaded:
        mpr_c = f.getvalue().decode('utf-8', errors='ignore')
        detected_ids = sorted(list(set(re.findall(r'(?:DU|TNO)="([^"]*)"', mpr_c))))
        
        with st.sidebar.expander(f"⚙️ הגדרות ופסיעות: {f.name}", expanded=True):
            t_map = {}; l_offsets = {}
            for t_id in detected_ids:
                col1, col2 = st.columns([2, 1])
                a_idx = 6 if t_id=="130" else 3 if t_id=="128" else 2 if t_id=="158" else 0 if t_id=="137" else 10 if t_id=="BV8" else 1
                t_map[t_id] = col1.selectbox(f"MPR {t_id}:", [t['T_CNC'] for t in cfg['tools']], index=min(a_idx, 11), key=f"t_{f.name}_{t_id}")
                l_offsets[t_id] = col2.number_input("Z+/-", value=0.0, step=0.1, key=f"z_{f.name}_{t_id}")
            
            # ניתוח פסיעות ראשוני (ללא שינויים)
            _, _, mill_list, thick, _ = convert_logic_v42(mpr_c, rot, nest, gz_off, t_map, l_offsets, {})
            
            st.markdown("---")
            st.markdown("### 📏 ניהול פסיעות")
            custom_passes = {}
            for g in mill_list:
                t_info = next((t for t in cfg['tools'] if t['T_CNC'] == g['t_cnc']), {"תיאור": ""})
                g_key = f"{g['t_cnc']}_{g['tno']}_{g['geo_id']}"
                
                st.markdown(f"**כלי {g['t_cnc']} - {t_info['תיאור']}**")
                
                orig_passes = sorted(g['passes'], reverse=True)
                updated_passes = []
                for i, p_val in enumerate(orig_passes):
                    label = f"פסיעה {'ראשונה' if i==0 else 'שנייה' if i==1 else f'פסיעה {i+1}'}:"
                    updated_passes.append(st.number_input(label, 0.0, 30.0, p_val, 0.1, key=f"p_{f.name}_{g_key}_{i}"))
                
                if st.checkbox("הוסף פסיעה", key=f"add_{f.name}_{g_key}"):
                    last_z = updated_passes[-1] if updated_passes else 0.0
                    updated_passes.append(st.number_input("עומק פסיעה חדשה (Z):", 0.0, 30.0, last_z, 0.1, key=f"new_{f.name}_{g_key}"))
                
                custom_passes[g_key] = updated_passes

        # יצירת NC סופי עם כל השינויים
        nc, drls, final_mills, thick, tm = convert_logic_v42(mpr_c, rot, nest, gz_off, t_map, l_offsets, custom_passes)
        st.subheader(f"📋 Timeline & Simulation: {f.name}")
        tcols = st.columns(min(len(tm), 10))
        for idx, step in enumerate(tm[:10]):
            tcols[idx].info(f"#{step['op']}\n{step['tool']}")
        
        plot_v42(drls, final_mills, thick, cfg, t_map)
        st.download_button(f"📥 הורד קוד NC", nc, f.name.replace(".mpr", ".nc"))
