import streamlit as st
import re, os
import pandas as pd
import math
import plotly.graph_objects as go

# Darwish PRO 42.60 - Absolute Tool Mapping & Final Hierarchy
st.set_page_config(page_title="Darwish PRO 42.60", layout="wide")

if 'profiles' not in st.session_state:
    st.session_state.profiles = {
        "אבי": {
            "tools": [
                {"T_CNC": "T1", "קוטר": 40.0, "תיאור": "כרסום 40 מילימטר (ניקוי פוקט)", "צבע": "brown"},
                {"T_CNC": "T2", "קוטר": 6.0, "תיאור": "כרסום 6 מילימטר (קונטור חיצוני)", "צבע": "red"},
                {"T_CNC": "T3", "קוטר": 8.0, "תיאור": "כרסום 8 מילימטר", "צבע": "green"},
                {"T_CNC": "T4", "קוטר": 12.0, "תיאור": "כרסום 12 מילימטר", "צבע": "purple"},
                {"T_CNC": "T8", "קוטר": 19.0, "תיאור": "כרסום 20 מילימטר", "צבע": "darkblue"},
                {"T_CNC": "T11", "קוטר": 3.0, "תיאור": "כרסום 3 מילימטר", "צבע": "pink"},
                {"T_CNC": "T13", "קוטר": 0.2, "תיאור": "כרסום 90/45 מעלות", "צבע": "gold"},
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
    return float(match.group(1)) if match else default

def convert_logic_v42_6(mpr_text, rotate_90, zero_nesting, global_z_off, tool_map, local_offsets, custom_passes_dict):
    thickness = get_safe_float('t', mpr_text, 16.0)
    raw_drills = []
    geos = {}
    
    parts = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(parts), 2):
        pts = []
        for elem in re.split(r'\$E\d+', parts[i+1]):
            x_m = re.search(r'X=([\d.-]+)', elem); y_m = re.search(r'Y=([\d.-]+)', elem)
            if x_m and y_m: pts.append([float(x_m.group(1)), float(y_m.group(1))])
        if pts: geos[parts[i]] = pts

    # קדחים - אופטימיזציית השכן הקרוב
    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1); xa, ya, ti = [get_safe_float(k, b) for k in ['XA', 'YA', 'TI']]
        t_mpr = (re.search(r'DU="([^"]*)"', b).group(1) if re.search(r'DU="([^"]*)"', b) else "5")
        l_off = local_offsets.get(t_mpr, 0.0)
        f_z = (thickness - ti) + global_z_off + l_off
        t_cnc = tool_map.get(t_mpr, "T44")
        if t_mpr in ["BV5", "5"]: t_cnc = "T45" if f_z <= 0.2 else "T44"
        raw_drills.append({'x': xa, 'y': ya, 'z': f_z, 't': t_cnc})

    # כרסומים
    milling_data = []
    for m in re.finditer(r'<(105|130)(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        bc = m.group(2); tno = re.search(r'TNO="([^"]*)"', bc).group(1) if re.search(r'TNO="([^"]*)"', bc) else "142"
        l_off = local_offsets.get(tno, 0.0)
        za = get_safe_float('ZA', bc) + global_z_off + l_off
        ea = re.search(r'EA="(\d+):', bc); geo_id = ea.group(1) if ea else None
        if geo_id and geo_id in geos:
            t_cnc = tool_map.get(tno, "T2")
            milling_data.append({'tno': tno, 't_cnc': t_cnc, 'za': round(za, 3), 'pts': [p[:] for p in geos[geo_id]]})

    if rotate_90:
        for d in raw_drills: d['x'], d['y'] = -d['y'], d['x']
        for g in milling_data:
            for p in g['pts']: p[0], p[1] = -p[1], p[0]

    mx, my = (0,0)
    if zero_nesting:
        coords = [(d['x'], d['y']) for d in raw_drills] + [(p[0], p[1]) for g in milling_data for p in g['pts']]
        if coords: mx, my = min(x for x,y in coords), min(y for x,y in coords)
    for d in raw_drills: d['x'] -= mx; d['y'] -= my
    for g in milling_data:
        for p in g['pts']: p[0] -= mx; p[1] -= my

    nc = ["%", "(NC DARWISH 42.60)", "G90 G54 G21"]; timeline = []; out_idx = 1
    
    # 1. קדחים (למעט T2)
    dr_tools = {}
    for d in raw_drills: 
        if d['t'] != "T2": dr_tools.setdefault(d['t'], []).append(d)
    
    for t_id in sorted(dr_tools.keys()):
        nc.append(f"M6 {t_id}"); timeline.append({"op": out_idx, "tool": t_id, "type": "Drill"})
        for d in optimize_path(dr_tools[t_id]):
            d['disp_num'] = out_idx
            nc.extend([f"G0 X{d['x']:.3f} Y{d['y']:.3f}", f"G1 Z{d['z']:.3f} F1000", f"G0 Z{thickness+20}"])
        out_idx += 1

    # 2. כרסומים (למעט T2)
    mill_by_t = {}
    for item in milling_data:
        if item['t_cnc'] != "T2": mill_by_t.setdefault(item['t_cnc'], []).append(item)
    
    for t_id in sorted(mill_by_t.keys()):
        nc.append(f"M6 {t_id}")
        active_passes = custom_passes_dict.get(t_id, [])
        for item in mill_by_t[t_id]:
            item['disp_num'] = out_idx
            item['active_passes'] = active_passes if active_passes else [item['za']]
            timeline.append({"op": out_idx, "tool": t_id, "type": "Mill"})
            for z in item['active_passes']:
                nc.append(f"(PASS Z={z})")
                nc.append(f"G0 X{item['pts'][0][0]:.3f} Y{item['pts'][0][1]:.3f}")
                nc.append(f"G1 Z{z:.3f} F2000")
                for p in item['pts'][1:]: nc.append(f"G1 X{p[0]:.3f} Y{p[1]:.3f} F3000")
                nc.append(f"G0 Z{thickness+20}")
            out_idx += 1

    # 3. סגירה מוחלטת עם T2 (חוק ברזל)
    all_t2_ops = [d for d in raw_drills if d['t'] == "T2"]
    all_t2_mills = [m for m in milling_data if m['t_cnc'] == "T2"]
    
    if all_t2_ops or all_t2_mills:
        nc.append("M6 T2")
        active_passes = custom_passes_dict.get("T2", [])
        if all_t2_ops:
            timeline.append({"op": out_idx, "tool": "T2", "type": "Drill/Contour"})
            for d in optimize_path(all_t2_ops):
                d['disp_num'] = out_idx
                nc.extend([f"G0 X{d['x']:.3f} Y{d['y']:.3f}", f"G1 Z{d['z']:.3f} F1000", f"G0 Z{thickness+20}"])
        if all_t2_mills:
            for item in all_t2_mills:
                item['disp_num'] = out_idx
                item['active_passes'] = active_passes if active_passes else [item['za']]
                timeline.append({"op": out_idx, "tool": "T2", "type": "Mill/Contour"})
                for z in item['active_passes']:
                    nc.append(f"(PASS Z={z})")
                    nc.append(f"G0 X{item['pts'][0][0]:.3f} Y{item['pts'][0][1]:.3f}")
                    nc.append(f"G1 Z{z:.3f} F2000")
                    for p in item['pts'][1:]: nc.append(f"G1 X{p[0]:.3f} Y{p[1]:.3f} F3000")
                    nc.append(f"G0 Z{thickness+20}")
        out_idx += 1

    nc.append("M30\n%")
    return "\n".join(nc), raw_drills, milling_data, thickness, timeline

def plot_v42_6(drills, milling_list, thickness, cfg):
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=3050, y1=1300, line=dict(color="black", width=2), layer="below")
    for g in milling_list:
        t_info = next((t for t in cfg['tools'] if t['T_CNC'] == g['t_cnc']), {"צבע": "red", "תיאור": "כרסום"})
        xp, yp = zip(*g['pts'])
        p_list = sorted(g.get('active_passes', [g['za']]), reverse=True)
        h_text = "".join([f"<br>פסיעה {'ראשונה' if i==0 else 'שנייה' if i==1 else f'מספר {i+1}'} - {round(thickness - p, 2)} מילימטר (מהחלק העליון)" for i, p in enumerate(p_list)])
        fig.add_trace(go.Scatter(x=xp, y=yp, mode='lines', line=dict(color=t_info['צבע'], width=2),
            hovertemplate=f"<b>פעולה {g.get('disp_num', '?')}</b><br>כלי: {g['t_cnc']} ({t_info['תיאור']}){h_text}<extra></extra>"))
    for d in drills:
        fig.add_trace(go.Scatter(x=[d['x']], y=[d['y']], mode='markers', marker=dict(size=8, color='blue'),
            hovertemplate=f"קידוח {d['t']}<br>Z סופי: {d['z']:.2f} מילימטר<extra></extra>"))
    fig.update_layout(width=1000, height=500, dragmode='pan', xaxis=dict(range=[0, 3050]), yaxis=dict(range=[0, 1300]))
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

# --- UI ---
st.sidebar.title("🛠️ Darwish PRO 42.60")
cfg = st.session_state.profiles["אבי"]
nest = st.sidebar.checkbox("Nesting (יישור ל-0,0)", value=False)
rot = st.sidebar.checkbox("סובב 90 מעלות", value=False)
gz_off = st.sidebar.slider("כיול Z גלובלי (מילימטר)", -3.0, 3.0, 0.0, 0.1)

uploaded = st.file_uploader("טען קבצי MPR", accept_multiple_files=True)
if uploaded:
    for f in uploaded:
        m_text = f.getvalue().decode('utf-8', errors='ignore')
        t_ids = sorted(list(set(re.findall(r'(?:DU|TNO)="([^"]*)"', m_text))))
        
        with st.sidebar.expander(f"⚙️ הגדרות: {f.name}", expanded=True):
            t_map = {}; l_offsets = {}
            for tid in t_ids:
                col1, col2 = st.columns([2, 1])
                # מיפוי קשיח (Ground Truth)
                idx = 6 if tid=="130" else 3 if tid=="128" else 2 if tid=="158" else 0 if tid=="137" else 9 if tid in ["8","8.0000","BV8"] else 1
                t_map[tid] = col1.selectbox(f"MPR {tid}:", [t['T_CNC'] for t in cfg['tools']], index=min(idx, 11), key=f"t_{f.name}_{tid}")
                l_offsets[tid] = col2.number_input("Z+/-", value=0.0, step=0.1, key=f"z_{f.name}_{tid}")
            
            _, _, m_list, thick, _ = convert_logic_v42_6(m_text, rot, nest, gz_off, t_map, l_offsets, {})
            st.markdown("---")
            st.markdown("### 📏 ניהול פסיעות (לפי כלי)")
            
            by_tool = {}
            for item in m_list: by_tool.setdefault(item['t_cnc'], set()).add(item['za'])
            
            c_passes_dict = {}
            s_tools = [t for t in sorted(by_tool.keys()) if t != "T2"]
            if "T2" in by_tool: s_tools.append("T2")

            for t_id in s_tools:
                t_info = next((t for t in cfg['tools'] if t['T_CNC'] == t_id), {"תיאור": "כרסום"})
                st.markdown(f"#### **כלי {t_id} - {t_info['תיאור']}**")
                p_depths = sorted(list(by_tool[t_id]), reverse=True)
                u_passes = []
                for i, p_val in enumerate(p_depths):
                    label = f"פסיעה {'ראשונה' if i==0 else 'שנייה' if i==1 else f'פסיעה {i+1}'}:"
                    u_passes.append(st.number_input(label, -5.0, 30.0, p_val, 0.1, key=f"p_{f.name}_{t_id}_{i}"))
                
                if st.checkbox(f"הוסף פסיעה", key=f"add_{f.name}_{t_id}"):
                    last_z = u_passes[-1] if u_passes else 0.0
                    u_passes.append(st.number_input("עומק פסיעה חדשה (Z):", -5.0, 30.0, last_z, 0.1, key=f"new_{f.name}_{t_id}"))
                
                c_passes_dict[t_id] = u_passes
                st.markdown("---")

        nc, drls, mills, thick, tm = convert_logic_v42_6(m_text, rot, nest, gz_off, t_map, l_offsets, c_passes_dict)
        st.subheader(f"📋 Timeline: {f.name}")
        t_cols = st.columns(min(len(tm), 10)); 
        for i, s in enumerate(tm[:10]): t_cols[i].info(f"#{s['op']}\n{s['tool']}")
        plot_v42_6(drls, mills, thick, cfg)
        st.download_button(f"📥 הורד NC", nc, f.name.replace(".mpr", ".nc"))
