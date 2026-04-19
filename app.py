import streamlit as st
import re, math
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# Darwish 49.8 Rev B - THE FULL MASTER ENGINE
# חוק יסוד: איסור מוחלט על צמצום קוד. שחזור מלא של ממשק 49.7 + מנוע ווקטורי 49.8.
st.set_page_config(page_title="Darwish 49.8 Master", layout="wide")

# --- 1. מסד כלים (Industrial DB - Locked) ---
if 'tool_db' not in st.session_state:
    st.session_state.tool_db = pd.DataFrame([
        {"T_CNC": "T1", "MPR_Name": "137", "תיאור": "כרסום 40 מילימטר", "קוטר": 40.0, "RPM": 12000, "Feed": 4000},
        {"T_CNC": "T2", "MPR_Name": "142", "תיאור": "כרסום יהלום 6 מילימטר", "קוטר": 6.0, "RPM": 18000, "Feed": 4500},
        {"T_CNC": "T3", "MPR_Name": "158", "תיאור": "כרסום 8 מילימטר", "קוטר": 8.0, "RPM": 18000, "Feed": 3000},
        {"T_CNC": "T4", "MPR_Name": "128", "תיאור": "כרסום 12 מילימטר", "קוטר": 12.0, "RPM": 18000, "Feed": 3500},
        {"T_CNC": "T6", "MPR_Name": "35", "תיאור": "מקדח צירים 35 מילימטר", "קוטר": 35.0, "RPM": 3000, "Feed": 1000},
        {"T_CNC": "T8", "MPR_Name": "19.0", "תיאור": "כרסום 19 מילימטר", "קוטר": 19.0, "RPM": 16000, "Feed": 3000},
        {"T_CNC": "T10", "MPR_Name": "6.0", "תיאור": "כרסום/מקדח 6 מילימטר", "קוטר": 6.0, "RPM": 18000, "Feed": 2000},
        {"T_CNC": "T11", "MPR_Name": "140", "תיאור": "כרסום 3 מילימטר (T11)", "קוטר": 3.0, "RPM": 18000, "Feed": 2500},
        {"T_CNC": "T44", "MPR_Name": "5.0", "תיאור": "מקדח 5 מילימטר", "קוטר": 5.0, "RPM": 4500, "Feed": 1200},
        {"T_CNC": "T47", "MPR_Name": "8.0", "תיאור": "מקדח 8 מילימטר", "קוטר": 8.0, "RPM": 4500, "Feed": 1200},
        {"T_CNC": "T49", "MPR_Name": "15.0", "תיאור": "מקדח 15 מילימטר", "קוטר": 15.0, "RPM": 3000, "Feed": 800}
    ])

with st.sidebar:
    st.header("🛠️ ניהול ייצור")
    with st.expander("מסד כלים", expanded=False):
        st.session_state.tool_db = st.data_editor(st.session_state.tool_db, num_rows="dynamic", key="tools_v498master")
    off_x = st.number_input("הזזת פלטה ציר X (מילימטר)", value=0.0)
    off_y = st.number_input("הזזת פלטה ציר Y (מילימטר)", value=0.0)
    gz = st.number_input("תיקון Z גלובלי (מילימטר)", value=0.0)

# --- 2. ליבה מתמטית v49.8 (Vector Pre-Processor) ---
def _safe_float(val):
    try: return float(re.sub(r'[^0-9.\-]', '', str(val)))
    except: return 0.0

def find_tool_numeric(mpr_id, df):
    try:
        target = round(_safe_float(mpr_id), 1)
        for _, row in df.iterrows():
            if round(_safe_float(row['MPR_Name']), 1) == target: return row
    except: pass
    return df[df['T_CNC'] == "T2"].iloc[0]

