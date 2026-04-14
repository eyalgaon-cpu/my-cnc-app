import streamlit as st
import re, math
import plotly.graph_objects as go

# Darwish PRO 44.32 - Multi-Reference Z Engine & Syntax Guard
st.set_page_config(page_title="Darwish PRO 44.32", layout="wide")

if 'profiles' not in st.session_state:
    st.session_state.profiles = {"אבי": {"tools": [
        {"T_CNC": "T1", "קוטר": 40.0, "תיאור": "כרסום 40 מילימטר", "צבע": "brown"},
        {"T_CNC": "T2", "קוטר": 6.0, "תיאור": "כרסום 6 מילימטר", "צבע": "red"},
        {"T_CNC": "T3", "קוטר": 8.0, "תיאור": "כרסום 8 מילימטר", "צבע": "green"},
        {"T_CNC": "T4", "קוטר": 12.0, "תיאור": "כרסום 12 מילימטר", "צבע": "purple"},
        {"T_CNC": "T8", "קוטר": 19.0, "תיאור": "כרסום 20 מילימטר", "צבע": "darkblue"},
        {"T_CNC": "T11", "קוטר": 3.0, "תיאור": "כרסום 3 מילימטר", "צבע": "pink"},
        {"T_CNC": "T13", "קוטר": 0.2, "תיאור": "כרסום 90/45 מעלות", "צבע": "gold"},
        {"T_CNC": "T6", "קוטר": 35.0, "תיאור": "מקדח 35 מילימטר", "צבע": "orange"},
        {"T_CNC": "T49", "קוטר": 15.0, "תיאור": "מקדח 15 מילימטר", "צבע": "yellow"},
        {"T_CNC": "T47", "קוטר": 8.0, "תיאור": "מקדח 8 מילימטר", "צבע": "darkgreen"},
        {"T_CNC": "T44", "קוטר": 5.0, "תיאור": "מקדח 5 מילימטר רגיל", "צבע": "gray"},
        {"T_CNC": "T45", "קוטר": 5.0, "תיאור": "מקדח 5 מילימטר עובר", "צבע": "white"}
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

def convert_logic_v44_32(mpr_text, rotate_90, ax, ay, gz_off, t_map, l_offs, cp_dict, user_tool_order):
    thick = get_f('t', mpr_text, 19.0)
    raw_drills, milling_data, geos = [], [], {}
    
    parts = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(parts), 2):
        pts = []
        for elem in re.split(r'\$E\d+', parts[i+1]):
            x_m = re.search(r'X=([\d.-]+)', elem); y_m = re.search(r'Y=([\d.-]+)', elem)
            if x_m and y_m: pts.append([float(x_m.group(1)), float(y_m.group(1))])
        if pts: geos[parts[i]] = pts

    # קידוחים (102 - ייחוס TI)
    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1); ti = get_f('TI', b)
        xa, ya = [get_f(k, b) for k in ['XA', 'YA']]
        an, ab, wi = int(get_f('AN', b, 1.0)), get_f('AB', b, 0.0), math.radians(get_f('WI', b, 0.0))
        t_mpr = re.search(r'DU="([^"]*)"', b).group(1) if re.search(r'DU="([^"]*)"', b) else "5"
        fz = (thick - ti) + gz_off + l_offs.get(t_mpr, 0.0)
        t_cnc = t_map.get(t_mpr, "T44")
        if t_mpr.replace("BV","") in ["5", "5.0"]: t_cnc = "T45" if fz <= 0.2 else "T44"
        for i in range(an): raw_drills.append({'x': xa+(i*ab*math.cos(wi)), 'y': ya+(i*ab*math.sin(wi)), 'z': fz, 't': t_cnc, 'depth': ti})

    # כרסומים (105/130 ייחוס ZA | 181 ייחוס TI)
    for m_match in re.finditer(r'<(105|130|181)(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        bc, tag = m_match.group(2), m_match.group(1)
        t_mpr = re.search(r'(?:TNO|T_)="([^"]*)"', bc).group(1) if re.search(r'(?:TNO|T_)="([^"]*)"', bc) else "142"
        
        # לוגיקת הפיצול של אייל:
        if tag == '181': # Pocket
            ti_val = get_f('TI', bc)
            za_calc = (thick - ti_val)
            depth_label = ti_val
        else: # Milling 105/130
            za_calc = get_f('ZA', bc)
            depth_label = thick - za_calc

        za = za_calc + gz_off + l_offs.get(t_mpr, 0.0)
        eid = re.search(r'EA="(\d+):', bc).group(1) if re.search(r'EA="(\d+):', bc) else None
        if eid in geos:
            mt = 'Pocket' if tag=='181' else ('Internal' if za > 0.5 else 'Final')
            milling_data.append({
                't_mpr': t_mpr, 't_cnc': t_map.get(t_mpr, "T2"), 
                'za': round(za, 3), 'pts': [p[:] for p in geos[eid]], 
                'rk': re.search(r'RK="([^"]*)"', bc).group(1) if re.search(r'RK="([^"]*)"', bc) else "NOWRK", 
                'mtype': mt, 'depth_orig': depth_label, 'za_mpr': za_calc
            })

    # עוגן וסיבוב
    all_x = [d['x'] for d in raw_drills] + [p[0] for m in milling_data for p in m['pts']]
    all_y = [d['y'] for d in raw_drills] + [p[1] for m in milling_data for p in m['pts']]
    ox, oy = (min(all_x) if all_x else 0.0, min(all_y) if all_y else 0.0)
    for d in raw_drills: d['x'] -= ox; d['y'] -= oy
    for g in milling_data:
        for p in g['pts']: p[0] -= ox; p[1] -= oy
    
    if rotate_90:
        for d in raw_drills: d['x'], d['y'] = -d['y'], d['x']
        for g in milling_data:
            for p in g['pts']: p[0], p[1] = -p[1], p[0]
        cur_x = [d['x'] for d in raw_drills] + [p[0] for m in milling_data for p in m['pts']]
        cur_y = [d['y'] for d in raw_drills] + [p[1] for m in milling_data for p in m['pts']]
        cx, cy = (min(cur_x) if cur_x else 0, min(cur_y) if cur_y else 0)
        for d in raw_drills: d['x'] += (ax - cx); d['y'] += (ay - cy)
        for g in milling_data:
            for p in g['pts']: p[0] += (ax - cx); p[1] += (ay - cy)
    else:
        for d in raw_drills: d['x'] += ax; d['y'] += ay
        for g in milling_data:
            for p in g['pts']: p[0] += ax; p[1] += ay

    # הפקת NC
    nc, timeline = ["%", f"(NC DARWISH 44.32 - Z-REF SPLIT)", "G90 G54 G21"], []
    final_execution_list = list(user_tool_order) if user_tool_order else []
    if any(m['mtype'] == 'Final' for m in milling_data) and "T2_Final" not in final_execution_list:
        final_execution_list.append("T2_Final")

    for t_key in final_execution_list:
        t_id = t_key.replace("_Final", "")
        mt_filter = 'Final' if "Final" in t_key else ('Internal' if t_id == "T2" else None)
        
        # 1. קידוחים
        if not mt_filter:
            ds = optimize_sequence([d for d in raw_drills if d['t'] == t_id])
            if ds:
                nc.append(f"M6 {t_id} (DRILLING)")
                for d in ds: nc.extend([f"G0 X{d['x']:.3f} Y{d['y']:.3f}", f"G1 Z{d['z']:.3f} F1000", "G0 Z36.0"])
                timeline.append({"tool": t_id, "type": "קידוח"})

        # 2. כרסומים
        ms_all = [m for m in milling_data if m['t_cnc'] == t_id]
        if mt_filter: ms_all = [m for m in ms_all if m['mtype'] == mt_filter]
        elif t_id == "T2": ms_all = [m for m in ms_all if m['mtype'] != 'Final']
        
        if ms_all:
            type_label = ms_all[0]['mtype']
            nc.append(f"M6 {t_id} ({type_label})")
            seq = optimize_sequence(ms_all)
            
            # בניית פסיעות מבוססת עומק חדירה (מילימטר)
            part_passes = []
            for m in seq:
                pkey = f"{t_id}_{m['mtype']}_{m['depth_orig']}"
                ps = cp_dict.get(pkey, [m['za']])
                part_passes.append(ps)
                m['active_passes'] = ps
            
            max_p = max(len(p) for p in part_passes)
            for p_idx in range(max_p):
                nc.append(f"(GLOBAL PASS {p_idx+1})")
                for i, m in enumerate(seq):
                    if p_idx < len(part_passes[i]):
                        z = part_passes[i][p_idx]
                        rk_c = "G41 " if m['rk'] == "WRKL" else "G42 " if m['rk'] == "WRKR" else ""
                        nc.append(f"G0 X{m['pts'][0][0]:.3f} Y{m['pts'][0][1]:.3f}")
                        nc.append(f"{rk_c}G1 Z{z:.3f} F2000")
                        for p in m['pts'][1:]:
                            nc.append(f"G1 X{p[0]:.3f} Y{p[1]:.3f} F3000")
                        nc.extend(["G40", "G0 Z36.0"])
            timeline.append({"tool": t_key, "type": type_label})

    nc.append("M30\n%")
    return "\n".join(nc), raw_drills, milling_data, thick, timeline, (ox, oy)

def plot_v44_32(drills, mills, thick, cfg, part_dims):
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=cfg['bed_x'], y1=cfg['bed_y'], line=dict(color="black", width=2), layer="below")
    fig.add_shape(type="rect", x0=0, y0=0, x1=part_dims[0], y1=part_dims[1], line=dict(color="blue", width=1, dash="dot"))
    for g in mills:
        xp, yp = zip(*g['pts'])
        ps = g.get('active_passes', [g['za']])
        h_info = "".join([f"<br>• עומק חדירה: {round(thick-p, 2) if p>0.5 else abs(round(p,2))} מילימטר" for p in ps])
        fig.add_trace(go.Scatter(x=xp, y=yp, mode='lines', name=g['t_cnc'], hovertemplate=f"<b>{g['t_cnc']} | {g['mtype']}</b>{h_info}<extra></extra>"))
    for d in drills:
        fig.add_trace(go.Scatter(x=[d['x']], y=[d['y']], mode='markers', name=f"קידוח {d['t']}", hovertemplate=f"קידוח {d['t']}<br>עומק חדירה: {round(d['depth'],2)} מילימטר<extra></extra>"))
    fig.update_layout(width=700, height=850, showlegend=False, dragmode='pan',
                      xaxis=dict(title="X מילימטר", range=[-50, 1350], gridcolor='lightgray', zeroline=True),
                      yaxis=dict(title="Y מילימטר", range=[-50, 3100], gridcolor='lightgray', zeroline=True))
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

# --- UI ---
st.sidebar.title("🛠️ Darwish PRO 44.32")
cfg = st.session_state.profiles["אבי"]
rot, gz_off = st.sidebar.checkbox("סובב 90 מעלות"), st.sidebar.slider("כיול Z (מילימטר)", -3.0, 3.0, 0.0, 0.1)

upl = st.file_uploader("טען MPR", accept_multiple_files=True)
if upl:
    for f in upl:
        txt = f.getvalue().decode('utf-8', errors='ignore')
        res_init = convert_logic_v44_32(txt, rot, 0, 0, 0, {}, {}, {}, [])
        ox_mpr, oy_mpr = res_init[5]; thick_mpr = res_init[3]
        
        with st.sidebar.expander(f"⚙️ {f.name}", expanded=True):
            ax = st.number_input("עוגן X (מילימטר)", value=ox_mpr, step=0.1, key=f"ax_{f.name}")
            ay = st.number_input("עוגן Y (מילימטר)", value=oy_mpr, step=0.1, key=f"ay_{f.name}")
            t_ids = sorted(list(set(re.findall(r'(?:TNO|T_|DU)="([^"]*)"', txt))))
            t_map, l_offs = {}, {}
            for tid in t_ids:
                col1, col2 = st.columns([2, 1])
                t_map[tid] = col1.selectbox(f"MPR {tid}:", [t['T_CNC'] for t in cfg['tools']], index=5 if "140" in tid else 1, key=f"tm_{f.name}_{tid}")
                l_offs[tid] = col2.number_input("Z+/-", value=0.0, step=0.1, key=f"zo_{f.name}_{tid}")
            
            res_ui = convert_logic_v44_32(txt, rot, ax, ay, gz_off, t_map, l_offs, {}, [])
            st.markdown("### 📏 פסיעות Global")
            groups, cp_dict = {}, {}
            for m in res_ui[2]: groups.setdefault((m['t_cnc'], m['mtype'], m['depth_orig']), []).append(m)
            for (t_id, mt, d_orig), mems in sorted(groups.items()):
                st.markdown(f"**כלי {t_id} | {mt}**")
                u_ps = [st.number_input(f"פסיעה (עומק חדירה {d_orig} מילימטר):", -5.0, 30.0, mems[0]['za'], 0.1, key=f"p_{f.name}_{t_id}_{mt}_{d_orig}")]
                if st.checkbox("הוסף פסיעה", key=f"add_{f.name}_{t_id}_{mt}_{d_orig}"):
                    u_ps.append(st.number_input("נוסף:", -5.0, 30.0, u_ps[-1], 0.1, key=f"n_{f.name}_{t_id}_{mt}_{d_orig}"))
                cp_dict[f"{t_id}_{mt}_{d_orig}"] = u_ps
            
            st.markdown("### 🔄 סדר ביצוע")
            avail_t = sorted(list(set([m['t_cnc'] for m in res_ui[2] if m['mtype'] != 'Final'] + [d['t'] for d in res_ui[1]])))
            t_order_user = st.multiselect("קבע סדר כלים:", options=avail_t, default=avail_t, key=f"ord_{f.name}")

        nc, drls, mills, thick, tm, _ = convert_logic_v44_32(txt, rot, ax, ay, gz_off, t_map, l_offs, cp_dict, t_order_user)
        st.subheader(f"📋 Timeline: {f.name}")
        t_cols = st.columns(len(tm) if tm else 1)
        for i, s in enumerate(tm): t_cols[i].info(f"{s['tool']}\n({s['type']})")
        p_l = get_f('l', txt); p_w = get_f('w', txt)
        plot_v44_32(drls, mills, thick, cfg, (p_l, p_w) if not rot else (p_w, p_l))
        st.download_button(f"📥 הורד NC", nc, f.name.replace(".mpr", ".nc"))
