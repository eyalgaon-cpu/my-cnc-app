import streamlit as st
import re, math
import plotly.graph_objects as go

# Darwish PRO 44.58 - FULL HEAVYWEIGHT BUILD (Lead-in + Drills + Plot)
st.set_page_config(page_title="Darwish PRO 44.58", layout="wide")

TOOL_MAP_CONFIG = {
    "130": "T13", "137": "T1", "128": "T4", "158": "T3",
    "142": "T2", "140": "T11", "147": "T8",
    "BV35": "T6", "BV15": "T49", "BV8": "T47", "BV5": "T44"
}

if 'profiles' not in st.session_state:
    st.session_state.profiles = {"אבי": {"tools": [
        {"T_CNC": "T1", "קוטר": 40.0}, {"T_CNC": "T2", "קוטר": 6.0},
        {"T_CNC": "T3", "קוטר": 8.0}, {"T_CNC": "T4", "קוטר": 12.0},
        {"T_CNC": "T8", "קוטר": 19.0}, {"T_CNC": "T11", "קוטר": 3.0},
        {"T_CNC": "T13", "קוטר": 0.2}, {"T_CNC": "T6", "קוטר": 35.0},
        {"T_CNC": "T49", "קוטר": 15.0}, {"T_CNC": "T47", "קוטר": 8.0},
        {"T_CNC": "T44", "קוטר": 5.0}, {"T_CNC": "T45", "קוטר": 5.0}
    ], "bed_x": 1300, "bed_y": 3050}}

def clean_txt(s): return str(s).replace("\r", "").replace("\n", "").strip()
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
    return float(clean_txt(m.group(1))) if m else default

