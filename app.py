import streamlit as st
import re, math
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# Darwish 49.5 - THE GEOMETRY-BASED ENGINE
# חוק יסוד: איסור מוחלט על צמצום קוד או שינוי ממשק ללא אישור אייל.
st.set_page_config(page_title="Darwish 49.5 Production", layout="wide")

# --- 1. מסד כלים (Industrial DB - Synced Keys) ---
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
        st.session_state.tool_db = st.data_editor(st.session_state.tool_db, num_rows="dynamic", key="tools_v495")
    off_x = st.number_input("הזזת פלטה ציר X (מילימטר)", value=0.0)
    off_y = st.number_input("הזזת פלטה ציר Y (מילימטר)", value=0.0)
    gz = st.number_input("תיקון Z גלובלי (מילימטר)", value=0.0)

# --- 2. ליבה מתמטית v48.7 (Intersection & Numeric) ---
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

def calculate_path_v495(pts, r, mpr_rk, is_pocket=False):
    if r <= 0 or len(pts) < 2: return pts
    pts_arr = np.array(pts); n = len(pts_arr)
    is_ccw = (sum((pts_arr[i][0]*pts_arr[(i+1)%n][1] - pts_arr[(i+1)%n][0]*pts_arr[i][1]) for i in range(n))/2.0) > 0
    side = 1 if is_ccw else -1
    if not is_pocket:
        side = 1 if "WRKL" in mpr_rk else -1 if "WRKR" in mpr_rk else 0
        if side == 0: return pts
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
    new_path = [tuple(shifted[0][0])]
    for i in range(len(shifted)-1): new_path.append(tuple(intersect(shifted[i], shifted[i+1])))
    new_path.append(tuple(shifted[-1][1]))
    return new_path

def get_f(key, block, default=0.0):
    m = re.search(f'{key}="?([^"\\s]+)"?', block)
    return _safe_float(m.group(1)) if m else default

# --- 3. ממשק הפקה והדמיה ---
st.title("🏭 דרוויש 49.5 - THE GEOMETRY-BASED ENGINE")
col_cfg, col_vis = st.columns([1, 2])

with col_cfg:
    st.subheader("הגדרות פרויקט")
    rotate = st.checkbox("סובב חלק 90 מעלות (CCW)", value=True)
    ramp_len = st.slider("אורך נחיתה (Ramp)", 0, 50, 20)
    upl = st.file_uploader("טען קבצי MPR", accept_multiple_files=True)

