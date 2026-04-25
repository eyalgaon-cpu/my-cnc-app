import streamlit as st
import re, math, json, os
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# Darwish 53.1 - REAL CIRCLES (FULL INTEGRITY)
# 52.2-53.0 היסטוריה | 53.1: קידוחים מוצגים כעיגולים גיאומטריים אמיתיים בסקלה נכונה
st.set_page_config(page_title="Darwish 53.1 Local", layout="wide")

CONFIG_FILE = "darwish_config.json"

# --- 1. מנוע סנכרון מקומי (Persistence Engine) ---
def save_config_auto():
    cfg = {
        "tool_db": st.session_state.tool_db.to_dict('records'),
        "safety_h": st.session_state.get('safety_h', 35.0),
        "off_x": st.session_state.get('off_x', 0.0),
        "off_y": st.session_state.get('off_y', 0.0),
        "gz": st.session_state.get('gz', 0.0)
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

def load_config_auto():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            st.session_state.tool_db = pd.DataFrame(cfg["tool_db"])
            st.session_state.safety_h = cfg.get("safety_h", 35.0)
            st.session_state.off_x = cfg.get("off_x", 0.0)
            st.session_state.off_y = cfg.get("off_y", 0.0)
            st.session_state.gz = cfg.get("gz", 0.0)
            return True
    return False

# --- 2. אתחול מסד כלים ---
if 'tool_db' not in st.session_state:
    if not load_config_auto():
        st.session_state.tool_db = pd.DataFrame([
            # כרסומים
            {"T_CNC": "T1",      "MPR_Name": "137",     "תיאור": "כרסום 40 מילימטר (ניקוי פוקט)",        "קוטר": 40.0,  "Z_Offset": 0.0, "RPM": 18000, "Feed": 8000},
            {"T_CNC": "T2",      "MPR_Name": "142",     "תיאור": "כרסום יהלום 6 מילימטר",               "קוטר": 6.0,   "Z_Offset": 0.0, "RPM": 17000, "Feed": 14000},
            {"T_CNC": "T3",      "MPR_Name": "158",     "תיאור": "כרסום 8 מילימטר",                     "קוטר": 8.0,   "Z_Offset": 0.0, "RPM": 22000, "Feed": 13000},
            {"T_CNC": "T4",      "MPR_Name": "128",     "תיאור": "כרסום 12 מילימטר",                    "קוטר": 12.0,  "Z_Offset": 0.0, "RPM": 22000, "Feed": 13000},
            {"T_CNC": "T8",      "MPR_Name": "MISSING", "תיאור": "כרסום 19 מילימטר",                    "קוטר": 18.0,  "Z_Offset": 0.0, "RPM": 22000, "Feed": 12000},
            {"T_CNC": "T11",     "MPR_Name": "140",     "תיאור": "כרסום 3 מילימטר",                     "קוטר": 3.0,   "Z_Offset": 0.0, "RPM": 20000, "Feed": 9000},
            {"T_CNC": "T12",     "MPR_Name": "MISSING", "תיאור": "כרסום 76 מילימטר (ניקוי פוקט גדול)", "קוטר": 76.2,  "Z_Offset": 0.0, "RPM": 12000, "Feed": 2000},
            {"T_CNC": "T15",     "MPR_Name": "MISSING", "תיאור": "כרסום 5 מילימטר",                    "קוטר": 5.0,   "Z_Offset": 0.0, "RPM": 22000, "Feed": 12000},
            {"T_CNC": "T23",     "MPR_Name": "MISSING", "תיאור": "כרסום ארוך 12.7 מילימטר",            "קוטר": 12.7,  "Z_Offset": 0.0, "RPM": 20000, "Feed": 6000},
            # וי-ביט
            {"T_CNC": "T13",     "MPR_Name": "130",     "תיאור": "וי-ביט 90 מעלות - גירונג",            "קוטר": 38.0,  "Z_Offset": 0.0, "RPM": 20000, "Feed": 10000},
            {"T_CNC": "T14",     "MPR_Name": "MISSING", "תיאור": "וי-ביט 120 מעלות",                   "קוטר": 32.0,  "Z_Offset": 0.0, "RPM": 18000, "Feed": 10000},
            # מקדחים
            {"T_CNC": "T6",      "MPR_Name": "35.0",    "תיאור": "מקדח צירים 35 מילימטר",              "קוטר": 35.0,  "Z_Offset": 0.0, "RPM": 4000,  "Feed": 1000},
            {"T_CNC": "T44",     "MPR_Name": "5.0",     "תיאור": "מקדח 5 מילימטר",                     "קוטר": 5.0,   "Z_Offset": 0.0, "RPM": 3500,  "Feed": 2800},
            {"T_CNC": "T45",     "MPR_Name": "MISSING", "תיאור": "מקדח 5 מילימטר (חור עובר)",          "קוטר": 5.0,   "Z_Offset": 0.0, "RPM": 3500,  "Feed": 2800},
            {"T_CNC": "T47",     "MPR_Name": "8.0",     "תיאור": "מקדח 8 מילימטר",                     "קוטר": 8.0,   "Z_Offset": 0.0, "RPM": 3500,  "Feed": 2800},
            {"T_CNC": "T48",     "MPR_Name": "3.0",     "תיאור": "מקדח 3 מילימטר",                     "קוטר": 3.0,   "Z_Offset": 0.0, "RPM": 3500,  "Feed": 2300},
            {"T_CNC": "T49",     "MPR_Name": "15.0",    "תיאור": "מקדח 15 מילימטר",                    "קוטר": 15.0,  "Z_Offset": 0.0, "RPM": 4000,  "Feed": 2800},
            {"T_CNC": "T42",     "MPR_Name": "MISSING", "תיאור": "מקדח 5 מילימטר (שלישייה)",           "קוטר": 4.98,  "Z_Offset": 0.0, "RPM": 3500,  "Feed": 2800},
            {"T_CNC": "T46",     "MPR_Name": "MISSING", "תיאור": "מקדח 10 מילימטר",                    "קוטר": 10.0,  "Z_Offset": 0.0, "RPM": 3500,  "Feed": 2800},
            # כלים חסרים במכונה
            {"T_CNC": "MISSING", "MPR_Name": "136",     "תיאור": "כרסום 16 מילימטר (חסר במכונה)",      "קוטר": 16.0,  "Z_Offset": 0.0, "RPM": 18000, "Feed": 2000},
            {"T_CNC": "MISSING", "MPR_Name": "139",     "תיאור": "כרסום 10 מילימטר (חסר במכונה)",      "קוטר": 10.0,  "Z_Offset": 0.0, "RPM": 18000, "Feed": 3000},
        ])

with st.sidebar:
    st.header("🛠️ ניהול ייצור (Local Sync)")
    with st.expander("פרופיל מכונה וכלים", expanded=True):
        new_df = st.data_editor(st.session_state.tool_db, num_rows="dynamic", key="tools_v522")
        if not new_df.equals(st.session_state.tool_db):
            st.session_state.tool_db = new_df
        save_config_auto()
        if st.button("אפס להגדרות יצרן"):
            if os.path.exists(CONFIG_FILE): os.remove(CONFIG_FILE)
            for key in ['tool_db', 'safety_h', 'off_x', 'off_y', 'gz']:
                if key in st.session_state: del st.session_state[key]
            st.rerun()

    st.divider()
    safety_h = st.number_input("גובה בטיחות Z (מילימטר)", value=st.session_state.get('safety_h', 35.0), key='safety_h_in')
    off_x = st.number_input("הזזת פלטה ציר X (מילימטר)", value=st.session_state.get('off_x', 0.0), key='off_x_in')
    off_y = st.number_input("הזזת פלטה ציר Y (מילימטר)", value=st.session_state.get('off_y', 0.0), key='off_y_in')
    gz = st.number_input("תיקון Z גלובלי (מילימטר)", value=st.session_state.get('gz', 0.0), key='gz_in')

    if (safety_h != st.session_state.get('safety_h') or off_x != st.session_state.get('off_x') or 
        off_y != st.session_state.get('off_y') or gz != st.session_state.get('gz')):
        st.session_state.safety_h = safety_h
        st.session_state.off_x = off_x
        st.session_state.off_y = off_y
        st.session_state.gz = gz
        save_config_auto()

# --- 3. ליבה מתמטית v52.2 ---
def _safe_float(val):
    try: return float(re.sub(r'[^0-9.\-]', '', str(val)))
    except: return 0.0

def rotate_pt_v518(x, y, angle_deg):
    rad = math.radians(angle_deg)
    return x * math.cos(rad) - y * math.sin(rad), x * math.sin(rad) + y * math.cos(rad)

def find_tool_numeric(mpr_id, df):
    try:
        target = round(_safe_float(mpr_id), 1)
        for _, row in df.iterrows():
            if round(_safe_float(row['MPR_Name']), 1) == target:
                is_missing = (row['T_CNC'] == "MISSING")
                return row, is_missing
    except: pass
    return {"T_CNC": "MISSING", "תיאור": f"כלי {mpr_id} לא מזוהה בטבלה", "קוטר": 6.0, "Z_Offset": 0.0, "RPM": 12000, "Feed": 2000}, True

def optimize_drill_path_v518(ops):
    if not ops: return ops
    optimized = [ops.pop(0)]
    while ops:
        last = optimized[-1]['pts'][0]
        next_idx = min(range(len(ops)), key=lambda i: (ops[i]['pts'][0][0]-last[0])**2 + (ops[i]['pts'][0][1]-last[1])**2)
        optimized.append(ops.pop(next_idx))
    return optimized

def calculate_path_v518(pts, r, mpr_rk, is_pocket=False):
    if r <= 0 or len(pts) < 2: return pts
    pts_arr = np.array(pts); n = len(pts_arr)
    area = sum((pts_arr[i][0]*pts_arr[(i+1)%n][1] - pts_arr[(i+1)%n][0]*pts_arr[i][1]) for i in range(n))/2.0
    side = (1 if area > 0 else -1) if is_pocket else (1 if "WRKL" in mpr_rk else -1 if "WRKR" in mpr_rk else 0)
    if side == 0: return pts

    if is_pocket:
        min_x, max_x = np.min(pts_arr[:,0]), np.max(pts_arr[:,0]); min_y, max_y = np.min(pts_arr[:,1]), np.max(pts_arr[:,1])
        r_guard = r + 0.1

    shifted = []
    for i in range(n-1):
        p1, p2 = pts_arr[i], pts_arr[i+1]; v = p2-p1; mag = np.linalg.norm(v)
        if mag == 0: continue
        normal = side * np.array([-v[1], v[0]]) / mag
        shifted.append((p1 + normal*r, p2 + normal*r))
    
    if not shifted: return pts
    
    def intersect(l1, l2):
        x1,y1=l1[0]; x2,y2=l1[1]; x3,y3=l2[0]; x4,y4=l2[1]
        den = (y4-y3)*(x2-x1)-(x4-x3)*(y2-y1)
        if abs(den)<1e-6: return l1[1]
        ua = ((x4-x3)*(y1-y3)-(y4-y3)*(x1-x3))/den
        return np.array([x1+ua*(x2-x1), y1+ua*(y2-y1)])
    
    new_path = []
    p0 = shifted[0][0]
    if is_pocket: p0 = [np.clip(p0[0], min_x+r_guard, max_x-r_guard), np.clip(p0[1], min_y+r_guard, max_y-r_guard)]
    new_path.append(tuple(p0))

    for i in range(len(shifted)-1):
        p_inter = intersect(shifted[i], shifted[i+1])
        if is_pocket:
            safe_x = (min_x + r_guard <= p_inter[0] <= max_x - r_guard)
            safe_y = (min_y + r_guard <= p_inter[1] <= max_y - r_guard)
            if not (safe_x and safe_y):
                new_path.append(tuple([np.clip(shifted[i][1][0], min_x+r_guard, max_x-r_guard), np.clip(shifted[i][1][1], min_y+r_guard, max_y-r_guard)]))
                new_path.append(tuple([np.clip(shifted[i+1][0][0], min_x+r_guard, max_x-r_guard), np.clip(shifted[i+1][0][1], min_y+r_guard, max_y-r_guard)]))
            else: new_path.append(tuple(p_inter))
        else: new_path.append(tuple(p_inter))

    pE = shifted[-1][1]
    if is_pocket: pE = [np.clip(pE[0], min_x+r_guard, max_x-r_guard), np.clip(pE[1], min_y+r_guard, max_y-r_guard)]
    new_path.append(tuple(pE))
    return new_path

def get_f(key, block, default=0.0):
    m = re.search(f'{key}="?([^"\\s]+)"?', block)
    return _safe_float(m.group(1)) if m else default

# --- 4. ממשק הפקה והדמיה ---
st.title("🏭 דרוויש 53.1 - REAL CIRCLES")
col_cfg, col_vis = st.columns([1, 2])

# שמירת נתוני הדמיה לכל קובץ
if 'fig_data' not in st.session_state:
    st.session_state.fig_data = {}
if 'file_info' not in st.session_state:
    st.session_state.file_info = {}

with col_cfg:
    st.subheader("הגדרות פרויקט")
    rotate = st.checkbox("סובב חלק 90 מעלות (CCW)", value=True)
    ramp_len_global = st.slider("אורך נחיתה (Ramp)", 0, 50, 20)
    upl = st.file_uploader("טען קבצי MPR", accept_multiple_files=True, type=['mpr'])

# בורר קובץ - שולט גם על הדמיה וגם על בלוקים
selected_file = None
if upl:
    file_names = [f.name for f in upl]
    with col_vis:
        if len(file_names) > 1:
            selected_file = st.radio("בחר קובץ:", file_names, horizontal=True)
        else:
            selected_file = file_names[0]
        vis_placeholder = st.empty()

if upl:
    for f_file in upl:
        mpr = f_file.getvalue().decode('utf-8', errors='ignore')
        wp_match = re.search(r'\[001(.*?)\]', mpr, re.DOTALL); wp_block = wp_match.group(1) if wp_match else ""
        wp_l, wp_w = get_f('l', wp_block, 2440.0), get_f('w', wp_block, 1220.0); thick = get_f('t', mpr, 19.0)

        geos = {}
        parts = re.split(r'\](\d+)', mpr)
        for i in range(1, len(parts), 2):
            pts = []
            for el in re.split(r'\$E\d+', parts[i+1]):
                xm, ym = re.search(r'X=([\d.-]+)', el), re.search(r'Y=([\d.-]+)', el)
                if xm and ym: pts.append([wp_w - float(ym.group(1)), float(xm.group(1))] if rotate else [float(xm.group(1)), float(ym.group(1))])
            if pts: geos[parts[i]] = pts

        ops = []
        for m in re.finditer(r'<(102|105|112|130|181)(.*?)(?=<|\!|\[H)', mpr, re.DOTALL):
            tag, bc = m.group(1), m.group(2)
            t_mpr = re.search(r'(?:TNO|T_|DU)="?([^"\\s]+)"?', bc).group(1).strip() if re.search(r'(?:TNO|T_|DU)="?([^"\\s]+)"?', bc) else "142"
            t_info, is_missing = find_tool_numeric(t_mpr, st.session_state.tool_db)
            ti_val = get_f('TI', bc); z_abs = round((thick - ti_val), 3) if tag in ['102', '181', '112'] else round(get_f('ZA', bc), 3)

            if tag == '102':
                xa, ya, an, ab, xr, yr = get_f('XA', bc), get_f('YA', bc), int(get_f('AN', bc, 1)), get_f('AB', bc, 0.0), get_f('XR', bc, 1.0), get_f('YR', bc, 0.0)
                for i in range(an):
                    curr_xa, curr_ya = xa + (i*ab*xr), ya + (i*ab*yr)
                    ops.append({'t_cnc': t_info['T_CNC'], 'desc': t_info['תיאור'], 'z': z_abs, 'ti': ti_val, 'z_off': t_info['Z_Offset'], 'pts': [[wp_w - curr_ya, curr_xa]] if rotate else [[curr_xa, curr_ya]], 'rad': t_info['קוטר']/2, 'diam': t_info['קוטר'], 'f': t_info['Feed'], 's': t_info['RPM'], 'type': tag, 'ea': f"DRILL_{round(curr_xa,1)}", 'rk': "WRKL", 'is_pocket': False, 'missing': is_missing})
            elif tag == '112':
                xa, ya, la, br, wi = get_f('XA', bc), get_f('YA', bc), get_f('LA', bc), get_f('BR', bc), get_f('WI', bc)
                rect_local = [(-la/2, -br/2), (la/2, -br/2), (la/2, br/2), (-la/2, br/2), (-la/2, -br/2)]
                f_pts = [[wp_w - (rotate_pt_v518(px, py, wi)[1] + ya), rotate_pt_v518(px, py, wi)[0] + xa] if rotate else [rotate_pt_v518(px, py, wi)[0] + xa, rotate_pt_v518(px, py, wi)[1] + ya] for px, py in rect_local]
                ops.append({'t_cnc': t_info['T_CNC'], 'desc': t_info['תיאור'], 'z': z_abs, 'ti': ti_val, 'z_off': t_info['Z_Offset'], 'pts': f_pts, 'rad': t_info['קוטר']/2, 'diam': t_info['קוטר'], 'f': t_info['Feed'], 's': t_info['RPM'], 'type': tag, 'ea': "TASCHE", 'rk': "WRKL", 'is_pocket': True, 'missing': is_missing})
            else:
                geoid = re.search(r'EA="?(\d+):?', bc).group(1).strip() if re.search(r'EA="?(\d+):?', bc) else "FREE"
                f_pts = geos.get(geoid) if geos.get(geoid) else [[wp_w - get_f('YA', bc), get_f('XA', bc)] if rotate else [get_f('XA', bc), get_f('YA', bc)]]
                ops.append({'t_cnc': t_info['T_CNC'], 'desc': t_info['תיאור'], 'z': z_abs, 'ti': thick-z_abs, 'z_off': t_info['Z_Offset'], 'pts': f_pts, 'rad': t_info['קוטר']/2, 'diam': t_info['קוטר'], 'f': t_info['Feed'], 's': t_info['RPM'], 'type': tag, 'ea': geoid, 'rk': re.search(r'RK="([^"]*)"', bc).group(1) if re.search(r'RK="([^"]*)"', bc) else "WRKL", 'is_pocket': (tag == '181'), 'missing': is_missing})

        visual_blocks = {}
        for op in ops:
            v_key = (op['t_cnc'], op['type'], tuple(tuple(p) for p in op['pts'])) if op['type'] != '102' else (op['t_cnc'], op['type'])
            if v_key not in visual_blocks: visual_blocks[v_key] = {'t_cnc': op['t_cnc'], 'desc': op['desc'], 'type': op['type'], 'is_dr': op['type'] == '102', 'paths': [], 's': op['s'], 'f': op['f'], 'diam': op['diam'], 'ea_id': op['ea'], 'missing': is_missing}
            visual_blocks[v_key]['paths'].append(op)
        
        for vk in visual_blocks:
            if visual_blocks[vk]['is_dr']: visual_blocks[vk]['paths'] = optimize_drill_path_v518(visual_blocks[vk]['paths'])

        # --- קיבוץ אוטומטי של כלים (Tool Grouping) ---
        # שלב 1: חישוב אם כל בלוק הוא ניתוק (sep) או לא
        blocks_list = []
        for v_key, v_block in visual_blocks.items():
            z_vals = sorted(list(set(p['z'] for p in v_block['paths'])), reverse=True)
            is_sep = any(z <= 0.2 for z in z_vals)
            blocks_list.append((v_key, v_block, z_vals, is_sep))

        # שלב 2: קיבוץ - כלים לא-ניתוק לפי כלי, ניתוק בסוף
        tool_groups = {}  # כלי -> רשימת בלוקים לא-ניתוק לפי סדר הופעה
        sep_blocks = []   # בלוקי ניתוק
        for item in blocks_list:
            v_key, v_block, z_vals, is_sep = item
            t = v_block['t_cnc']
            if is_sep:
                sep_blocks.append(item)
            else:
                if t not in tool_groups: tool_groups[t] = []
                tool_groups[t].append(item)

        # שלב 3: בניית הסדר הסופי - כלים מקובצים + ניתוק בסוף
        ordered_blocks = []
        seen_tools = []
        for item in blocks_list:
            t = item[1]['t_cnc']
            if not item[3] and t not in seen_tools:  # לא ניתוק ולא נראה עדיין
                seen_tools.append(t)
                ordered_blocks.extend(tool_groups[t])
        ordered_blocks.extend(sep_blocks)

        # שלב 4: חישוב def_idx לפי הסדר החדש
        def_idx_map = {}
        sep_counter = 1000
        reg_counter = 10
        for item in ordered_blocks:
            v_key = item[0]
            is_sep = item[3]
            if is_sep:
                def_idx_map[v_key] = sep_counter
                sep_counter += 10
            else:
                def_idx_map[v_key] = reg_counter
                reg_counter += 10

        # שמירת מידע על הפלטה
        st.session_state.file_info[f_file.name] = {
            'l': wp_l, 'w': wp_w, 't': thick,
            'n_parts': len([k for k in geos if k != '1'])
        }

        # אתחול ברירת מחדל לקבצים שאינם נבחרים
        block_configs = []
        order = []

        # הצגת בלוקים רק לקובץ הנבחר
        if f_file.name == selected_file:
            with col_cfg:
                # מידע על הפלטה
                info = st.session_state.file_info[f_file.name]
                st.info(f"📐 {info['l']} × {info['w']} מילימטר | עובי: {info['t']} מילימטר | חלקים: {info['n_parts']}")

                with st.container(height=550):
                    with st.expander(f"📦 ניהול בלוקים: {f_file.name}", expanded=True):
                        block_configs = []
                        all_blocks_raw = []
                        for i, (v_key, v_block) in enumerate(visual_blocks.items()):
                            z_vals = sorted(list(set(p['z'] for p in v_block['paths'])), reverse=True)
                            is_sep_val = any(z <= 0.2 for z in z_vals)
                            def_idx = def_idx_map.get(v_key, 500 + i*10)
                            pass_key = f"passes_{i}_{f_file.name}"
                            if pass_key not in st.session_state:
                                st.session_state[pass_key] = [float(z) for z in z_vals]
                            active_key = f"active_{i}_{f_file.name}"
                            if active_key not in st.session_state:
                                st.session_state[active_key] = not v_block['missing']
                            current_idx = st.session_state.get(f"idx_{i}_{f_file.name}", def_idx)
                            all_blocks_raw.append((i, v_key, v_block, z_vals, is_sep_val, def_idx, pass_key, current_idx))

                        all_blocks_sorted = sorted(all_blocks_raw, key=lambda x: x[7])

                        for i, v_key, v_block, z_vals, is_sep_val, def_idx, pass_key, current_idx in all_blocks_sorted:
                            z_str = " → ".join([str(z) for z in z_vals])
                            sep_icon = "🔴" if is_sep_val else "🔵"
                            missing_icon = "❌ " if v_block['missing'] else ""
                            expander_label = f"[{current_idx}] {sep_icon} {missing_icon}{v_block['t_cnc']} | {v_block['desc']} | {z_str}"
                            with st.expander(expander_label):
                                active = st.checkbox("כלול בייצור", value=st.session_state[f"active_{i}_{f_file.name}"], key=f"act_{i}_{f_file.name}")
                                st.session_state[f"active_{i}_{f_file.name}"] = active
                                order_idx = st.number_input("סדר ביצוע", value=def_idx, key=f"idx_{i}_{f_file.name}")
                                current_passes = st.session_state[pass_key]
                                f_z = []
                                to_delete = None
                                for zi, z_val in enumerate(current_passes):
                                    is_cut = z_val <= 0.2
                                    col_z, col_del = st.columns([4, 1])
                                    with col_z:
                                        label = f"{'🔴 ניתוק' if is_cut else '🔵 פסיעה'} {zi+1}"
                                        new_val = st.number_input(label, value=float(z_val), key=f"z_{i}_{zi}_{f_file.name}")
                                        f_z.append(new_val)
                                    with col_del:
                                        st.write("")
                                        if st.button("✕", key=f"del_{i}_{zi}_{f_file.name}", help="מחק פסיעה"):
                                            to_delete = zi
                                if to_delete is not None:
                                    st.session_state[pass_key].pop(to_delete)
                                    st.rerun()
                                if st.button("➕ הוסף פסיעה", key=f"add_{i}_{f_file.name}"):
                                    st.session_state[pass_key].append(0.0)
                                    st.rerun()
                                if f_z: st.session_state[pass_key] = f_z
                                is_sep_val = any(z <= 0.2 for z in f_z)
                                block_configs.append({'id': i, 'active': active, 'order_idx': order_idx, 'passes': f_z, 'orig_z': z_vals, 'v_block': v_block, 'is_sep': is_sep_val})

                sorted_blocks = sorted([bc for bc in block_configs if bc['active']], key=lambda x: x['order_idx'])
                order = [b['id'] for b in sorted_blocks]

        # --- ייצור NC (Production Master 52.6 - Smart Waves) ---
        nc = ["%", "(DARWISH 53.1 - REAL CIRCLES)", f"N10 G90 G54 G21 G17"]; n_c = 20
        last_tool_id = None

        def write_block_at_depth(b_cfg, v_block, zv_final, it, nc, n_c, last_tool_id):
            if v_block['t_cnc'] != last_tool_id:
                if last_tool_id is not None:
                    nc.append(f"N{n_c} M05"); n_c += 5
                nc.extend([f"N{n_c} {v_block['t_cnc']} M06", f"N{n_c+5} G43 H{v_block['t_cnc'][1:] if v_block['t_cnc'] != 'MISSING' else '101'}", f"N{n_c+10} S{int(v_block['s'])} M03"]); n_c += 15
                last_tool_id = v_block['t_cnc']
            if v_block['is_dr']:
                for drill_op in v_block['paths']:
                    pt = drill_op['pts'][0]
                    nc.append(f"N{n_c} G00 X{pt[0]+st.session_state.off_x:.3f} Y{pt[1]+st.session_state.off_y:.3f} Z{st.session_state.safety_h:.3f}"); n_c += 5
                    nc.append(f"N{n_c} G01 Z{zv_final:.3f} F{int(it['f'])}"); n_c += 5
                    nc.append(f"N{n_c} G00 Z{st.session_state.safety_h:.3f}"); n_c += 5
            else:
                path = calculate_path_v518(it['pts'], it['rad'], it['rk'], it['is_pocket'])
                for pi, p in enumerate(path):
                    if pi == 0:
                        if (it['is_pocket'] or len(path) < 2 or ramp_len_global == 0):
                            nc.append(f"N{n_c} G00 X{p[0]+st.session_state.off_x:.3f} Y{p[1]+st.session_state.off_y:.3f} Z{st.session_state.safety_h:.3f}"); n_c += 5
                            nc.append(f"N{n_c} G01 Z{zv_final:.3f} F1500"); n_c += 5
                        else:
                            p0, p1 = np.array(path[0]), np.array(path[1])
                            vec = p1 - p0; mag = np.linalg.norm(vec)
                            if mag > 0:
                                unit_v = vec / mag; r_start = p0 - (unit_v * ramp_len_global)
                                nc.append(f"N{n_c} G00 X{r_start[0]+st.session_state.off_x:.3f} Y{r_start[1]+st.session_state.off_y:.3f} Z{st.session_state.safety_h:.3f}"); n_c += 5
                                nc.append(f"N{n_c} G01 X{p[0]+st.session_state.off_x:.3f} Y{p[1]+st.session_state.off_y:.3f} Z{zv_final:.3f} F1500"); n_c += 5
                            else:
                                nc.append(f"N{n_c} G00 X{p[0]+st.session_state.off_x:.3f} Y{p[1]+st.session_state.off_y:.3f} Z{st.session_state.safety_h:.3f}"); n_c += 5
                                nc.append(f"N{n_c} G01 Z{zv_final:.3f} F1500"); n_c += 5
                    else:
                        nc.append(f"N{n_c} G01 X{p[0]+st.session_state.off_x:.3f} Y{p[1]+st.session_state.off_y:.3f} F{int(it['f'])}"); n_c += 5
                nc.append(f"N{n_c} G00 Z{st.session_state.safety_h:.3f}"); n_c += 5
            return nc, n_c, last_tool_id

        if order:
            # הפרדה: בלוקים עם ניתוק vs בלי ניתוק
            # בלוק "עם ניתוק" = יש לו לפחות פסיעה אחת ≤ 0.2
            cutting_ids = [b_id for b_id in order if block_configs[b_id]['is_sep']]
            non_cutting_ids = [b_id for b_id in order if not block_configs[b_id]['is_sep']]

            # שלב 1: בלוקים ללא ניתוק - כל הפסיעות שלהם רצות ברצף
            for b_id in non_cutting_ids:
                b_cfg = block_configs[b_id]; v_block = b_cfg['v_block']
                it = v_block['paths'][0]
                for zv in b_cfg['passes']:
                    zv_final = zv - it['z_off'] + st.session_state.gz
                    nc, n_c, last_tool_id = write_block_at_depth(b_cfg, v_block, zv_final, it, nc, n_c, last_tool_id)

            # שלב 2: בלוקים עם ניתוק - לוגיקת גלים (כל הפסיעות חוץ מהאחרונה על כולם, ואז ניתוק)
            if cutting_ids:
                max_waves = max(len(block_configs[b_id]['passes']) for b_id in cutting_ids)
                for wave_idx in range(max_waves):
                    for b_id in cutting_ids:
                        b_cfg = block_configs[b_id]; v_block = b_cfg['v_block']
                        if wave_idx < len(b_cfg['passes']):
                            it = v_block['paths'][0]
                            zv_final = b_cfg['passes'][wave_idx] - it['z_off'] + st.session_state.gz
                            nc, n_c, last_tool_id = write_block_at_depth(b_cfg, v_block, zv_final, it, nc, n_c, last_tool_id)
            
        nc.extend([f"N{n_c} M30", "%"])
        if f_file.name == selected_file:
            with col_cfg: st.download_button(f"📥 הורד NC (גרסה 53.1)", "\n".join(nc), f"{f_file.name}.nc")

        # שמירת הגרף ב-session_state
        fig = go.Figure(); fig.update_layout(dragmode='pan', xaxis=dict(scaleanchor="y", scaleratio=1), yaxis=dict(scaleanchor="x", scaleratio=1), margin=dict(l=0, r=0, t=0, b=0), height=650)
        fig.add_shape(type="rect", x0=0, y0=0, x1=1300, y1=3050, line=dict(color="Gray", width=2), fillcolor="rgba(128,128,128,0.1)")
        fig.add_shape(type="rect", x0=st.session_state.off_x, y0=st.session_state.off_y, x1=wp_w+st.session_state.off_x, y1=wp_l+st.session_state.off_y, line=dict(color="Sienna", width=3), fillcolor="rgba(139, 69, 19, 0.4)")
        for b_id in order:
            b_cfg = block_configs[b_id]; v_block = b_cfg['v_block']
            for it in v_block['paths']:
                zv_calc = b_cfg['passes'][b_cfg['orig_z'].index(it['z'])] if it['z'] in b_cfg['orig_z'] else it['z']
                ti_calc = round(thick - (zv_calc - it['z_off'] + st.session_state.gz), 3)
                h_text = f"<b>{v_block['t_cnc']}</b>: {v_block['desc']}<br>EA: {it['ea']}<br>קוטר: {it['diam']} מילימטר<br>TI: {ti_calc:.3f} מילימטר"
                ox, oy = zip(*it['pts']); color = "red" if v_block['missing'] else ("green" if v_block['is_dr'] else ("red" if b_cfg['is_sep'] else "blue"))
                if v_block['is_dr']:
                    # ציור עיגולים גיאומטריים אמיתיים בקואורדינטות מילימטר
                    r = it['diam'] / 2
                    theta = np.linspace(0, 2*np.pi, 32)
                    for pt in it['pts']:
                        cx = pt[0] + st.session_state.off_x
                        cy = pt[1] + st.session_state.off_y
                        circle_x = list(cx + r * np.cos(theta)) + [None]
                        circle_y = list(cy + r * np.sin(theta)) + [None]
                        fig.add_trace(go.Scatter(
                            x=circle_x, y=circle_y,
                            mode='lines',
                            line=dict(color=color, width=1.5),
                            fill='toself',
                            fillcolor=f'rgba(0,180,0,0.3)' if color == 'green' else f'rgba(255,0,0,0.3)',
                            hoverinfo="text", text=h_text, showlegend=False
                        ))
                else:
                    fig.add_trace(go.Scatter(x=[x+st.session_state.off_x for x in ox]+[ox[0]+st.session_state.off_x], y=[y+st.session_state.off_y for y in oy]+[oy[0]+st.session_state.off_y], mode='lines', line=dict(color=color, width=2), hoverinfo="skip", showlegend=False))
                    s_p = calculate_path_v518(it['pts'], it['rad'], it['rk'], it['is_pocket'])
                    fig.add_trace(go.Scatter(x=[p[0]+st.session_state.off_x for p in s_p]+[None], y=[p[1]+st.session_state.off_y for p in s_p]+[None], mode='lines', line=dict(color="yellow", dash="dash"), hoverinfo="text", text=h_text, showlegend=False))
        st.session_state.fig_data[f_file.name] = fig

# הצגת הדמיה דרך placeholder קבוע בצד ימין
if upl and st.session_state.fig_data and selected_file:
    if selected_file in st.session_state.fig_data:
        with col_vis:
            vis_placeholder.plotly_chart(st.session_state.fig_data[selected_file], use_container_width=True, config={'scrollZoom': True})