def convert_logic_v44_58(mpr_text, rotate_90, ax, ay, gz_off, t_map, l_offs, cp_dict, user_tool_order, filename=""):
    thick = get_f('t', mpr_text, 19.0)
    raw_drills, milling_data, geos = [], [], {}
    
    parts = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(parts), 2):
        pts = []
        for elem in re.split(r'\$E\d+', parts[i+1]):
            xm, ym = re.search(r'X=([\d.-]+)', elem), re.search(r'Y=([\d.-]+)', elem)
            if xm and ym:
                xv, yv = float(xm.group(1)), float(ym.group(1))
                pts.append([yv, xv] if rotate_90 else [xv, yv])
        if pts: geos[parts[i]] = pts

    # סריקת קידוחים (שחזור)
    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1); ti = get_f('TI', b); za_c = thick - ti
        t_mpr = clean_txt(re.search(r'DU="([^"]*)"', b).group(1)) if re.search(r'DU="([^"]*)"', b) else "5"
        fz = za_c + gz_off + l_offs.get(t_mpr, 0.0)
        xa, ya = get_f('XA', b), get_f('YA', b)
        if rotate_90: xa, ya = ya, xa
        raw_drills.append({'x': xa, 'y': ya, 'z': round(fz, 3), 't': t_map.get(t_mpr, "T44"), 'pts': [[xa, ya]]})

    # סריקת כרסומים
    for op_idx, m_match in enumerate(re.finditer(r'<(105|130|181)(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL)):
        bc, tag = m_match.group(2), m_match.group(1)
        t_mpr = clean_txt(re.search(r'(?:TNO|T_)="([^"]*)"', bc).group(1)) if re.search(r'(?:TNO|T_)="([^"]*)"', bc) else "142"
        za_c = get_f('TI', bc) if tag == '181' else get_f('ZA', bc)
        za = (thick - za_c if tag == '181' else za_c) + gz_off + l_offs.get(t_mpr, 0.0)
        eid = clean_txt(re.search(r'EA="(\d+):', bc).group(1)) if re.search(r'EA="(\d+):', bc) else None
        if eid in geos:
            mt = 'Pocket' if tag=='181' else ('Internal' if za > 0.5 else 'Final')
            milling_data.append({'op_id': op_idx, 't_cnc': t_map.get(t_mpr, "T2"), 'za': round(za, 3), 'pts': [p[:] for p in geos[eid]], 'mtype': mt})

    # חישוב עוגנים
    all_x = [d['x'] for d in raw_drills] + [p[0] for m in milling_data for p in m['pts']]
    all_y = [d['y'] for d in raw_drills] + [p[1] for m in milling_data for p in m['pts']]
    ox, oy = (min(all_x) if all_x else 0.0, min(all_y) if all_y else 0.0)
    for d in raw_drills: d['x'] = d['x'] - ox + ax; d['y'] = d['y'] - oy + ay
    for g in milling_data:
        for p in g['pts']: p[0] = p[0] - ox + ax; p[1] = p[1] - oy + ay

    nc, timeline = ["%", "(NC DARWISH 44.58 - HEAVY BUILD)", "G90 G54 G21"], []
    exec_list = list(user_tool_order) if user_tool_order else []
    
    for t_id in exec_list:
        ds = optimize_sequence([d for d in raw_drills if d['t'] == t_id])
        ms = [m for m in milling_data if m['t_cnc'] == t_id]
        if ds or ms:
            nc.append("M5"); nc.append(f"M6 {t_id}"); nc.append("S18000 M3")
            if ds:
                for d in ds: nc.extend([f"G0 X{d['x']:.3f} Y{d['y']:.3f}", f"G1 Z{d['z']:.3f} F1000", "G0 Z36.0"])
                timeline.append({"tool": t_id, "type": "קידוח"})
            if ms:
                for m in optimize_sequence(ms):
                    for z in cp_dict.get(f"{filename}_{m['op_id']}", [m['za']]):
                        # LEAD-IN LOGIC
                        sx, sy = m['pts'][0][0], m['pts'][0][1]
                        rx, ry = sx - 15.0, sy - 15.0
                        nc.append(f"G0 X{rx:.3f} Y{ry:.3f}")
                        nc.append(f"G1 Z{z:.3f} F2000")
                        rk_c = "G41" if (m['t_cnc'] == "T2" or m['t_cnc'] == "T4") else ""
                        nc.append(f"{rk_c} G1 X{sx:.3f} Y{sy:.3f} F3000" if rk_c else f"G1 X{sx:.3f} Y{sy:.3f} F3000")
                        for p in m['pts'][1:]: nc.append(f"G1 X{p[0]:.3f} Y{p[1]:.3f} F3000")
                        nc.extend(["G40", "G0 Z36.0"])
                timeline.append({"tool": t_id, "type": "כרסום"})
    nc.append("M5\nM30\n%")
    return "\n".join(nc), raw_drills, milling_data, thick, timeline, (ox, oy)

def plot_v44_58(drills, mills, cfg, p_dims):
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=cfg['bed_x'], y1=cfg['bed_y'], line=dict(color="black", width=2))
    fig.add_shape(type="rect", x0=0, y0=0, x1=p_dims[0], y1=p_dims[1], line=dict(color="blue", width=1, dash="dot"))
    for g in mills:
        xp, yp = zip(*g['pts']); fig.add_trace(go.Scatter(x=xp, y=yp, mode='lines', name=g['t_cnc']))
    for d in drills:
        fig.add_trace(go.Scatter(x=[d['x']], y=[d['y']], mode='markers', name=d['t']))
    fig.update_layout(width=700, height=850, showlegend=True, dragmode='pan')
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

# --- UI (Main Loop) ---
st.sidebar.title("🛠️ Darwish PRO 44.58")
cfg = st.session_state.profiles["אבי"]
rot = st.sidebar.checkbox("סובב חלק ב 90 מעלות", value=True)
gz_off = st.sidebar.slider("כיול Z", -3.0, 3.0, 0.0, 0.1)

upl = st.file_uploader("טען MPR", accept_multiple_files=True)
if upl:
    for f in upl:
        txt = f.getvalue().decode('utf-8', errors='ignore')
        t_ids_raw = sorted(list(set(re.findall(r'(?:TNO|T_|DU)="([^"]*)"', txt))))
        t_map, l_offs, cp_dict = {}, {}, {}
        with st.sidebar.expander(f"⚙️ {f.name}", expanded=True):
            res_i = convert_logic_v44_58(txt, rot, 0, 0, 0, TOOL_MAP_CONFIG, {}, {}, [], f.name)
            ax = st.number_input("עוגן X", value=res_i[5][0], key=f"ax_{f.name}")
            ay = st.number_input("עוגן Y", value=res_i[5][1], key=f"ay_{f.name}")
            tl_names = [t['T_CNC'] for t in cfg['tools']]
            for tid in t_ids_raw:
                def_t = TOOL_MAP_CONFIG.get(tid.replace("BV",""), "T2")
                t_map[tid] = st.selectbox(f"MPR {tid}:", tl_names, index=tl_names.index(def_t) if def_t in tl_names else 0, key=f"tm_{f.name}_{tid}")
                l_offs[tid] = 0.0
            res_u = convert_logic_v44_58(txt, rot, ax, ay, gz_off, t_map, l_offs, {}, [], f.name)
            for m in res_u[2]:
                cp_dict[f"{f.name}_{m['op_id']}"] = [st.number_input(f"בלוק {m['op_id']} Z:", value=m['za'], key=f"p_{f.name}_{m['op_id']}")]
            avail = sorted(list(set([m['t_cnc'] for m in res_u[2]] + [d['t'] for d in res_u[1]])))
            t_order = st.multiselect("סדר כלים:", options=avail, default=avail, key=f"ord_{f.name}")

        nc, drls, mills, thick, tm, _ = convert_logic_v44_58(txt, rot, ax, ay, gz_off, t_map, l_offs, cp_dict, t_order, f.name)
        st.subheader(f"📋 Timeline: {f.name}")
        pw, pl = get_f('w', txt), get_f('l', txt)
        plot_v44_58(drls, mills, cfg, (pw, pl) if rot else (pl, pw))
        st.download_button(f"📥 הורד NC (גרסה 44.58)", nc, f.name.replace(".mpr", ".nc"))
