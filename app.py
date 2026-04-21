import streamlit as st
import re, math, json, os
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# Darwish 51.8 - THE CONTINUITY SYNC (FULL INTEGRITY)
# חוק יסוד: איסור מוחלט על צמצום קוד. פנייה לאייל בלשון זכר.
st.set_page_config(page_title="Darwish 51.8 Local", layout="wide")

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

# --- 2. אתחול מסד כלים (מעודכן לפי ייצוא 51.8) ---
if 'tool_db' not in st.session_state:
    if not load_config_auto():
        st.session_state.tool_db = pd.DataFrame([
            {"T_CNC": "T1", "MPR_Name": "137", "תיאור": "כרסום 40 מילימטר (ניקוי שולחן)", "קוטר": 40.0, "Z_Offset": 0.0, "RPM": 12000, "Feed": 4000},
            {"T_CNC": "T2", "MPR_Name": "142", "תיאור": "כרסום יהלום 6 מילימטר", "קוטר": 6.0, "Z_Offset": 0.0, "RPM": 18000, "Feed": 4500},
            {"T_CNC": "T3", "MPR_Name": "158", "תיאור": "כרסום 8 מילימטר", "קוטר": 8.0, "Z_Offset": 0.0, "RPM": 18000, "Feed": 3000},
            {"T_CNC": "T4", "MPR_Name": "128", "תיאור": "כרסום 12 מילימטר", "קוטר": 12.0, "Z_Offset": 0.0, "RPM": 18000, "Feed": 3500},
            {"T_CNC": "T6", "MPR_Name": "35", "תיאור": "מקדח צירים 35 מילימטר", "קוטר": 35.0, "Z_Offset": 0.0, "RPM": 3000, "Feed": 1000},
            {"T_CNC": "T8", "MPR_Name": "MISSING", "תיאור": "כרסום 19 מילימטר", "קוטר": 19.0, "Z_Offset": 0.0, "RPM": 16000, "Feed": 3000},
            {"T_CNC": "MISSING", "MPR_Name": "136", "תיאור": "כרסום 16 מילימטר", "קוטר": 16.0, "Z_Offset": 0.0, "RPM": 18000, "Feed": 2000},
            {"T_CNC": "T11", "MPR_Name": "140", "תיאור": "כרסום 3 מילימטר (T11)", "קוטר": 3.0, "Z_Offset": 0.0, "RPM": 18000, "Feed": 2500},
            {"T_CNC": "T13", "MPR_Name": "130", "תיאור": "כרסום V 45 מעלות (גירונג)", "קוטר": 0.2, "Z_Offset": 0.0, "RPM": 18000, "Feed": 4000},
            {"T_CNC": "MISSING", "MPR_Name": "139", "תיאור": "כרסום 10 מילימטר (חסר פיזית)", "קוטר": 10.0, "Z_Offset": 0.0, "RPM": 18000, "Feed": 3000}
        ])

with st.sidebar:
    st.header("🛠️ ניהול ייצור (Local Sync)")
    with st.expander("פרופיל מכונה וכלים", expanded=True):
        new_df = st.data_editor(st.session_state.tool_db, num_rows="dynamic", key="tools_v518")
        if not new_df.equals(st.session_state.tool_db):
            st.session_state.tool_db = new_df
            save_config_auto()
        if st.button("אפס להגדרות יצרן"):
            if os.path.exists(CONFIG_FILE): os.remove(CONFIG_FILE)
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

# --- 3. ליבה מתמטית v51.8 (Sequence Master) ---
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
st.title("🏭 דרוויש 51.8 - THE CONTINUITY SYNC")
col_cfg, col_vis = st.columns([1, 2])

