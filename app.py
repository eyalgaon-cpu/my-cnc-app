import streamlit as st
import re, math
import plotly.graph_objects as go

# Darwish PRO 44.11 - Syntax Fix & Point Iteration Guard
st.set_page_config(page_title="Darwish PRO 44.11", layout="wide")

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
        nxt = min(rem, key=lambda i: get_dist(curr, {'x': i['pts'][0][0], 'y': i['pts'][0][1]}))
        res.append(nxt)
        rem.remove(nxt)
        curr = {'x': nxt['pts'][-1][0], 'y': nxt['pts'][-1][1]}
    return res

def get_f(key, block, default=0.0):
    m = re.search(f'{key}="([^"]*)"', block)
    return float(m.group(1)) if m else default

def convert_logic_v44_11(mpr_text, rotate_90, ax, ay, gz_off, t_map, l_offs, cp_dict, tool_order):
    thick = get_f('t', mpr_text, 19.0)
    milling_data, geos = [], {}
    
    parts = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(parts), 2):
        pts = []
        for elem in re.split(r'\$E\d+', parts[i+1]):
            x_m = re.search(r'X=([\d.-]+)', elem); y_m = re.search(r'Y=([\d.-]+)', elem)
            if x_m and y_m: pts.append([float(x_m.group(1)), float(y_m.group(1))])
        if pts: geos[parts[i]] = pts

    for m in re.finditer(r'<(105|130|181)(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        bc, tag = m.group(2), m.group(1)
        t_mpr = re.search(r'(?:TNO|T_)="([^"]*)"', bc).group(1) if re.search(r'(?:TNO|T_)="([^"]*)"', bc) else "142"
        za_orig = get_f('TI', bc) if tag == '181' else get_f('ZA', bc)
        za = za_orig + gz_off + l_offs.get(t_mpr, 0.0)
        eid = re.search(r'EA="(\d+):', bc).group(1) if re.search(r'EA="(\d+):', bc) else None
        if eid in geos:
            mtype = 'Pocket' if tag=='181' else ('Internal' if za > 0.5 else 'Final')
            milling_data.append({'t_mpr': t_mpr, 't_cnc': t_map.get(t_mpr, "T2"), 'za': round(za, 3), 'pts': [p[:] for p in geos[eid]], 'rk': re.search(r'RK="([^"]*)"', bc).group(1) if re.search(r'RK="([^"]*)"', bc) else "NOWRK", 'mtype': mtype, 'za_orig': za_orig})

    all_x = [p[0] for m in milling_data for p in m['pts']]
    all_y = [p[1] for m in milling_data for p in m['pts']]
    ox, oy = (min(all_x) if all_x else 0.0, min(all_y) if all_y else 0.0)
    for g in milling_data:
        for p in g['pts']: p[0] -= ox; p[1] -= oy
    
    if rotate_90:
        for g in milling_data:
            for p in g['pts']:
                p[0], p[1] = -p[1], p[0]
        cur_x = [p[0] for m in milling_data for p in m['pts']]
        cur_y = [p[1] for m in milling_data for p in m['pts']]
        cx, cy = (min(cur_x) if cur_x else 0, min(cur_y) if cur_y else 0)
        for g in milling_data:
            for p in g['pts']:
                p[0] += (ax - cx); p[1] += (ay - cy)
    else:
        for g in milling_data:
            for p in g['pts']:
                p[0] += ax; p[1] += ay

    nc, timeline = ["%", "(NC DARWISH 44.11)", "G90 G54 G21"], []
    final_tool_order = tool_order + (["T2_Final"] if any(m['mtype']=='Final' for m in milling_data) else [])
    
    for t_key in final_tool_order:
        t_id = t_key.replace("_Final", "")
        mt_filter = 'Final' if "Final" in t_key else ('Internal' if t_id == "T2" else None)
        ms_all = [m for m in milling_data if m['t_cnc'] == t_id]
        if mt_filter: ms_all = [m for m in ms_all if m['mtype'] == mt_filter]
        elif t_id != "T2": ms_all = [m for m in ms_all if m['mtype'] != 'Final']
        
        if not ms_all: continue
        nc.append(f"M6 {t_id}")
        seq = optimize_sequence(ms_all)
        part_passes = [cp_dict.get(f"{t_id}_{m['mtype']}_{m['za_orig']}", [m['za']]) for m in seq]
        for m, ps in zip(seq, part_passes): m['active_passes'] = ps
        
        max_p = max(len(p) for p in part_passes)
        for p_idx in range(max_p):
            nc.append(f"(GLOBAL PASS {p_idx+1})")
            for i, m in enumerate(seq):
                if p_idx < len(part_passes[i]):
                    z = part_passes[i][p_idx]
                    rk_c = "G41 " if m['rk'] == "WRKL" else "G42 " if m['rk'] == "WRKR" else ""
                    nc.extend([f"G0 X{m['pts'][0][0]:.3f} Y{m['pts'][0][1]:.3f}", f"G1 Z{z:.3f} F2000"])
                    for p in m['pts'][1:]: nc.append(f"G1 X{p[0]:.3f} Y{p[1]:.3f} F3000")
                    nc.extend(["G40", "G0 Z36.0"])
        timeline.append({"tool": t_key, "type": ms_all[0]['mtype']})

    nc.append("M30\n%")
    return "\n".join(nc), milling_data, thick, timeline, (ox, oy)

def plot_v44_11(mills, thick, cfg, part_dims):
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=cfg['bed_x'], y1=cfg['bed_y'], line=dict(color="black", width=2), layer="below")
    fig.add_shape(type="rect", x0=0, y0=0, x1=part_dims[0], y1=part_dims[1], line=dict(color="blue", width=1, dash="dot"))
    for g in mills:
        xp, yp = zip(*g['pts'])
        ps = g.get('active_passes', [g['za']])
        h_info = "".join([f"<br>• עומק חדירה: {round(thick-p, 2) if p>0.5 else abs(round(p,2))} מילימטר" for p in ps])
        fig.add_trace(go.Scatter(x=xp, y=yp, mode='lines', name=g['t_cnc'], hovertemplate=f"<b>{g['t_cnc']}</b>{h_info}<extra></extra>"))
    fig.update_layout(width=700, height=850, showlegend=False, dragmode='pan',
                      xaxis=dict(title="X מילימטר", range=[-50, 1350], gridcolor='lightgray', zeroline=True),
                      yaxis=dict(title="Y מילימטר", range=[-50, 3100], gridcolor='lightgray', zeroline=True))
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

