import streamlit as st
import re, math
import plotly.graph_objects as go

# Darwish PRO 44.40 - Stable Engine & Scroll Zoom Fix
st.set_page_config(page_title="Darwish PRO 44.40", layout="wide")

# טבלת מיפוי קשיחה (מבוסס Tool_Mapping_Final_V2)
TOOL_MAP_CONFIG = {
    "130": "T13", "137": "T1", "128": "T4", "158": "T3",
    "142": "T2", "140": "T11", "147": "T8",
    "BV35": "T6", "BV15": "T49", "BV8": "T47", "BV5": "T44"
}

if 'profiles' not in st.session_state:
    st.session_state.profiles = {"אבי": {"tools": [
        {"T_CNC": "T1", "קוטר": 40.0, "תיאור": "כרסום 40 מילימטר"},
        {"T_CNC": "T2", "קוטר": 6.0, "תיאור": "כרסום 6 מילימטר"},
        {"T_CNC": "T3", "קוטר": 8.0, "תיאור": "כרסום 8 מילימטר"},
        {"T_CNC": "T4", "קוטר": 12.0, "תיאור": "כרסום 12 מילימטר"},
        {"T_CNC": "T8", "קוטר": 19.0, "תיאור": "כרסום 20 מילימטר"},
        {"T_CNC": "T11", "קוטר": 3.0, "תיאור": "כרסום 3 מילימטר"},
        {"T_CNC": "T13", "קוטר": 0.2, "תיאור": "כרסום 90/45 מעלות"},
        {"T_CNC": "T6", "קוטר": 35.0, "תיאור": "מקדח 35 מילימטר"},
        {"T_CNC": "T49", "קוטר": 15.0, "תיאור": "מקדח 15 מילימטר"},
        {"T_CNC": "T47", "קוטר": 8.0, "תיאור": "מקדח 8 מילימטר"},
        {"T_CNC": "T44", "קוטר": 5.0, "תיאור": "מקדח 5 מילימטר רגיל"},
        {"T_CNC": "T45", "קוטר": 5.0, "תיאור": "מקדח 5 מילימטר עובר"}
    ], "bed_x": 1300, "bed_y": 3050}}

def get_dist(p1, p2): return math.sqrt((p1['x'] - p2['x'])**2 + (p1['y'] - p2['y'])**2)

def optimize_sequence(items):
    if not items: return []
    res, curr, rem = [], {'x': 0, 'y': 0}, items[:]
    while rem:
        nxt = min(rem, key=lambda i: get_dist(curr, {'x': i['pts'][0][0], 'y': i['pts'][0][1]} if 'pts' in i else i))
        res.append(nxt); rem.remove(nxt)
        curr = {'x': nxt['pts'][-1][0], 'y': nxt['pts'][-1][1]} if 'pts' in nxt else nxt
    return res

def get_f(key, block, default=0.0):
    m = re.search(f'{key}="([^"]*)"', block)
    return float(m.group(1)) if m else default