with col_cfg:
    st.subheader("הגדרות פרויקט")
    rotate = st.checkbox("סובב חלק 90 מעלות (CCW)", value=True)
    ramp_len_global = st.slider("אורך נחיתה (Ramp)", 0, 50, 20)
    upl = st.file_uploader("טען קבצי MPR", accept_multiple_files=True, type=['mpr'])

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
            if v_key not in visual_blocks: visual_blocks[v_key] = {'t_cnc': op['t_cnc'], 'desc': op['desc'], 'type': op['type'], 'is_dr': op['type'] == '102', 'paths': [], 's': op['s'], 'f': op['f'], 'diam': op['diam'], 'ea_id': op['ea'], 'missing': op['missing']}
            visual_blocks[v_key]['paths'].append(op)
        for vk in visual_blocks:
            if visual_blocks[vk]['is_dr']: visual_blocks[vk]['paths'] = optimize_drill_path_v518(visual_blocks[vk]['paths'])

        with col_cfg:
            st.write(f"### 📦 ניהול בלוקים: {f_file.name}")
            block_configs = []
            for i, (v_key, v_block) in enumerate(visual_blocks.items()):
                z_vals = sorted(list(set(p['z'] for p in v_block['paths'])), reverse=True); is_sep_val = any(z < 0.2 for z in z_vals)
                def_idx = 100 + (i*10) if is_sep_val else 10 + (i*10)
                with (st.error(f"❌ {v_block['t_cnc']} | {v_block['desc']} (חסר במכונה)") if v_block['missing'] else st.expander(f"{v_block['t_cnc']} | {v_block['desc']} (EA:{v_block['ea_id']})")):
                    active = st.checkbox("כלול בייצור", value=not v_block['missing'], key=f"act_{i}")
                    order_idx = st.number_input("סדר ביצוע", value=def_idx, key=f"idx_{i}")
                    f_z = [st.number_input(f"גובה Z {zi+1}", value=float(z), key=f"z_{i}_{zi}") for zi, z in enumerate(z_vals)]
                    block_configs.append({'id': i, 'active': active, 'order_idx': order_idx, 'passes': f_z, 'orig_z': z_vals, 'v_block': v_block, 'is_sep': is_sep_val})

            sorted_blocks = sorted([bc for bc in block_configs if bc['active']], key=lambda x: x['order_idx'])
            order = st.multiselect("סדר עבודה:", options=[b['id'] for b in block_configs if b['active']], default=[b['id'] for b in sorted_blocks], format_func=lambda x: f"[{block_configs[x]['order_idx']}] {block_configs[x]['v_block']['t_cnc']} - {block_configs[x]['v_block']['ea_id']}")

        # --- ייצור NC (Production Master 51.8 - Continuity Upgrade) ---
        nc = ["%", "(DARWISH 51.8 - CONTINUITY SYNC)", f"N10 G90 G54 G21 G17"]; n_c = 20
        last_tool_id = None
        
        for b_id in order:
            b_cfg = block_configs[b_id]; v_block = b_cfg['v_block']
            
            # בדיקת רציפות כלי למניעת עצירות M05/M06 מיותרות
            if v_block['t_cnc'] != last_tool_id:
                if last_tool_id is not None:
                    nc.append(f"N{n_c} M05"); n_c += 5
                nc.extend([f"N{n_c} {v_block['t_cnc']} M06", f"N{n_c+5} G43 H{v_block['t_cnc'][1:] if v_block['t_cnc'] != 'MISSING' else '101'}", f"N{n_c+10} S{int(v_block['s'])} M03"]); n_c += 15
            
            for it in v_block['paths']:
                zv_final = b_cfg['passes'][b_cfg['orig_z'].index(it['z'])] - it['z_off'] + st.session_state.gz
                path = calculate_path_v518(it['pts'], it['rad'], it['rk'], it['is_pocket'])
                for pi, p in enumerate(path):
                    if pi == 0:
                        ramp = 0 if (it['is_pocket'] or it['type'] == '102') else ramp_len_global
                        nc.append(f"N{n_c} G00 X{p[0]+st.session_state.off_x-ramp:.3f} Y{p[1]+st.session_state.off_y:.3f} Z{st.session_state.safety_h:.3f}"); n_c += 5
                        nc.append(f"N{n_c} G01 Z{zv_final:.3f} X{p[0]+st.session_state.off_x:.3f} Y{p[1]+st.session_state.off_y:.3f} F1500"); n_c += 5
                    else: nc.append(f"N{n_c} G01 X{p[0]+st.session_state.off_x:.3f} Y{p[1]+st.session_state.off_y:.3f} F{int(it['f'])}"); n_c += 5
                nc.append(f"N{n_c} G00 Z{st.session_state.safety_h:.3f}"); n_c += 5
            
            last_tool_id = v_block['t_cnc']
            
        nc.extend([f"N{n_c} M30", "%"])
        with col_cfg: st.download_button(f"📥 הורד NC (גרסה 51.8)", "\n".join(nc), f"{f_file.name}.nc")

        with col_vis:
            fig = go.Figure(); fig.update_layout(dragmode='pan', xaxis=dict(scaleanchor="y", scaleratio=1), yaxis=dict(scaleanchor="x", scaleratio=1), margin=dict(l=0, r=0, t=0, b=0))
            fig.add_shape(type="rect", x0=0, y0=0, x1=1300, y1=3050, line=dict(color="Gray", width=2), fillcolor="rgba(128,128,128,0.1)")
            fig.add_shape(type="rect", x0=st.session_state.off_x, y0=st.session_state.off_y, x1=wp_w+st.session_state.off_x, y1=wp_l+st.session_state.off_y, line=dict(color="Sienna", width=3), fillcolor="rgba(139, 69, 19, 0.4)")
            for b_id in order:
                b_cfg = block_configs[b_id]; v_block = b_cfg['v_block']
                for it in v_block['paths']:
                    zv_calc = b_cfg['passes'][b_cfg['orig_z'].index(it['z'])] - it['z_off'] + st.session_state.gz; ti_calc = round(thick - zv_calc, 3)
                    h_text = f"<b>{v_block['t_cnc']}</b>: {v_block['desc']}<br>EA: {it['ea']}<br>קוטר: {it['diam']} מילימטר<br>Z סופי: {zv_calc:.3f} מילימטר<br>TI: {ti_calc:.3f} מילימטר"
                    ox, oy = zip(*it['pts']); color = "red" if v_block['missing'] else ("green" if v_block['is_dr'] else ("red" if b_cfg['is_sep'] else "blue"))
                    if v_block['is_dr']: fig.add_trace(go.Scatter(x=[x+st.session_state.off_x for x in ox], y=[y+st.session_state.off_y for y in oy], mode='markers+lines', marker=dict(size=it['diam'], color=color), line=dict(width=1, dash='dot'), hoverinfo="text", text=h_text, showlegend=False))
                    else:
                        fig.add_trace(go.Scatter(x=[x+st.session_state.off_x for x in ox]+[ox[0]+st.session_state.off_x], y=[y+st.session_state.off_y for y in oy]+[oy[0]+st.session_state.off_y], mode='lines', line=dict(color=color, width=2), hoverinfo="skip", showlegend=False))
                        s_p = calculate_path_v518(it['pts'], it['rad'], it['rk'], it['is_pocket'])
                        fig.add_trace(go.Scatter(x=[p[0]+st.session_state.off_x for p in s_p]+[None], y=[p[1]+st.session_state.off_y for p in s_p]+[None], mode='lines', line=dict(color="yellow", dash="dash"), hoverinfo="text", text=h_text, showlegend=False))
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})