def calculate_path_v498_master(pts, r, mpr_rk, is_pocket=False):
    if r <= 0 or len(pts) < 2: return pts, []
    pts_arr = np.array(pts); n = len(pts_arr)
    area = sum((pts_arr[i][0]*pts_arr[(i+1)%n][1] - pts_arr[(i+1)%n][0]*pts_arr[i][1]) for i in range(n))/2.0
    is_ccw = area > 0
    side = (1 if is_ccw else -1) if is_pocket else (1 if "WRKL" in mpr_rk else -1 if "WRKR" in mpr_rk else 0)
    if side == 0: return pts, []

    full_path = [] # (X, Y, is_arc, center_x, center_y, direction)
    for i in range(n - 1):
        p1, p2 = pts_arr[i], pts_arr[i+1]
        v = p2 - p1; mag = np.linalg.norm(v)
        if mag == 0: continue
        norm = side * np.array([-v[1], v[0]]) / mag
        s_off, e_off = p1 + norm * r, p2 + norm * r
        
        if i > 0 and not np.allclose(full_path[-1][:2], s_off):
            full_path.append((s_off[0], s_off[1], True, p1[0], p1[1], "G03" if side > 0 else "G02"))
        
        if i == 0: full_path.append((s_off[0], s_off[1], False, 0, 0, ""))
        full_path.append((e_off[0], e_off[1], False, 0, 0, ""))
    return full_path

def get_f(key, block, default=0.0):
    m = re.search(f'{key}="?([^"\\s]+)"?', block)
    return _safe_float(m.group(1)) if m else default

# --- 3. ממשק הפקה והדמיה ---
st.title("🏭 דרוויש 49.8 Rev B - THE MASTER ENGINE")
col_cfg, col_vis = st.columns([1, 2])

with col_cfg:
    st.subheader("הגדרות פרויקט")
    rotate = st.checkbox("סובב חלק 90 מעלות (CCW)", value=True)
    ramp_len_global = st.slider("אורך נחיתה (Ramp)", 0, 50, 20)
    upl = st.file_uploader("טען קבצי MPR", accept_multiple_files=True)