def convert_logic_v44_40(mpr_text, rotate_90, ax, ay, gz_off, t_map, l_offs, cp_dict, user_tool_order):
    thick = get_f('t', mpr_text, 19.0)
    raw_drills, milling_data, geos = [], [], {}
    
    parts = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(parts), 2):
        pts = []
        for elem in re.split(r'\$E\d+', parts[i+1]):
            x_m = re.search(r'X=([\d.-]+)', elem); y_m = re.search(r'Y=([\d.-]+)', elem)
            if x_m and y_m: pts.append([float(x_m.group(1)), float(y_m.group(1))])
        if pts: geos[parts[i]] = pts

    # קידוחים
    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1); ti = get_f('TI', b)
        fz = (thick - ti) + gz_off + l_offs.get(re.search(r'DU="([^"]*)"', b).group(1) if re.search(r'DU="([^"]*)"', b) else "5", 0.0)
        t_mpr = re.search(r'DU="([^"]*)"', b).group(1) if re.search(r'DU="([^"]*)"', b) else "5"
        t_cnc = t_map.get(t_mpr, "T44")
        if "5" in t_mpr: t_cnc = "T45" if fz <= 0.2 else "T44"
        raw_drills.append({'x': get_f('XA', b), 'y': get_f('YA', b), 'z': round(fz,3), 't': t_cnc, 'depth': ti})

    # כרסומים
    for op_idx, m_match in enumerate(re.finditer(r'<(105|130|181)(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL)):
        bc, tag = m_match.group(2), m_match.group(1)
        t_mpr = re.search(r'(?:TNO|T_)="([^"]*)"', bc).group(1) if re.search(r'(?:TNO|T_)="([^"]*)"', bc) else "142"
        
        if tag == '181': # Pocket
            ti_val = get_f('TI', bc); za_calc = (thick - ti_val); d_label = ti_val
        else: # Milling
            za_calc = get_f('ZA', bc); d_label = thick - za_calc

        za = za_calc + gz_off + l_offs.get(t_mpr, 0.0)
        eid = re.search(r'EA="(\d+):', bc).group(1) if re.search(r'EA="(\d+):', bc) else None
        if eid in geos:
            mt = 'Pocket' if tag=='181' else ('Internal' if za > 0.5 else 'Final')
            milling_data.append({
                'op_id': op_idx, 't_mpr': t_mpr, 't_cnc': t_map.get(t_mpr, "T2"), 
                'za': round(za, 3), 'pts': [p[:] for p in geos[eid]], 
                'rk': re.search(r'RK="([^"]*)"', bc).group(1) if re.search(r'RK="([^"]*)"', bc) else "NOWRK", 
                'mtype': mt, 'depth_orig': d_label
            })

    # עוגן
    all_x = [d['x'] for d in raw_drills] + [p[0] for m in milling_data for p in m['pts']]
    all_y = [d['y'] for d in raw_drills] + [p[1] for m in milling_data for p in m['pts']]
    ox, oy = (min(all_x) if all_x else 0.0, min(all_y) if all_y else 0.0)
    for d in raw_drills: d['x'] -= ox; d['y'] -= oy
    for g in milling_data:
        for p in g['pts']: p[0] -= ox; p[1] -= oy
    
    for d in raw_drills: d['x'] += ax; d['y'] += ay
    for g in milling_data:
        for p in g['pts']: p[0] += ax; p[1] += ay

    # הפקת NC
    nc, timeline = ["%", "(NC DARWISH 44.40 - FULL OPERATION STABILITY)", "G90 G54 G21"], []
    exec_list = list(user_tool_order) if user_tool_order else []
    if any(m['mtype'] == 'Final' for m in milling_data) and "T2_Final" not in exec_list:
        exec_list.append("T2_Final")

    for t_key in exec_list:
        t_id = t_key.replace("_Final", "")
        mt_f = 'Final' if "Final" in t_key else ('Internal' if t_id == "T2" else None)
        
        # קידוחים
        ds = optimize_sequence([d for d in raw_drills if d['t'] == t_id])
        if ds and not mt_f:
            nc.append(f"M6 {t_id} (DRILLING)")
            for d in ds: nc.extend([f"G0 X{d['x']:.3f} Y{d['y']:.3f}", f"G1 Z{d['z']:.3f} F1000", "G0 Z36.0"])
            timeline.append({"tool": t_id, "type": "קידוח"})

        # כרסומים
        ms = [m for m in milling_data if m['t_cnc'] == t_id]
        if mt_f: ms = [m for m in ms if m['mtype'] == mt_f]
        elif t_id == "T2": ms = [m for m in ms if m['mtype'] != 'Final']
        
        if ms:
            nc.append(f"M6 {t_id} ({ms[0]['mtype']})")
            seq = optimize_sequence(ms)
            for m in seq:
                # שימוש ב-op_id להבטחת ייחודיות פסיעה לכל בלוק ב-MPR
                ps = cp_dict.get(f"{f.name}_{m['op_id']}", [m['za']])
                for z in ps:
                    rk = "G41 " if m['rk'] == "WRKL" else "G42 " if m['rk'] == "WRKR" else ""
                    nc.append(f"G0 X{m['pts'][0][0]:.3f} Y{m['pts'][0][1]:.3f}")
                    nc.append(f"{rk}G1 Z{z:.3f} F2000")
                    for p in m['pts'][1:]:
                        nc.append(f"G1 X{p[0]:.3f} Y{p[1]:.3f} F3000")
                    nc.extend(["G40", "G0 Z36.0"])
            timeline.append({"tool": t_key, "type": ms[0]['mtype']})

    nc.append("M30\n%")
    return "\n".join(nc), raw_drills, milling_data, thick, timeline, (ox, oy)

def plot_v44_40(drills, mills, thick, cfg, part_dims):
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=cfg['bed_x'], y1=cfg['bed_y'], line=dict(color="black", width=2), layer="below")
    fig.add_shape(type="rect", x0=0, y0=0, x1=part_dims[0], y1=part_dims[1], line=dict(color="blue", width=1, dash="dot"))
    for g in mills:
        xp, yp = zip(*g['pts'])
        fig.add_trace(go.Scatter(x=xp, y=yp, mode='lines', name=g['t_cnc'], hovertemplate=f"<b>{g['t_cnc']}</b><br>עומק חדירה: {g['depth_orig']} מילימטר<extra></extra>"))
    for d in drills:
        fig.add_trace(go.Scatter(x=[d['x']], y=[d['y']], mode='markers', name=d['t'], hovertemplate=f"<b>{d['t']}</b><br>עומק חדירה: {d['depth']} מילימטר<extra></extra>"))
    fig.update_layout(width=700, height=850, showlegend=False, dragmode='pan',
                      xaxis=dict(title="X מילימטר", gridcolor='lightgray'),
                      yaxis=dict(title="Y מילימטר", gridcolor='lightgray'))
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

# --- UI ---
st.sidebar.title("🛠️ Darwish PRO 44.40")
cfg = st.session_state.profiles["אבי"]
rot, gz_off = st.sidebar.checkbox("סובב 90 מעלות"), st.sidebar.slider("כיול Z (מילימטר)", -3.0, 3.0, 0.0, 0.1)

upl = st.file_uploader("טען MPR", accept_multiple_files=True)
if upl:
    for f in upl:
        txt = f.getvalue().decode('utf-8', errors='ignore')
        res_init = convert_logic_v44_40(txt, rot, 0, 0, 0, TOOL_MAP_CONFIG, {}, {}, [])
        with st.sidebar.expander(f"⚙️ {f.name}", expanded=True):
            ax = st.number_input("עוגן X (מילימטר)", value=res_init[5][0], step=0.1, key=f"ax_{f.name}")
            ay = st.number_input("עוגן Y (מילימטר)", value=res_init[5][1], step=0.1, key=f"ay_{f.name}")
            
            t_ids = sorted(list(set(re.findall(r'(?:TNO|T_|DU)="([^"]*)"', txt))))
            t_map, l_offs = {}, {}
            for tid in t_ids:
                col1, col2 = st.columns([2, 1])
                def_t = TOOL_MAP_CONFIG.get(tid.replace("BV",""), "T2")
                t_list = [t['T_CNC'] for t in cfg['tools']]
                t_map[tid] = col1.selectbox(f"MPR {tid}:", t_list, index=t_list.index(def_t) if def_t in t_list else 1, key=f"tm_{f.name}_{tid}")
                l_offs[tid] = col2.number_input("Z+/-", value=0.0, step=0.1, key=f"zo_{f.name}_{tid}")
            
            res_ui = convert_logic_v44_40(txt, rot, ax, ay, gz_off, t_map, l_offs, {}, [])
            cp_dict = {}
            st.markdown("### 📏 פסיעות עבודה")
            for m in res_ui[2]:
                st.markdown(f"**בלוק {m['op_id']} | כלי {m['t_cnc']} | חדירה {m['depth_orig']} מילימטר**")
                cp_dict[f"{f.name}_{m['op_id']}"] = [st.number_input("עומק NC (מילימטר):", value=m['za'], key=f"p_{f.name}_{m['op_id']}")]
            
            avail = sorted(list(set([m['t_cnc'] for m in res_ui[2] if m['mtype'] != 'Final'] + [d['t'] for d in res_ui[1]])))
            t_order = st.multiselect("סדר כלים:", options=avail, default=avail, key=f"ord_{f.name}")

        nc, drls, mills, thick, tm, _ = convert_logic_v44_40(txt, rot, ax, ay, gz_off, t_map, l_offs, cp_dict, t_order)
        st.subheader(f"📋 Timeline: {f.name}")
        t_cols = st.columns(len(tm) if tm else 1)
        for i, s in enumerate(tm): t_cols[i].info(f"{s['tool']}\n({s['type']})")
        p_l = get_f('l', txt); p_w = get_f('w', txt)
        plot_v44_40(drls, mills, thick, cfg, (p_l, p_w) if not rot else (p_w, p_l))
        st.download_button(f"📥 הורד NC", nc, f.name.replace(".mpr", ".nc"))
