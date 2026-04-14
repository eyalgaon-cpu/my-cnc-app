import streamlit as st
import re, math
import plotly.graph_objects as go

# Darwish PRO 44.00 - Global Pass (Opt 1) & Full Path Optimization
st.set_page_config(page_title="Darwish PRO 44.00", layout="wide")

if 'profiles' not in st.session_state:
    st.session_state.profiles = {"אבי": {"tools": [
        {"T_CNC": "T1", "קוטר": 40.0, "תיאור": "כרסום 40 מילימטר", "צבע": "brown"},
        {"T_CNC": "T2", "קוטר": 6.0, "תיאור": "כרסום 6 מילימטר (קונטור)", "צבע": "red"},
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
    res, curr = [], {'x': 0, 'y': 0}
    rem = items[:]
    while rem:
        nxt = min(rem, key=lambda i: get_dist(curr, {'x': i['pts'][0][0], 'y': i['pts'][0][1]} if 'pts' in i else i))
        res.append(nxt)
        rem.remove(nxt)
        curr = {'x': nxt['pts'][-1][0], 'y': nxt['pts'][-1][1]} if 'pts' in nxt else nxt
    return res

def get_f(key, block, default=0.0):
    m = re.search(f'{key}="([^"]*)"', block)
    return float(m.group(1)) if m else default

def convert_logic_v44_0(mpr_text, rotate_90, ax, ay, gz_off, t_map, l_offs, cp_dict):
    thick = get_f('t', mpr_text, 19.0)
    raw_drills, milling_data, geos = [], [], {}
    
    parts = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(parts), 2):
        pts = []
        for elem in re.split(r'\$E\d+', parts[i+1]):
            x_m = re.search(r'X=([\d.-]+)', elem); y_m = re.search(r'Y=([\d.-]+)', elem)
            if x_m and y_m: pts.append([float(x_m.group(1)), float(y_m.group(1))])
        if pts: geos[parts[i]] = pts

    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1); xa, ya, ti = [get_f(k, b) for k in ['XA', 'YA', 'TI']]
        an, ab, wi = int(get_f('AN', b, 1.0)), get_f('AB', b, 0.0), math.radians(get_f('WI', b, 0.0))
        t_mpr = re.search(r'DU="([^"]*)"', b).group(1) if re.search(r'DU="([^"]*)"', b) else "5"
        fz = (thick - ti) + gz_off + l_offs.get(t_mpr, 0.0)
        t_cnc = t_map.get(t_mpr, "T44")
        if t_mpr.replace("BV","") in ["5", "5.0"]: t_cnc = "T45" if fz <= 0.2 else "T44"
        for i in range(an): raw_drills.append({'x': xa+(i*ab*math.cos(wi)), 'y': ya+(i*ab*math.sin(wi)), 'z': fz, 't': t_cnc})

    op_idx = 0
    for m in re.finditer(r'<(105|130|181)(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        bc, tag = m.group(2), m.group(1)
        t_id_m = re.search(r'(?:TNO|T_)="([^"]*)"', bc)
        t_mpr = t_id_m.group(1) if t_id_m else ("140" if tag == '181' else "142")
        za_orig = get_f('TI', bc) if tag == '181' else get_f('ZA', bc)
        za = za_orig + gz_off + l_offs.get(t_mpr, 0.0)
        ea = re.search(r'EA="(\d+):', bc); geo_id = ea.group(1) if ea else None
        if geo_id and geo_id in geos:
            mtype = 'Pocket' if tag=='181' else ('Internal' if za > 0.5 else 'Final')
            milling_data.append({'op_id': op_idx, 't_mpr': t_mpr, 't_cnc': t_map.get(t_mpr, "T2"), 'za': round(za, 3), 'pts': [p[:] for p in geos[geo_id]], 'rk': re.search(r'RK="([^"]*)"', bc).group(1) if re.search(r'RK="([^"]*)"', bc) else "NOWRK", 'mtype': mtype, 'za_orig': za_orig})
            op_idx += 1

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

    # הפקת NC - Global Pass + Option 1
    nc, timeline, out_idx = ["%", "(NC DARWISH 44.00)", "G90 G54 G21"], [], 1
    used_tools = sorted(list(set([d['t'] for d in raw_drills] + [m['t_cnc'] for m in milling_data])))
    
    # מיון כלים (T2 אחרון)
    tool_order = [t for t in used_tools if t != "T2"] + (["T2"] if "T2" in used_tools else [])
    
    for t_id in tool_order:
        nc.append(f"M6 {t_id}")
        # קידוחים (אופטימיזציית שכן קרוב)
        ds = optimize_sequence([d for d in raw_drills if d['t'] == t_id])
        if ds:
            timeline.append({"op": out_idx, "tool": t_id, "type": "קידוח"})
            for d in ds: nc.extend([f"G0 X{d['x']:.3f} Y{d['y']:.3f}", f"G1 Z{d['z']:.3f} F1000", "G0 Z36.0"])
            out_idx += 1
            
        # כרסומים - לוגיקת Global Pass
        ms_all = [m for m in milling_data if m['t_cnc'] == t_id]
        if ms_all:
            # שלב 1: אופטימיזציית סדר החלקים (Sequence)
            seq = optimize_sequence(ms_all)
            # שלב 2: זיהוי עומקים (Passes)
            all_passes_for_tool = {}
            for m in seq:
                pkey = f"{t_id}_{m['mtype']}_{m['za_orig']}"
                all_passes_for_tool[m['op_id']] = cp_dict.get(pkey, [m['za']])
                m['active_passes'] = all_passes_for_tool[m['op_id']]

            max_p = max([len(v) for v in all_passes_for_tool.values()])
            
            # שלב 3: לולאת Global Pass (אפשרות 1: סדר קבוע)
            for p_idx in range(max_p):
                nc.append(f"(GLOBAL PASS {p_idx+1})")
                for m in seq:
                    m_passes = all_passes_for_tool[m['op_id']]
                    if p_idx < len(m_passes):
                        z = m_passes[p_idx]
                        rk_c = "G41 " if m['rk'] == "WRKL" else "G42 " if m['rk'] == "WRKR" else ""
                        nc.extend([f"(OP {m['op_id']} Z={z})", f"{rk_c}G0 X{m['pts'][0][0]:.3f} Y{m['pts'][0][1]:.3f}", f"G1 Z{z:.3f} F2000"])
                        for p in m['pts'][1:]: nc.append(f"G1 X{p[0]:.3f} Y{p[1]:.3f} F3000")
                        nc.extend(["G40", "G0 Z36.0"])
            
            # הוספה ל-Timeline (לפי סוגים)
            for mt in sorted(list(set(m['mtype'] for m in ms_all))):
                timeline.append({"op": out_idx, "tool": t_id, "type": mt})
                out_idx += 1

    nc.append("M30\n%")
    return "\n".join(nc), raw_drills, milling_data, thick, timeline, (ox, oy)

def plot_v44_0(drills, milling_list, thick, cfg, part_dims):
    fig = go.Figure()
    # משטח מכונה
    fig.add_shape(type="rect", x0=0, y0=0, x1=cfg['bed_x'], y1=cfg['bed_y'], line=dict(color="rgba(100,100,100,0.5)", width=2, dash="dash"), layer="below")
    # פלטה
    fig.add_shape(type="rect", x0=0, y0=0, x1=part_dims[0] if part_dims else 0, y1=part_dims[1] if part_dims else 0, line=dict(color="black", width=2), fillcolor="rgba(0,0,0,0.05)")
    
    for g in milling_list:
        xp, yp = zip(*g['pts'])
        ps = g.get('active_passes', [g['za']])
        h_info = "".join([f"<br>• פסיעה: {round(thick-p, 2) if p>0.5 else abs(round(p,2))} מילימטר" for p in ps])
        fig.add_trace(go.Scatter(x=xp, y=yp, mode='lines', line=dict(width=2), name=f"{g['t_cnc']}", 
                                 hovertemplate=f"<b>{g['t_cnc']} | {g['mtype']}</b>{h_info}<extra></extra>"))
    
    fig.update_layout(width=700, height=900, dragmode='pan', showlegend=False, 
                      xaxis=dict(title="X מילימטר", range=[-100, 1400], gridcolor='lightgray', zeroline=True), 
                      yaxis=dict(title="Y מילימטר", range=[-100, 3150], gridcolor='lightgray', zeroline=True))
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

# --- UI ---
st.sidebar.title("🛠️ Darwish PRO 44.00")
cfg = st.session_state.profiles["אבי"]
rot, gz_off = st.sidebar.checkbox("סובב 90 מעלות"), st.sidebar.slider("כיול Z", -3.0, 3.0, 0.0, 0.1)

uploaded = st.file_uploader("טען MPR", accept_multiple_files=True)
if uploaded:
    for f in uploaded:
        txt = f.getvalue().decode('utf-8', errors='ignore')
        # סריקה ראשונית לעוגן
        temp = convert_logic_v44_0(txt, rot, 0, 0, 0, {}, {}, {})
        ox, oy = temp[5]; thick_mpr = temp[3]
        
        with st.sidebar.expander(f"⚙️ {f.name}", expanded=True):
            ax, ay = st.slider("עוגן X", 0.0, 500.0, ox, 0.5, key=f"x_{f.name}"), st.slider("עוגן Y", 0.0, 500.0, oy, 0.5, key=f"y_{f.name}")
            t_ids = sorted(list(set(re.findall(r'(?:TNO|T_|DU)="([^"]*)"', txt))))
            t_map, l_offs = {}, {}
            for tid in t_ids:
                col1, col2 = st.columns([2, 1])
                try:
                    v = float(tid.replace("BV",""))
                    idx = 5 if v==140 else 1 # T11 (3mm) or Default
                except: idx = 1
                t_map[tid] = col1.selectbox(f"MPR {tid}:", [t['T_CNC'] for t in cfg['tools']], index=idx, key=f"t_{f.name}_{tid}")
                l_offs[tid] = col2.number_input("Z+/-", value=0.0, step=0.1, key=f"z_{f.name}_{tid}")
            
            # איחוד פסיעות בסידבר
            res = convert_logic_v44_0(txt, rot, ax, ay, gz_off, t_map, l_offs, {})
            groups = {}
            for m in res[2]:
                groups.setdefault((m['t_cnc'], m['mtype'], m['za_orig']), []).append(m)
            
            cp_dict = {}
            st.markdown("### 📏 ניהול פסיעות (Global)")
            for (t_id, mt, za_o), members in sorted(groups.items()):
                st.markdown(f"**כלי {t_id} | {mt}**")
                u_ps = []
                label = f"עומק {round(thick_mpr-za_o,1)}" if za_o > 0.5 else f"חדירה {abs(round(za_o,1))}"
                u_ps.append(st.number_input(f"פסיעה מקורית ({label}):", -5.0, 30.0, za_o, 0.1, key=f"p_{f.name}_{t_id}_{mt}_{za_o}"))
                if st.checkbox(f"הוסף פסיעה לכל הקבוצה", key=f"a_{f.name}_{t_id}_{mt}_{za_o}"):
                    u_ps.append(st.number_input("נוסף:", -5.0, 30.0, u_ps[-1], 0.1, key=f"n_{f.name}_{t_id}_{mt}_{za_o}"))
                cp_dict[f"{t_id}_{mt}_{za_o}"] = u_ps
        
        nc, drls, mills, thick, tm, _ = convert_logic_v44_0(txt, rot, ax, ay, gz_off, t_map, l_offs, cp_dict)
        st.subheader(f"📋 Timeline: {f.name}")
        t_cols = st.columns(len(tm))
        for i, s in enumerate(tm): t_cols[i].info(f"#{s['op']}\n{s['tool']}\n({s['type']})")
        plot_v44_0(drls, mills, thick, cfg, (get_f('l', txt), get_f('w', txt)) if not rot else (get_f('w', txt), get_f('l', txt)))
        st.download_button(f"📥 הורד NC", nc, f.name.replace(".mpr", ".nc"))
