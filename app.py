import streamlit as st
import re, os
import pandas as pd
import math

st.set_page_config(page_title="Darwish CNC Pro 35.0", layout="wide")

DEFAULT_TOOLS = [
    {"קוטר": 6.0, "תיאור": "כרסום 6", "T_CNC": "T2", "S": 18000, "F": 6000, "תיקון_Z": 0.0},
    {"קוטר": 8.0, "תיאור": "מקדח 8", "T_CNC": "T47", "S": 4000, "F": 2000, "תיקון_Z": -1.0},
    {"קוטר": 10.0, "תיאור": "מקדח 10", "T_CNC": "T46", "S": 4000, "F": 2000, "תיקון_Z": -0.5},
    {"קוטר": 15.0, "תיאור": "מקדח 15", "T_CNC": "T49", "S": 4000, "F": 2000, "תיקון_Z": 0.0},
    {"קוטר": 35.0, "תיאור": "מקדח 35", "T_CNC": "T6", "S": 3000, "F": 1500, "תיקון_Z": -0.1},
    {"קוטר": 5.0, "תיאור": "מקדח 5", "T_CNC": "T44", "S": 4000, "F": 2000, "תיקון_Z": 0.0}
]

def get_safe_float(key, block, default=0.0):
    match = re.search(f'{key}="([^"]*)"', block)
    if not match: return default
    try: return float(match.group(1))
    except:
        nums = re.findall(r'[\d.-]+', match.group(1))
        return float(nums[0]) if nums else default

def convert_logic(mpr_text, tool_df, num_passes, swap_axes, offset, zero_nesting, margin, global_z_off):
    dia_map = {round(float(row['קוטר']), 1): row for _, row in tool_df.iterrows()}
    thickness = get_safe_float('t', mpr_text, 19.0)
    
    geos = {}
    parts = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(parts), 2):
        bid, content = parts[i], parts[i+1]
        pts = []
        for elem in re.split(r'\$E\d+', content):
            x_m, y_m = re.search(r'X=([\d.-]+)', elem), re.search(r'Y=([\d.-]+)', elem)
            if x_m and y_m: pts.append([float(x_m.group(1)), float(y_m.group(1))])
        if pts: geos[bid] = pts

    raw_drills, raw_millings = [], []
    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1)
        xa, ya, ti, du = [get_safe_float(k, b) for k in ['XA', 'YA', 'TI', 'DU']]
        an, ab, wi = int(get_safe_float('AN', b, 1)), get_safe_float('AB', b), get_safe_float('WI', b)
        conf = dia_map.get(round(du, 1))
        if not conf: continue
        
        final_z = (thickness - ti) - global_z_off - conf.get("תיקון_Z", 0.0)
        for i in range(an):
            raw_drills.append({
                'x': xa + i * ab * math.cos(math.radians(wi)),
                'y': ya + i * ab * math.sin(math.radians(wi)),
                'z': final_z, 't': conf['T_CNC'], 's': conf['S'], 'f': conf['F'], 'group': m.start()
            })

    for m in re.finditer(r'<105(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1)
        geo_m = re.search(r'EA="(\d+):', b)
        if geo_m:
            eid = geo_m.group(1)
            za = get_safe_float('ZA', b)
            conf = dia_map.get(6.0, {"T_CNC": "T2", "S": 18000, "F": 6000, "תיקון_Z": 0.0})
            raw_millings.append({'geo_id': eid, 'z': za - global_z_off - conf.get("תיקון_Z", 0.0), 't': conf['T_CNC'], 's': conf['S'], 'f': conf['F']})

    # נרמול ואיפוס גלובלי (שימור יחסי)
    if zero_nesting:
        # עדיפות לכרסומים כגבולות גזרה
        ref_x = [p[0] for pts in geos.values() for p in pts] if geos else [d['x'] for d in raw_drills]
        ref_y = [p[1] for pts in geos.values() for p in pts] if geos else [d['y'] for d in raw_drills]
        if ref_x and ref_y:
            mx, my = min(ref_x), min(ref_y)
            for d in raw_drills: d['x'] -= mx; d['y'] -= my
            for pts in geos.values():
                for p in pts: p[0] -= mx; p[1] -= my

    # הוספת Margin והחלפת צירים
    for d in raw_drills:
        d['x'] += margin; d['y'] += margin
        if swap_axes: d['x'], d['y'] = d['y'], d['x']
    for pts in geos.values():
        for p in pts:
            p[0] += margin; p[1] += margin
            if swap_axes: p[0], p[1] = p[1], p[0]

    nc, ln, last_t = [f"G90 {offset}"], 10, ""
    active_tools = sorted(list(set(d['t'] for d in raw_drills)))
    for t_name in active_tools:
        subset = sorted([dr for dr in raw_drills if dr['t']==t_name], key=lambda k: (k['group'], k['x']))
        for d in subset:
            if d['t'] != last_t:
                nc.extend([f"N{ln} {d['t']} M06", f"N{ln+5} G43 H{d['t'][1:]} S{int(d['s'])} M03"])
                ln, last_t = ln + 10, d['t']
            nc.extend([f"N{ln} G00 X{d['x']:.3f} Y{d['y']:.3f}", f"N{ln+5} G01 Z{d['z']:.3f} F{int(d['f'])}", f"N{ln+10} G00 Z{thickness+10:.3f}"])
            ln += 15
            
    for m in raw_millings:
        if m['t'] != last_t:
            nc.extend([f"N{ln} {m['t']} M06", f"N{ln+5} G43 H{m['t'][1:]} S{int(m['s'])} M03"])
            ln, last_t = ln + 10, m['t']
        pts = geos.get(m['geo_id'])
        if pts:
            z_levels = [m['z']] if num_passes!=2 else [3.0 - global_z_off, -0.25 - global_z_off]
            for zv in z_levels:
                nc.append(f"N{ln} G00 X{pts[0][0]:.3f} Y{pts[0][1]:.3f}")
                nc.append(f"N{ln+5} G01 Z{zv:.3f} F{int(m['f'])}")
                ln+=10
                for p in pts[1:]: nc.append(f"N{ln} G01 X{p[0]:.3f} Y{p[1]:.3f}"); ln+=5
                nc.append(f"N{ln} G00 Z{thickness+10:.3f}"); ln+=5
    nc.append(f"N{ln} M30")
    return "\n".join(nc)

# UI
st.title("🪚 Darwish CNC Pro - גרסה 35.0")
if 'tool_df' not in st.session_state: st.session_state.tool_df = pd.DataFrame(DEFAULT_TOOLS)
edited_df = st.sidebar.data_editor(st.session_state.tool_df, num_rows="dynamic")
z_off = st.sidebar.number_input("כיול Z כללי", value=2.0)
mar = st.sidebar.number_input("Margin (מרווח סופי)", value=7.0)
nest = st.sidebar.checkbox("צמד לפינה (Nesting)", value=True)
swap = st.sidebar.checkbox("החלף צירים (X ↔ Y)", value=True)
uploaded = st.file_uploader("בחר קבצי MPR", accept_multiple_files=True)

if uploaded:
    for f in uploaded:
        res = convert_logic(f.getvalue().decode('utf-8', errors='ignore'), edited_df, 0, swap, "G54", nest, mar, z_off)
        st.download_button(f"📂 הורד {f.name.replace('.mpr', '.nc')}", res, f.name.replace(".mpr", ".nc"))
        st.code(res, language='gcode')