if upl:
    for f_file in upl:
        mpr = f_file.getvalue().decode('utf-8', errors='ignore')
        wp_match = re.search(r'\[001(.*?)\]', mpr, re.DOTALL)
        wp_block = wp_match.group(1) if wp_match else ""
        wp_l, wp_w = get_f('l', wp_block, 1000.0), get_f('w', wp_block, 500.0)
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
            
            if tag == '102':
                xa, ya = get_f('XA', bc), get_f('YA', bc)
                count = int(get_f('AN', bc, 1))
                dist = get_f('AB', bc, 0.0)
                xr, yr = get_f('XR', bc, 1.0), get_f('YR', bc, 0.0)
                z_abs = round((thick - get_f('TI', bc)), 3)
                for i in range(count):
                    curr_xa, curr_ya = xa + (i*dist*xr), ya + (i*dist*yr)
                    f_pts = [[wp_w - curr_ya, curr_xa]] if rotate else [[curr_xa, curr_ya]]
                    ops.append({'t_cnc': t_info['T_CNC'], 'desc': t_info['תיאור'], 'z': z_abs, 'pts': f_pts, 'rad': t_info['קוטר']/2, 'diam': t_info['קוטר'], 'f': t_info['Feed'], 's': t_info['RPM'], 'type': tag, 'ea': f"DRILL_{tag}_{xa}_{ya}", 'rk': "WRKL", 'is_pocket': False})
            else:
                z_abs = round(get_f('ZA', bc), 3)
                geoid = re.search(r'EA="?(\d+):?', bc).group(1).strip() if re.search(r'EA="?(\d+):?', bc) else "FREE"
                raw_pts = geos.get(geoid, [[get_f('XA', bc), get_f('YA', bc)]])
                ops.append({'t_cnc': t_info['T_CNC'], 'desc': t_info['תיאור'], 'z': z_abs, 'pts': raw_pts, 'rad': t_info['קוטר']/2, 'diam': t_info['קוטר'], 'f': t_info['Feed'], 's': t_info['RPM'], 'type': tag, 'ea': geoid, 'rk': re.search(r'RK="([^"]*)"', bc).group(1) if re.search(r'RK="([^"]*)"', bc) else "WRKL", 'is_pocket': (tag == '181')})

        # --- היררכיית קיבוץ חדשה: Tool + Geometry (EA) ---
        geo_paths = {}
        for op in ops:
            key = (op['t_cnc'], op['ea'], op['type'] == '102')
            if key not in geo_paths: geo_paths[key] = {'t_cnc': op['t_cnc'], 'desc': op['desc'], 'is_dr': op['type'] == '102', 'ea': op['ea'], 'ops': [], 's': op['s'], 'f': op['f']}
            geo_paths[key]['ops'].append(op)

        # --- איחוד ויזואלי של בלוקים זהים ---
        visual_blocks = {}
        for g_key, group in geo_paths.items():
            # מפתח איחוד: כלי + רשימת עומקים + האם קדח
            z_list = tuple(sorted([o['z'] for o in group['ops']], reverse=True))
            v_key = (group['t_cnc'], group['is_dr'], z_list)
            if v_key not in visual_blocks:
                visual_blocks[v_key] = {'t_cnc': group['t_cnc'], 'desc': group['desc'], 'is_dr': group['is_dr'], 'passes': z_list, 'paths': [], 's': group['s'], 'f': group['f']}
            visual_blocks[v_key]['paths'].append(group)

        with col_cfg:
            st.write(f"### 📦 ניהול בלוקים: {f_file.name}")
            block_configs = []
            for i, (v_key, v_block) in enumerate(visual_blocks.items()):
                count = len(v_block['paths'])
                label = "🟢 קדחים" if v_block['is_dr'] else ("🔴 חיתוך/מגרעת" if any(z <= 0.2 for z in v_block['passes']) else "🔵 עיבוד")
                with st.expander(f"{label}: {v_block['t_cnc']} ({v_block['desc']}) | {count} יח'"):
                    active = st.checkbox("כלול בייצור", value=True, key=f"act_{i}")
                    # אפשרות לשנות עומקים לכל הבלוק המאוחד
                    final_depths = [st.number_input(f"עומק פסיעה {di+1}", value=float(d), key=f"z_{i}_{di}") for di, d in enumerate(v_block['passes'])]
                    block_configs.append({'id': i, 'active': active, 'passes': final_depths, 'v_block': v_block})
            order = st.multiselect("סדר עבודה:", options=[i for i, b in enumerate(block_configs) if b['active']], default=[i for i, b in enumerate(block_configs) if b['active']], format_func=lambda x: f"{block_configs[x]['v_block']['t_cnc']}")

        # ייצור NC
        nc = ["%", f"(DARWISH 49.5 - GEOMETRY ENGINE)", "N10 G90 G54 G21 G17"]
        n_c = 20
        for b_id in order:
            b_cfg = block_configs[b_id]; v_block = b_cfg['v_block']
            nc.extend([f"N{n_c} M05", f"N{n_c+5} {v_block['t_cnc']} M06", f"N{n_c+10} G43 H{v_block['t_cnc'][1:]}", f"N{n_c+15} S{int(v_block['s'])} M03"])
            n_c += 20
            for path_group in v_block['paths']:
                for zv in b_cfg['passes']:
                    for it in path_group['ops']:
                        if it['type'] == '102':
                            nc.append(f"N{n_c} G00 X{it['pts'][0][0]+off_x:.3f} Y{it['pts'][0][1]+off_y:.3f}")
                            nc.append(f"N{n_c+5} G01 Z{zv + gz:.3f} F{int(it['f'])}"); n_c += 10
                        else:
                            path = calculate_path_v495(it['pts'], it['rad'], it['rk'], it['is_pocket'])
                            ramp = 0 if it['is_pocket'] else ramp_len
                            for pi, p in enumerate(path):
                                nx, ny = p[0] + off_x, p[1] + off_y
                                if pi == 0:
                                    nc.append(f"N{n_c} G00 X{nx-ramp:.3f} Y{ny:.3f}"); n_c += 5
                                    nc.append(f"N{n_c} G01 Z{zv + gz:.3f} X{nx:.3f} F2000"); n_c += 5
                                else: nc.append(f"N{n_c} G01 X{nx:.3f} Y{ny:.3f} F{int(it['f'])}"); n_c += 5
                        nc.append(f"N{n_c} G00 Z35.0"); n_c += 5
        nc.extend([f"N{n_c} M30", "%"])
        
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
                            px, py = zip(*calculate_path_v495(it['pts'], it['rad'], it['rk'], it['is_pocket']))
                            fig.add_trace(go.Scatter(x=[x+off_x for x in px], y=[y+off_y for y in py], mode='lines', line=dict(color="yellow", dash="dash", width=1.5), hoverinfo="text", text=h_text, showlegend=False))
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})
        st.download_button(f"📥 הורד NC (גרסה 49.5)", "\n".join(nc), f"{f_file.name}.nc")
