import streamlit as st
import re, os, zipfile
import pandas as pd
import math
from collections import defaultdict
from io import BytesIO

# חובה: פקודה ראשונה
st.set_page_config(page_title="Darwish CNC Pro 33.0", layout="wide")

# טבלת כלים עם עמודת תיקון עומק (Z_Corr)
DEFAULT_TOOLS = [
    {"ID_MPR": "142", "תיאור": "כרסום 6", "T_CNC": "T2", "S": 18000, "F": 6000, "תיקון_Z": 0.0},
    {"ID_MPR": "158", "תיאור": "מקדח 8", "T_CNC": "T47", "S": 4000, "F": 2000, "תיקון_Z": -1.0},
    {"ID_MPR": "100", "תיאור": "מקדח 10", "T_CNC": "T46", "S": 4000, "F": 2000, "תיקון_Z": -0.5},
    {"ID_MPR": "149", "תיאור": "מקדח 15", "T_CNC": "T49", "S": 4000, "F": 2000, "תיקון_Z": 0.0},
    {"ID_MPR": "135", "תיאור": "מקדח 35", "T_CNC": "T6", "S": 3000, "F": 1500, "תיקון_Z": -0.1},
    {"ID_MPR": "121", "תיאור": "מקדח 5", "T_CNC": "T44", "S": 4000, "F": 2000, "תיקון_Z": 0.0}
]

def get_safe_float(key, block, default=0.0):
    match = re.search(f'{key}="([^"]*)"', block)
    if not match: return default
    val_str = match.group(1)
    try: return float(val_str)
    except:
        nums = re.findall(r'[\d.-]+', val_str)
        return float(nums[0]) if nums else default