if upl:
    for f_file in upl:
        mpr = f_file.getvalue().decode('utf-8', errors='ignore')
        wp_match = re.search(r'\[001(.*?)\]', mpr, re.DOTALL)
        wp_block = wp_match.group(1) if wp_match else ""
        wp_l, wp_w = get_f('l', wp_block, 2440.0), get_f('w', wp_block, 1220.0)
        thick = get_f('t', mpr, 19.0)

        geos = {}
        parts = re.split(r'\](\d+)', mpr)
        for i in range(1, len(parts), 2):
            pts = []
            for el in re.split(r'\$E\d+', parts[i+1]):
                xm, ym = re.search(r'X=([\d.-]+)', el), re.search(r'Y=([\d.-]+)', el)
                if xm and ym:
                    px, py = float(xm.group(1)), float(ym.group(1))
                    pts.append([wp_w - py, px] if rotate else [px, py])
            if pts: geos[parts[i]] = pts

        ops = []
        for m in re.finditer(r'<(102|105|130|181)(.*?)(?=<|\!|\[H)', mpr, re.DOTALL):
            tag, bc = m.group(1), m.group(2)
            t_mpr = re.search(r'(?:TNO|T_|DU)="?([^"\\s]+)"?', bc).group(1).strip() if re.search(r'(?:TNO|T_|DU)="?([^"\\s]+)"?', bc) else "142"
            t_info = find_tool_numeric(t_mpr, st.session_state.tool_db)
            z_abs = round((thick - get_f('TI', bc)), 3) if tag in ['102', '181'] else round(get_f('ZA', bc), 3)

            if tag == '102':
                xa, ya = get_f('XA', bc), get_f('YA', bc)
                an, ab = int(get_f('AN', bc, 1)), get_f('AB', bc, 0.0)
                xr, yr = get_f('XR', bc, 1.0), get_f('YR', bc, 0.0)
                for i in range(an):
                    curr_xa, curr_ya = xa + (i*ab*xr), ya + (i*ab*yr)
                    f_pts = [[wp_w - curr_ya, curr_xa]] if rotate else [[curr_xa, curr_ya]]
                    ops.append({'t_cnc': t_info['T_CNC'], 'desc': t_info['תיאור'], 'z': z_abs, 'pts': f_pts, 'diam': t_info['קוטר'], 'rad': t_info['קוטר']/2, 'f': t_info['Feed'], 's': t_info['RPM'], 'type': tag, 'ea': f"DR_{tag}_{round(curr_xa,1)}_{round(curr_ya,1)}", 'rk': "WRKL", 'is_pocket': False})
            else:
                geoid = re.search(r'EA="?(\d+):?', bc).group(1).strip() if re.search(r'EA="?(\d+):?', bc) else "FREE"
                ops.append({'t_cnc': t_info['T_CNC'], 'desc': t_info['תיאור'], 'z': z_abs, 'pts': geos.get(geoid, [[get_f('XA', bc), get_f('YA', bc)]]), 'diam': t_info['קוטר'], 'rad': t_info['קוטר']/2, 'f': t_info['Feed'], 's': t_info['RPM'], 'type': tag, 'ea': geoid, 'rk': re.search(r'RK="([^"]*)"', bc).group(1) if re.search(r'RK="([^"]*)"', bc) else "WRKL", 'is_pocket': (tag == '181')})

        # --- היררכיית קיבוץ (שחזור 49.7) ---
        geo_paths = {}
        for op in ops:
            key = (op['t_cnc'], op['ea'], op['type'] == '102')
            if key not in geo_paths: geo_paths[key] = {'t_cnc': op['t_cnc'], 'desc': op['desc'], 'is_dr': op['type'] == '102', 'ea': op['ea'], 'ops': [], 's': op['s'], 'f': op['f'], 'diam': op['diam'], 'rad': op['rad']}
            geo_paths[key]['ops'].append(op)

        visual_blocks = {}
        for g_key, group in geo_paths.items():
            z_list = tuple(sorted(list(set(round(o['z'], 3) for o in group['ops'])), reverse=True))
            v_key = (group['t_cnc'], group['is_dr'], z_list)
            if v_key not in visual_blocks:
                visual_blocks[v_key] = {'t_cnc': group['t_cnc'], 'desc': group['desc'], 'is_dr': group['is_dr'], 'passes': z_list, 'paths': [], 's': group['s'], 'f': group['f'], 'diam': group['diam'], 'rad': group['rad']}
            visual_blocks[v_key]['paths'].append(group)

        with col_cfg:
            st.write(f"### 📦 ניהול בלוקים: {f_file.name}")
            block_configs = []
            for i, (v_key, v_block) in enumerate(visual_blocks.items()):
                drill_count = sum(len(p['ops']) for p in v_block['paths']) if v_block['is_dr'] else len(v_block['paths'])
                label = "🟢 קדחים" if v_block['is_dr'] else ("🔴 חיתוך/מגרעת" if any(z <= 0.2 for z in v_block['passes']) else "🔵 עיבוד")
                with st.expander(f"{label}: {v_block['t_cnc']} ({v_block['desc']}) | {drill_count} יח'"):
                    active = st.checkbox("כלול בייצור", value=True, key=f"act_{i}")
                    final_depths = [st.number_input(f"עומק פסיעה {di+1}", value=float(d), key=f"z_{i}_{di}") for di, d in enumerate(v_block['passes'])]
                    block_configs.append({'id': i, 'active': active, 'passes': final_depths, 'v_block': v_block})
            order = st.multiselect("סדר עבודה:", options=[i for i, b in enumerate(block_configs) if b['active']], default=[i for i, b in enumerate(block_configs) if b['active']], format_func=lambda x: f"{block_configs[x]['v_block']['t_cnc']} ({block_configs[x]['v_block']['desc']})")

        # --- ייצור NC (מניעת יתירות + ווקטור) ---
        nc = ["%", "(DARWISH 49.8 Rev B - MASTER)", "N10 G90 G54 G21 G17"]; n_c = 20
        written_ops = set()
        for b_id in order:
            b_cfg = block_configs[b_id]; v_block = b_cfg['v_block']
            nc.extend([f"N{n_c} M05", f"N{n_c+5} {v_block['t_cnc']} M06", f"N{n_c+10} G43 H{v_block['t_cnc'][1:]}", f"N{n_c+15} S{int(v_block['s'])} M03"])
            n_c += 20
            for path_group in v_block['paths']:
                for zv in b_cfg['passes']:
                    for it in path_group['ops']:
                        sig = (it['t_cnc'], it['ea'], it['type'], zv)
                        if sig in written_ops: continue
                        written_ops.add(sig)
                        if it['type'] == '102':
                            nc.append(f"N{n_c} G00 X{it['pts'][0][0]+off_x:.3f} Y{it['pts'][0][1]+off_y:.3f}")
                            nc.append(f"N{n_c+5} G01 Z{zv+gz:.3f} F{int(it['f'])}"); n_c += 10
                        else:
                            pts_arr = np.array(it['pts']); center = np.mean(pts_arr, axis=0)
                            is_small = it['is_pocket'] and (np.linalg.norm(np.max(pts_arr, axis=0) - np.min(pts_arr, axis=0)) < 3*it['diam'])
                            if is_small:
                                nc.append(f"N{n_c} (CENTER PLUNGE)"); nc.append(f"N{n_c+5} G00 X{center[0]+off_x:.3f} Y{center[1]+off_y:.3f}")
                                nc.append(f"N{n_c+10} G01 Z{zv+gz:.3f} F1000"); n_c += 15
                            path = calculate_path_v498_master(it['pts'], it['rad'], it['rk'], it['is_pocket'])
                            for pi, p in enumerate(path):
                                px, py, is_arc, cx, cy, d = p
                                if pi == 0 and not is_small:
                                    nc.append(f"N{n_c} G00 X{px+off_x-ramp_len_global:.3f} Y{py+off_y:.3f}")
                                    nc.append(f"N{n_c+5} G01 Z{zv+gz:.3f} X{px+off_x:.3f} F1500"); n_c += 10
                                elif pi == 0 and is_small:
                                    nc.append(f"N{n_c} G01 X{px+off_x:.3f} Y{py+off_y:.3f} F{int(it['f'])}"); n_c += 5
                                else:
                                    if is_arc:
                                        prev_p = path[pi-1]; ii, jj = cx - prev_p[0], cy - prev_p[1]
                                        nc.append(f"N{n_c} G61 (EXACT STOP)"); nc.append(f"N{n_c+5} {d} X{px+off_x:.3f} Y{py+off_y:.3f} I{ii:.3f} J{jj:.3f} F{int(it['f']*0.6)}"); n_c += 10
                                        nc.append(f"N{n_c} G64")
                                    else:
                                        nc.append(f"N{n_c} G01 X{px+off_x:.3f} Y{py+off_y:.3f} F{int(it['f'])}"); n_c += 5
                        nc.append(f"N{n_c} G00 Z35.0"); n_c += 5
        nc.extend([f"N{n_c} M30", "%"])
        st.download_button(f"📥 הורד NC (גרסה 49.8 Rev B)", "\n".join(nc), f"{f_file.name}.nc")

        with col_vis:
            fig = go.Figure()
            fig.update_layout(dragmode='pan', xaxis=dict(scaleanchor="y", scaleratio=1), yaxis=dict(scaleanchor="x", scaleratio=1), margin=dict(l=0, r=0, t=0, b=0))
            fig.add_shape(type="rect", x0=0, y0=0, x1=1300, y1=3050, line=dict(color="Gray", width=2), fillcolor="rgba(128, 128, 128, 0.1)")
            fig.add_shape(type="rect", x0=off_x, y0=off_y, x1=wp_w+off_x, y1=wp_l+off_y, line=dict(color="Sienna", width=3), fillcolor="rgba(139, 69, 19, 0.4)")
            for b_id in order:
                b_cfg = block_configs[b_id]; v_block = b_cfg['v_block']
                for path_group in v_block['paths']:
                    for it in path_group['ops']:
                        ox, oy = zip(*it['pts']); color = "green" if v_block['is_dr'] else ("red" if any(z <= 0.2 for z in b_cfg['passes']) else "blue")
                        p_steps = "<br>".join([f"פסיעה {idx+1}: {z_val} מילימטר" for idx, z_val in enumerate(b_cfg['passes'])])
                        h_text = f"<b>{v_block['t_cnc']}</b>: {v_block['desc']}<br>EA: {it['ea']}<br>{p_steps}"
                        if it['type'] == '102':
                            fig.add_trace(go.Scatter(x=[x+off_x for x in ox], y=[y+off_y for y in oy], mode='markers', marker=dict(size=it['diam'], sizemode='diameter', color=color), hoverinfo="text", text=h_text, showlegend=False))
                        else:
                            fig.add_trace(go.Scatter(x=[x+off_x for x in ox], y=[y+off_y for y in oy], mode='lines', line=dict(color=color, width=2), hoverinfo="skip", showlegend=False))
                            path_obj, _ = calculate_path_v498_master(it['pts'], it['rad'], it['rk'], it['is_pocket'])
                            px, py = [p[0]+off_x for p in path_obj], [p[1]+off_y for p in path_obj]
                            fig.add_trace(go.Scatter(x=px, y=py, mode='lines', line=dict(color="yellow", dash="dash", width=1.5), hoverinfo="text", text=h_text, showlegend=False))
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})
