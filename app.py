import streamlit as st
import re, math
import plotly.graph_objects as go

# Darwish PRO 45.0 - THE MASTER SPEC (WEIHONG NC60c OFFICIAL)
st.set_page_config(page_title="Darwish 45.0 Master", layout="wide")

# --- קבועי מערכת ---
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

# --- פונקציות עזר ---
def clean_txt(s): return str(s).replace("\r", "").replace("\n", "").strip()
def get_dist(p1, p2): return math.sqrt((p1['x'] - p2['x'])**2 + (p1['y'] - p2['y'])**2)

def get_f(key, block, default=0.0):
    m = re.search(f'{key}="([^"]*)"', block)
    return float(clean_txt(m.group(1))) if m else default

def optimize_sequence(items):
    if not items: return []
    res, curr, rem = [], {'x': 0, 'y': 0}, items[:]
    while rem:
        nxt = min(rem, key=lambda i: get_dist(curr, {'x': i['pts'][0][0], 'y': i['pts'][0][1]} if 'pts' in i else i))
        res.append(nxt); rem.remove(nxt)
        curr = {'x': nxt['pts'][-1][0], 'y': nxt['pts'][-1][1]} if 'pts' in nxt else nxt
    return res

# --- מנוע המרה ראשי ---
def convert_logic_v45_0(mpr_text, rotate_90, ax, ay, gz_off, t_map, cp_dict, user_tool_order, filename=""):
    thick = get_f('t', mpr_text, 19.0)
    raw_drills, milling_data, geos = [], [], {}
    
    # פירוק גאומטריה
    parts = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(parts), 2):
        pts = []
        for elem in re.split(r'\$E\d+', parts[i+1]):
            xm, ym = re.search(r'X=([\d.-]+)', elem), re.search(r'Y=([\d.-]+)', elem)
            if xm and ym:
                xv, yv = float(xm.group(1)), float(ym.group(1))
                pts.append([yv, xv] if rotate_90 else [xv, yv])
        if pts: geos[parts[i]] = pts

    # סריקת קידוחים (<102)
    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1); ti = get_f('TI', b)
        za_c = thick - ti
        t_mpr = clean_txt(re.search(r'DU="([^"]*)"', b).group(1)) if re.search(r'DU="([^"]*)"', b) else "5"
        fz = za_c + gz_off
        xa, ya = get_f('XA', b), get_f('YA', b)
        if rotate_90: xa, ya = ya, xa
        raw_drills.append({'x': xa, 'y': ya, 'z': round(fz, 3), 't': t_map.get(t_mpr, "T44"), 'pts': [[xa, ya]]})

    # סריקת כרסומים (<105, <130, <181)
    for op_idx, m_match in enumerate(re.finditer(r'<(105|130|181)(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL)):
        bc, tag = m_match.group(2), m_match.group(1)
        t_mpr = clean_txt(re.search(r'(?:TNO|T_)="([^"]*)"', bc).group(1)) if re.search(r'(?:TNO|T_)="([^"]*)"', bc) else "142"
        za_c = get_f('TI', bc) if tag == '181' else get_f('ZA', bc)
        za = (thick - za_c if tag == '181' else za_c) + gz_off
        eid = clean_txt(re.search(r'EA="(\d+):', bc).group(1)) if re.search(r'EA="(\d+):', bc) else None
        if eid in geos:
            milling_data.append({'op_id': op_idx, 't_cnc': t_map.get(t_mpr, "T2"), 'za': round(za, 3), 'pts': [p[:] for p in geos[eid]]})

    # חישוב אופסט עוגן
    all_x = [d['x'] for d in raw_drills] + [p[0] for m in milling_data for p in m['pts']]
    all_y = [d['y'] for d in raw_drills] + [p[1] for m in milling_data for p in m['pts']]
    ox, oy = (min(all_x) if all_x else 0.0, min(all_y) if all_y else 0.0)
    for d in raw_drills: d['x'] = d['x'] - ox + ax; d['y'] = d['y'] - oy + ay
    for g in milling_data:
        for p in g['pts']: p[0] = p[0] - ox + ax; p[1] = p[1] - oy + ay

    # בניית NC (WEIHONG Syntax)
    n_idx = 10
    def n(): nonlocal n_idx; r = f"N{n_idx}"; n_idx += 10; return r

    nc = ["%", f"({n()} MASTER 45.0 - {filename})", f"{n()} G90 G54 G21"]
    for t_id in user_tool_order:
        ds = optimize_sequence([d for d in raw_drills if d['t'] == t_id])
        ms = optimize_sequence([m for m in milling_data if m['t_cnc'] == t_id])
        if ds or ms:
            nc.append(f"{n()} M05")
            nc.append(f"{n()} {t_id} M06")
            nc.append(f"{n()} G00 G43 H{t_id.replace('T','')}") # פיצוי אורך
            nc.append(f"{n()} S18000 M03")
            if ds:
                for d in ds:
                    nc.append(f"{n()} G00 X{d['x']:.3f} Y{d['y']:.3f}")
                    nc.append(f"{n()} G01 Z{d['z']:.3f} F1000")
                    nc.append(f"{n()} G00 Z36.0")
            if ms:
                for m in ms:
                    for z in cp_dict.get(f"{filename}_{m['op_id']}", [m['za']]):
                        sx, sy = m['pts'][0][0], m['pts'][0][1]
                        nc.append(f"{n()} G00 X{sx-20:.3f} Y{sy-20:.3f}") # Lead-in
                        nc.append(f"{n()} G01 Z{z:.3f} F2000")
                        comp = "G41" if t_id == "T2" else "G42"
                        nc.append(f"{n()} {comp} D{t_id.replace('T','')} G01 X{sx:.3f} Y{sy:.3f} F3000")
                        for p in m['pts'][1:]: nc.append(f"{n()} G01 X{p[0]:.3f} Y{p[1]:.3f} F3000")
                        nc.append(f"{n()} G40")
                        nc.append(f"{n()} G00 Z36.0")
    
    nc.extend([f"{n()} M05", f"{n()} M30", f"{n()} M200", "%"])
    return "\n".join(nc), raw_drills, milling_data, (ox, oy)

# --- ממשק משתמש ---
st.sidebar.title("🛠️ Darwish PRO 45.0")
cfg = st.session_state.profiles["אבי"]
rot = st.sidebar.checkbox("סובב חלק ב 90 מעלות", value=True)
gz_off = st.sidebar.slider("כיול Z גלובלי", -3.0, 3.0, 0.0, 0.1)

upl = st.file_uploader("טען קבצי MPR", accept_multiple_files=True)
if upl:
    for f in upl:
        txt = f.getvalue().decode('utf-8', errors='ignore')
        with st.sidebar.expander(f"⚙️ הגדרות: {f.name}", expanded=True):
            ax = st.number_input("עוגן X", value=30.0, key=f"ax_{f.name}")
            ay = st.number_input("עוגן Y", value=30.0, key=f"ay_{f.name}")
            
            # מיפוי כלים דינמי
            t_ids = sorted(list(set(re.findall(r'(?:TNO|T_|DU)="([^"]*)"', txt))))
            t_map = {}
            for tid in t_ids:
                def_t = TOOL_MAP_CONFIG.get(tid.replace("BV",""), "T2")
                t_map[tid] = st.selectbox(f"MPR {tid}:", [t['T_CNC'] for t in cfg['tools']], index=0, key=f"tm_{f.name}_{tid}")
            
            # עריכת עומקים לכל בלוק
            res_temp = convert_logic_v45_0(txt, rot, ax, ay, gz_off, t_map, {}, [], f.name)
            cp_dict = {}
            for m in res_temp[2]:
                cp_dict[f"{f.name}_{m['op_id']}"] = [st.number_input(f"בלוק {m['op_id']} Z:", value=m['za'], key=f"z_{f.name}_{m['op_id']}")]
            
            avail_tools = sorted(list(set([m['t_cnc'] for m in res_temp[2]] + [d['t'] for d in res_temp[1]])))
            t_order = st.multiselect("סדר כלים:", options=avail_tools, default=avail_tools, key=f"ord_{f.name}")

        nc, drls, mills, _ = convert_logic_v45_0(txt, rot, ax, ay, gz_off, t_map, cp_dict, t_order, f.name)
        
        # תצוגה גרפית
        fig = go.Figure()
        fig.add_shape(type="rect", x0=0, y0=0, x1=cfg['bed_x'], y1=cfg['bed_y'], line=dict(color="black", width=2))
        for g in mills:
            xp, yp = zip(*g['pts']); fig.add_trace(go.Scatter(x=xp, y=yp, mode='lines', name=g['t_cnc']))
        for d in drls:
            fig.add_trace(go.Scatter(x=[d['x']], y=[d['y']], mode='markers', name=d['t']))
        fig.update_layout(width=700, height=850, title=f"Preview: {f.name}")
        st.plotly_chart(fig, use_container_width=True)
        
        st.download_button(f"📥 הורד NC (גרסת 45.0 Master)", nc, f.name.replace(".mpr", ".nc"))