def convert_logic(mpr_text, tool_df, num_passes, swap_axes, offset, zero_nesting, margin, global_z_off):
    tool_config = tool_df.set_index('T_CNC').to_dict('index')
    # מיפוי משני לפי ID_MPR
    id_to_t = tool_df.set_index('ID_MPR')['T_CNC'].to_dict()
    
    t_m = re.search(r't="([\d.]+)"', mpr_text)
    thickness = float(t_m.group(1)) if t_m else 19.0
    
    geos = {}
    parts = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(parts), 2):
        bid, content = parts[i], parts[i+1]
        pts = []
        for elem in re.split(r'\$E\d+', content):
            x, y = re.search(r'X=([\d.-]+)', elem), re.search(r'Y=([\d.-]+)', elem)
            if x and y: pts.append([float(x.group(1)), float(y.group(1))])
        if pts: geos[bid] = pts

    raw_drills, raw_millings = [], []
    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1)
        xa, ya, ti, du = [get_safe_float(k, b) for k in ['XA', 'YA', 'TI', 'DU']]
        an = int(get_safe_float('AN', b, 1))
        ab, wi = get_safe_float('AB', b), get_safe_float('WI', b)
        tno = re.search(r'TNO="(\d+)"', b).group(1) if re.search(r'TNO="(\d+)"', b) else ""
        
        t_cnc = id_to_t.get(tno, "T44")
        conf = tool_config.get(t_cnc, {"S": 4000, "F": 2000, "תיקון_Z": 0.0})
        
        # חישוב עומק: עובי - TI - כיול כללי - תיקון ספציפי לכלי
        final_z = (thickness - ti) - global_z_off - conf.get("תיקון_Z", 0.0)
        
        for i in range(an):
            raw_drills.append({'x': xa + i*ab*math.cos(math.radians(wi)), 'y': ya + i*ab*math.sin(math.radians(wi)), 
                               'z': final_z, 't': t_cnc, 's': conf['S'], 'f': conf['F'], 'group': m.start()})

    for m in re.finditer(r'<105(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1)
        geo_m = re.search(r'EA="(\d+):', b)
        if geo_m:
            eid = geo_m.group(1)
            za = get_safe_float('ZA', b)
            tno = re.search(r'TNO="(\d+)"', b).group(1) if re.search(r'TNO="(\d+)"', b) else "142"
            t_cnc = id_to_t.get(tno, "T2")
            conf = tool_config.get(t_cnc, {"S": 18000, "F": 6000, "תיקון_Z": 0.0})
            raw_millings.append({'geo_id': eid, 'z': za - global_z_off - conf.get("תיקון_Z", 0.0), 
                                't': t_cnc, 's': conf['S'], 'f': conf['F']})

    if zero_nesting:
        all_x = [d['x'] for d in raw_drills] + [p[0] for bid, pts in geos.items() if bid != "1" for p in pts]
        all_y = [d['y'] for d in raw_drills] + [p[1] for bid, pts in geos.items() if bid != "1" for p in pts]
        if all_x and all_y:
            mx, my = min(all_x), min(all_y)
            for d in raw_drills: d['x'] -= mx; d['y'] -= my
            for bid, pts in geos.items():
                for p in pts: p[0] -= mx; p[1] -= my

    # הוספת Margin (מרווח ביטחון) והחלפת צירים
    for d in raw_drills:
        d['x'] += margin; d['y'] += margin
        if swap_axes: d['x'], d['y'] = d['y'], d['x']
    for bid, pts in geos.items():
        for p in pts:
            p[0] += margin; p[1] += margin
            if swap_axes: p[0], p[1] = p[1], p[0]

    nc, ln, last_t = [f"G90 {offset}"], 10, ""
    for tool_name in sorted(list(set(d['t'] for d in raw_drills))):
        subset = sorted([dr for dr in raw_drills if dr['t']==tool_name], key=lambda k: (k['group'], k['x']))
        for d in subset:
            if d['t'] != last_t:
                nc.extend([f"N{ln} {d['t']} M06", f"N{ln+5} G43 H{d['t'][1:]} S{int(d['s'])} M03"]); ln, last_t = ln+10, d['t']
            nc.extend([f"N{ln} G00 X{d['x']:.3f} Y{d['y']:.3f}", f"N{ln+5} G01 Z{d['z']:.3f} F{int(d['f'])}", f"N{ln+10} G00 Z{thickness+10:.3f}"]); ln+=15
    for m in raw_millings:
        if m['t'] != last_t:
            nc.extend([f"N{ln} {m['t']} M06", f"N{ln+5} G43 H{m['t'][1:]} S{int(m['s'])} M03"]); ln, last_t = ln+10, m['t']
        pts = geos.get(m['geo_id'])
        if pts:
            z_lvls = [m['z']] if num_passes!=2 else [3.0 - global_z_off, -0.25 - global_z_off]
            for zv in z_lvls:
                nc.append(f"N{ln} G00 X{pts[0][0]:.3f} Y{pts[0][1]:.3f}")
                nc.append(f"N{ln+5} G01 Z{zv:.3f} F{int(m['f'])}")
                ln+=10
                for p in pts[1:]: nc.append(f"N{ln} G01 X{p[0]:.3f} Y{p[1]:.3f}"); ln+=5
                nc.append(f"N{ln} G00 Z{thickness+10:.3f}"); ln+=5
    nc.append(f"N{ln} M30")
    return "\n".join(nc)

# --- UI ---
st.title("🪚 Darwish CNC Pro - גרסה 33.0")
st.sidebar.header("🛠️ טבלת כלים וכיול")
if 'tool_df' not in st.session_state: st.session_state.tool_df = pd.DataFrame(DEFAULT_TOOLS)
edited_df = st.sidebar.data_editor(st.session_state.tool_df, num_rows="dynamic")

st.sidebar.markdown("---")
st.sidebar.header("📏 הגדרות עבודה")
z_off_global = st.sidebar.number_input("כיול Z כללי (מ''מ)", value=2.0)
mar_val = st.sidebar.number_input("מרווח ביטחון (Margin)", value=0.0, help="אם הקובץ כבר מורחק ב-WoodWOP, שים כאן 0")
nest_on = st.sidebar.checkbox("צמד לפינה (Nesting)", value=False, help="כבה אם הקובץ כבר ממוקם נכון")
swap_on = st.sidebar.checkbox("החלף צירים (X ↔ Y)", value=True)
off_mode = st.sidebar.selectbox("נקודת אפס", ["G54", "G55"])
mode_sel = st.sidebar.radio("שיטת כרסום:", ('לפי MPR', '2 פסיעות'))

uploaded = st.file_uploader("בחר קבצי MPR", accept_multiple_files=True)
if uploaded:
    pv = 2 if '2 פסיעות' in mode_sel else 0
    for f in uploaded:
        res = convert_logic(f.getvalue().decode('utf-8', errors='ignore'), edited_df, pv, swap_on, off_mode, nest_on, mar_val, z_off_global)
        st.download_button(f"📂 הורד {f.name.replace('.mpr', '.nc')}", res, f.name.replace(".mpr", ".nc"))
        st.code(res, language='gcode')
