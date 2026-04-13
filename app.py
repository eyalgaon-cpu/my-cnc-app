import streamlit as st
import re, os, math
import plotly.graph_objects as go

# Darwish PRO 43.10 - RK Compensation & Tool Radius Correction
st.set_page_config(page_title="Darwish PRO 43.10", layout="wide")

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
    ], "bed_x": 3050, "bed_y": 1300}}

def get_dist(p1, p2): return math.sqrt((p1['x'] - p2['x'])**2 + (p1['y'] - p2['y'])**2)
def optimize_path(points):
    if not points: return []
    opt = []; curr = {'x': 0, 'y': 0}; rem = points[:]
    while rem:
        nxt = min(rem, key=lambda p: get_dist(curr, p))
        opt.append(nxt); rem.remove(nxt); curr = nxt
    return opt
def get_f(key, block, default=0.0):
    m = re.search(f'{key}="([^"]*)"', block)
    return float(m.group(1)) if m else default

def convert_logic_v43_1(mpr_text, rotate_90, zero_nesting, global_z_off, tool_map, local_offsets, custom_passes_dict):
    thick = get_f('t', mpr_text, 16.0); raw_drills = []; geos = {}
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
        fz = (thick - ti) + global_z_off + local_offsets.get(t_mpr, 0.0)
        t_cnc = tool_map.get(t_mpr, "T44")
        if t_mpr.replace("BV","") in ["5", "5.0", "5.0000"]: t_cnc = "T45" if fz <= 0.2 else "T44"
        for i in range(an): raw_drills.append({'x': xa+(i*ab*math.cos(wi)), 'y': ya+(i*ab*math.sin(wi)), 'z': fz, 't': t_cnc})

    milling_data = []
    for m in re.finditer(r'<(105|130)(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        bc = m.group(2); tno = re.search(r'TNO="([^"]*)"', bc).group(1) if re.search(r'TNO="([^"]*)"', bc) else "142"
        rk = re.search(r'RK="([^"]*)"', bc).group(1) if re.search(r'RK="([^"]*)"', bc) else "NOWRK"
        za = get_f('ZA', bc) + global_z_off + local_offsets.get(tno, 0.0)
        ea = re.search(r'EA="(\d+):', bc); geo_id = ea.group(1) if ea else None
        if geo_id and geo_id in geos:
            milling_data.append({'t_cnc': tool_map.get(tno, "T2"), 'za': round(za, 3), 'pts': [p[:] for p in geos[geo_id]], 'rk': rk})

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

    nc = ["%", "(NC DARWISH 43.10)", "G90 G54 G21"]; timeline = []; out_idx = 1
    used = sorted(list(set([d['t'] for d in raw_drills] + [m['t_cnc'] for m in milling_data])))
    order = [t for t in used if t != "T2"] + (["T2"] if "T2" in used else [])

    for t_id in order:
        nc.append(f"M6 {t_id}")
        ds = [d for d in raw_drills if d['t'] == t_id]
        if ds:
            timeline.append({"op": out_idx, "tool": t_id, "type": "קידוח"})
            for d in optimize_path(ds): nc.extend([f"G0 X{d['x']:.3f} Y{d['y']:.3f}", f"G1 Z{d['z']:.3f} F1000", "G0 Z36.0"])
        ms = [m for m in milling_data if m['t_cnc'] == t_id]
        if ms:
            timeline.append({"op": out_idx, "tool": t_id, "type": "כרסום"})
            for m in ms:
                m['active_passes'] = custom_passes_dict.get(t_id, [m['za']])
                rk_cmd = "G41 " if m['rk'] == "WRKL" else "G42 " if m['rk'] == "WRKR" else ""
                for z in m['active_passes']:
                    nc.extend([f"(PASS Z={z})", f"{rk_cmd}G0 X{m['pts'][0][0]:.3f} Y{m['pts'][0][1]:.3f}", f"G1 Z{z:.3f} F2000"])
                    for p in m['pts'][1:]: nc.append(f"G1 X{p[0]:.3f} Y{p[1]:.3f} F3000")
                    nc.extend(["G40", "G0 Z36.0"])
        out_idx += 1
    nc.append("M30\n%")
    return "\n".join(nc), raw_drills, milling_data, thick, timeline

def plot_v43_1(drills, milling_list, thick, cfg):
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=3050, y1=1300, line=dict(color="black", width=2), layer="below")
    for g in milling_list:
        xp, yp = zip(*g['pts']); ps = sorted(g.get('active_passes', [g['za']]), reverse=True)
        h = "".join([f"<br>פסיעה {i+1} - {round(thick-p,2)} מילימטר" for i,p in enumerate(ps)])
        fig.add_trace(go.Scatter(x=xp, y=yp, mode='lines', line=dict(width=2), hovertemplate=f"כלי: {g['t_cnc']}<br>פיצוי: {g['rk']}{h}<extra></extra>"))
    for d in drills: fig.add_trace(go.Scatter(x=[d['x']], y=[d['y']], mode='markers', hovertemplate=f"קידוח {d['t']}<extra></extra>"))
    fig.update_layout(width=1000, height=500, xaxis=dict(range=[-50, 3100]), yaxis=dict(range=[-50, 1350]), dragmode='pan')
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

st.sidebar.title("🛠️ Darwish PRO 43.10")
cfg = st.session_state.profiles["אבי"]
nest, rot = st.sidebar.checkbox("Nesting"), st.sidebar.checkbox("סובב 90 מעלות")
gz_off = st.sidebar.slider("כיול Z (מילימטר)", -3.0, 3.0, 0.0, 0.1)

uploaded = st.file_uploader("טען MPR", accept_multiple_files=True)
if uploaded:
    for f in uploaded:
        txt = f.getvalue().decode('utf-8', errors='ignore')
        t_ids = sorted(list(set(re.findall(r'(?:DU|TNO)="([^"]*)"', txt))))
        with st.sidebar.expander(f"⚙️ {f.name}", expanded=True):
            t_map, l_offs = {}, {}
            for tid in t_ids:
                col1, col2 = st.columns([2, 1])
                try:
                    v = float(tid.replace("BV",""))
                    idx = 6 if v==130 else 3 if v==128 else 2 if v==158 else 0 if v==137 else 7 if v==35 else 8 if v==15 else 9 if v==8 else 10 if v==5 else 1
                except: idx = 1
                t_map[tid] = col1.selectbox(f"MPR {tid}:", [t['T_CNC'] for t in cfg['tools']], index=min(idx, 11), key=f"t_{f.name}_{tid}")
                l_offs[tid] = col2.number_input("Z+/-", value=0.0, step=0.1, key=f"z_{f.name}_{tid}")
            _, _, m_list, _, _ = convert_logic_v43_1(txt, rot, nest, gz_off, t_map, l_offs, {})
            st.markdown("---")
            st.markdown("### 📏 פסיעות")
            by_tool = {}; [by_tool.setdefault(m['t_cnc'], set()).add(m['za']) for m in m_list]
            c_p_dict = {}
            s_order = [t for t in sorted(by_tool.keys()) if t != "T2"] + (["T2"] if "T2" in by_tool else [])
            for t_id in s_order:
                st.markdown(f"#### כלי {t_id}")
                p_ds = sorted(list(by_tool[t_id]), reverse=True); u_ps = []
                for i, p in enumerate(p_ds): u_ps.append(st.number_input(f"פסיעה {i+1}:", -5.0, 30.0, p, 0.1, key=f"p_{f.name}_{t_id}_{i}"))
                if st.checkbox(f"הוסף פסיעה", key=f"add_{f.name}_{t_id}"): u_ps.append(st.number_input("עומק נוסף:", -5.0, 30.0, u_ps[-1], 0.1, key=f"new_{f.name}_{t_id}"))
                c_p_dict[t_id] = u_ps
        nc, drls, mills, thick, tm = convert_logic_v43_1(txt, rot, nest, gz_off, t_map, l_offs, c_p_dict)
        st.subheader(f"📋 Timeline: {f.name}")
        t_cols = st.columns(min(len(tm), 10))
        for i, s in enumerate(tm[:10]): t_cols[i].info(f"#{s['op']}\n{s['tool']}\n({s['type']})")
        plot_v43_1(drls, mills, thick, cfg)
        st.download_button(f"📥 הורד NC", nc, f.name.replace(".mpr", ".nc"))