st.sidebar.title("🛠️ Darwish PRO 44.11")
cfg = st.session_state.profiles["אבי"]
rot, gz_off = st.sidebar.checkbox("סובב 90 מעלות"), st.sidebar.slider("כיול Z", -3.0, 3.0, 0.0, 0.1)

upl = st.file_uploader("טען MPR", accept_multiple_files=True)
if upl:
    for f in upl:
        txt = f.getvalue().decode('utf-8', errors='ignore')
        res_init = convert_logic_v44_11(txt, rot, 0, 0, 0, {}, {}, {}, [])
        ox, oy = res_init[4]; thick_mpr = res_init[2]
        with st.sidebar.expander(f"⚙️ {f.name}", expanded=True):
            ax = st.number_input("עוגן X", value=ox, step=0.1, key=f"ax_{f.name}")
            ay = st.number_input("עוגן Y", value=oy, step=0.1, key=f"ay_{f.name}")
            t_ids = sorted(list(set(re.findall(r'(?:TNO|T_)="([^"]*)"', txt))))
            t_map, l_offs = {}, {}
            for tid in t_ids:
                col1, col2 = st.columns([2, 1])
                t_map[tid] = col1.selectbox(f"MPR {tid}:", [t['T_CNC'] for t in cfg['tools']], index=5 if "140" in tid else 1, key=f"tm_{f.name}_{tid}")
                l_offs[tid] = col2.number_input("Z+/-", value=0.0, step=0.1, key=f"zo_{f.name}_{tid}")
            res_ui = convert_logic_v44_11(txt, rot, ax, ay, gz_off, t_map, l_offs, {}, [])
            groups, cp_dict = {}, {}
            for m in res_ui[1]: groups.setdefault((m['t_cnc'], m['mtype'], m['za_orig']), []).append(m)
            st.markdown("### 📏 פסיעות Global")
            for (t_id, mt, za_o), mems in sorted(groups.items()):
                st.markdown(f"**כלי {t_id} | {mt}**")
                label = f"עומק {round(thick_mpr-za_o,1)}" if za_o > 0.5 else f"חדירה {abs(round(za_o,1))}"
                u_ps = [st.number_input(f"פסיעה ({label}):", -5.0, 30.0, za_o, 0.1, key=f"p_{f.name}_{t_id}_{mt}_{za_o}")]
                if st.checkbox("הוסף פסיעה", key=f"add_{f.name}_{t_id}_{mt}_{za_o}"):
                    u_ps.append(st.number_input("נוסף:", -5.0, 30.0, u_ps[-1], 0.1, key=f"n_{f.name}_{t_id}_{mt}_{za_o}"))
                cp_dict[f"{t_id}_{mt}_{za_o}"] = u_ps
            avail_t = sorted(list(set(m['t_cnc'] for m in res_ui[1])))
            t_ord = [t for t in avail_t if t != "T2"] + (["T2"] if "T2" in avail_t else [])
            st.write("סדר כלים:", t_ord)
        nc, mills, thick, tm, _ = convert_logic_v44_11(txt, rot, ax, ay, gz_off, t_map, l_offs, cp_dict, t_ord)
        st.subheader(f"📋 Timeline: {f.name}")
        t_cols = st.columns(len(tm))
        for i, s in enumerate(tm): t_cols[i].info(f"{s['tool']}\n({s['type']})")
        p_l = get_f('l', txt); p_w = get_f('w', txt)
        plot_v44_11(mills, thick, cfg, (p_l, p_w) if not rot else (p_w, p_l))
        st.download_button(f"📥 הורד NC", nc, f.name.replace(".mpr", ".nc"))
