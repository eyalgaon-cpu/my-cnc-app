import streamlit as st
import re, math
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# Darwish 48.11 - THE FINAL CONTROL
st.set_page_config(page_title="Darwish 48.11 Final", layout="wide")

# --- 1. שחזור מסד כלים (מבוסס קובץ האקסל של אבי) ---
if 'tool_db' not in st.session_state:
    st.session_state.tool_db = pd.DataFrame([
        {"T_CNC": "T1", "MPR_Name": "137", "תיאור": "כרסום 40 מילימטר", "קוטר": 40.0, "RPM": 18000, "Feed": 12000},
        {"T_CNC": "T2", "MPR_Name": "142", "תיאור": "כרסום 6 מילימטר", "קוטר": 6.0, "RPM": 18000, "Feed": 4500},
        {"T_CNC": "T3", "MPR_Name": "158", "תיאור": "כרסום 8 מילימטר", "קוטר": 8.0, "RPM": 18000, "Feed": 4500},
        {"T_CNC": "T4", "MPR_Name": "128", "תיאור": "כרסום 12 מילימטר", "קוטר": 12.0, "RPM": 18000, "Feed": 5000},
        {"T_CNC": "T8", "MPR_Name": "147", "תיאור": "כרסום 20 מילימטר", "קוטר": 20.0, "RPM": 16000, "Feed": 6000},
        {"T_CNC": "T11", "MPR_Name": "140", "תיאור": "כרסום 3 מילימטר", "קוטר": 3.0, "RPM": 18000, "Feed": 2500},
        {"T_CNC": "T13", "MPR_Name": "130", "תיאור": "כרסום 90/45 מעלות", "קוטר": 0.2, "RPM": 16000, "Feed": 3000},
        {"T_CNC": "T6", "MPR_Name": "BV35", "תיאור": "מקדח 35 מילימטר", "קוטר": 35.0, "RPM": 4500, "Feed": 1200},
        {"T_CNC": "T49", "MPR_Name": "BV15", "תיאור": "מקדח 15 מילימטר", "קוטר": 15.0, "RPM": 4500, "Feed": 1200},
        {"T_CNC": "T47", "MPR_Name": "BV8", "תיאור": "מקדח 8 מילימטר", "קוטר": 8.0, "RPM": 4500, "Feed": 1200},
        {"T_CNC": "T44", "MPR_Name": "BV5", "תיאור": "מקדח 5 מילימטר", "קוטר": 5.0, "RPM": 4500, "Feed": 1200},
        {"T_CNC": "T45", "MPR_Name": "BV5", "תיאור": "מקדח 5 מילימטר עובר", "קוטר": 5.0, "RPM": 4500, "Feed": 1000}
    ])

with st.expander("🛠️ מסד כלים קבוע (מכונת אבי)", expanded=False):
    st.session_state.tool_db = st.data_editor(st.session_state.tool_db, num_rows="dynamic", key="tools_final_v11")

# --- 2. ליבה מתמטית v11: Inset + Boundary Guard ---
def is_point_in_poly(x, y, poly):
    n = len(poly)
    inside = False
    p1x, p1y = poly[0]
    for i in range(n + 1):
        p2x, p2y = poly[i % n]
        if y > min(p1y, p2y) and y <= max(p1y, p2y) and x <= max(p1x, p2x):
            if p1y != p2y:
                xints = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
            if p1x == p2x or x <= xints:
                inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def calculate_path_v4811(pts, r, mpr_rk, is_pocket=False, is_boring=False):
    if is_boring or r <= 0: return pts
    pts_arr = np.array(pts)
    is_ccw = (sum((pts_arr[i][0] * pts_arr[(i+1)%len(pts_arr)][1] - pts_arr[(i+1)%len(pts_arr)][0] * pts_arr[i][1]) for i in range(len(pts_arr))) / 2.0) > 0
    side = 1 if is_ccw else -1
    if not is_pocket:
        side = 1 if "WRKL" in mpr_rk else -1 if "WRKR" in mpr_rk else 0
        if side == 0: return pts
    
    n = len(pts_arr)
    shifted_lines = []
    for i in range(n - 1):
        p1, p2 = pts_arr[i], pts_arr[i+1]
        v = p2 - p1
        mag = np.linalg.norm(v)
        if mag == 0: continue
        normal = side * np.array([-v[1], v[0]]) / mag
        shifted_lines.append((p1 + normal * r, p2 + normal * r))
        
    new_path = []
    for i in range(len(shifted_lines)):
        l1, l2 = shifted_lines[i], shifted_lines[(i + 1) % len(shifted_lines)]
        def intersect(line1, line2):
            x1, y1 = line1[0]; x2, y2 = line1[1]; x3, y3 = line2[0]; x4, y4 = line2[1]
            denom = (y4-y3)*(x2-x1) - (x4-x3)*(y2-y1)
            if abs(denom) < 1e-6: return line1[1]
            ua = ((x4-x3)*(y1-y3) - (y4-y3)*(x1-x3)) / denom
            return np.array([x1 + ua*(x2-x1), y1 + ua*(y2-y1)])
        p_int = intersect(l1, l2)
        if is_pocket and not is_point_in_poly(p_int[0], p_int[1], pts):
            new_path.append(l1[1].tolist()); new_path.append(l2[0].tolist())
        else: new_path.append(p_int.tolist())
    if len(new_path) > 2: new_path.append(new_path[0])
    return new_path

def get_f(key, block, default=0.0):
    m = re.search(f'{key}="([^"]*)"', block)
    return float(m.group(1).strip()) if m else default

# --- 3. ממשק משתמש ושחזור יכולות ---
st.title("🏭 דרוויש 48.11 - THE FINAL CONTROL")
col_cfg, col_vis = st.columns([1, 2])

with col_cfg:
    st.subheader("הגדרות ייצור")
    rotate = st.checkbox("סובב חלק 90 מעלות (CCW)", value=True)
    off_x = st.number_input("תוספת הרחקה X", value=0.0)
    off_y = st.number_input("תוספת הרחקה Y", value=0.0)
    ramp_len = st.slider("אורך נחיתה (Ramp)", 0, 50, 20)
    upl = st.file_uploader("טען קבצי MPR", accept_multiple_files=True)

if upl:
    for f_file in upl:
        mpr = f_file.getvalue().decode('utf-8', errors='ignore')
        wp_block = re.search(r'\[001(.*?)\]', mpr, re.DOTALL)
        wp_w = get_f('w', wp_block.group(1)) if wp_block else 1220.0
        thick = get_f('t', mpr, 19.0)
        
        # חילוץ גאומטריות
        geos = {}
        parts = re.split(r'\](\d+)', mpr)
        for i in range(1, len(parts), 2):
            pts = []
            for el in re.split(r'\$E\d+', parts[i+1]):
                xm, ym = re.search(r'X=([\d.-]+)', el), re.search(r'Y=([\d.-]+)', el)
                if xm and ym:
                    px, py = float(xm.group(1)), float(ym.group(1))
                    if rotate: pts.append([wp_w - py, px])
                    else: pts.append([px, py])
            if pts: geos[parts[i]] = pts

        # סריקה ואיחוד פעולות (Consolidation Logic)
        raw_ops = []
        for m in re.finditer(r'<(100|102|105|130|181)(.*?)(?=<|\!|\[H)', mpr, re.DOTALL):
            tag, bc = m.group(1), m.group(2)
            t_mpr = re.search(r'(?:TNO|T_|DU)="([^"]*)"', bc).group(1).strip() if re.search(r'(?:TNO|T_|DU)="([^"]*)"', bc) else "142"
            t_info = st.session_state.tool_db[st.session_state.tool_db['MPR_Name'] == t_mpr.replace("BV","")]
            if t_info.empty: t_info = st.session_state.tool_db[st.session_state.tool_db['T_CNC'] == "T2"]
            
            z_abs = round((thick - get_f('TI', bc)), 3) if tag in ['181', '102', '100'] else round(get_f('ZA', bc), 3)
            geoid = re.search(r'EA="(\d+):', bc).group(1).strip() if re.search(r'EA="(\d+):', bc) else "Drill" if tag == '100' else "None"
            xa, ya = get_f('XA', bc), get_f('YA', bc)
            pts = geos.get(geoid, [[xa, ya]]) if tag != '102' else [[wp_w - ya, xa] if rotate else [xa, ya]]
            if tag == '100': pts = [[wp_w - ya, xa] if rotate else [xa, ya]]

            raw_ops.append({
                't_cnc': t_info.iloc[0]['T_CNC'], 'desc': t_info.iloc[0]['תיאור'], 'z': z_abs, 'pts': pts, 
                'geoid': geoid, 'rad': t_info.iloc[0]['קוטר']/2, 'f': t_info.iloc[0]['Feed'], 's': t_info.iloc[0]['RPM'],
                'rk': re.search(r'RK="([^"]*)"', bc).group(1) if re.search(r'RK="([^"]*)"', bc) else "WRKL",
                'is_pocket': (tag == '181'), 'is_boring': (tag == '100')
            })

        # איחוד בלוקים לפי כלי ומסלול
        tool_blocks = {}
        for op in raw_ops:
            key = (op['t_cnc'], str(op['pts']))
            if key not in tool_blocks:
                tool_blocks[key] = {**op, 'depths': []}
            if op['z'] not in tool_blocks[key]['depths']:
                tool_blocks[key]['depths'].append(op['z'])

        with col_cfg:
            st.write(f"### 📦 ניהול בלוקים: {f_file.name}")
            final_configs = []
            for i, (key, block) in enumerate(tool_blocks.items()):
                label = "🟢 קידוח" if block['is_boring'] else "🔵 כרסום"
                with st.expander(f"{label}: {block['t_cnc']} ({block['desc']})"):
                    active = st.checkbox("כלול", value=True, key=f"act_{i}_{f_file.name}")
                    # הצגת פסיעות מה-MPR
                    active_depths = []
                    for di, d in enumerate(sorted(block['depths'], reverse=True)):
                        new_d = st.number_input(f"עומק פסיעה {di+1}", value=d, key=f"z_{i}_{di}_{f_file.name}")
                        active_depths.append(new_d)
                    
                    # מנגנון "הוסף פסיעה" שביקשת
                    add_manual = st.checkbox("➕ הוסף פסיעה ידנית", key=f"add_{i}_{f_file.name}")
                    if add_manual:
                        manual_z = st.number_input("עומק פסיעה נוסף (למשל -0.200)", value=-0.200, key=f"man_{i}_{f_file.name}")
                        active_depths.append(manual_z)
                    
                    final_configs.append({'active': active, 'depths': active_depths, 'block': block, 'id': i})

            order = st.multiselect("סדר עבודה:", options=[c['id'] for c in final_configs if c['active']], default=[c['id'] for c in final_configs if c['active']], format_func=lambda x: f"{final_configs[x]['block']['t_cnc']}")

        # --- ייצור NC ---
        st.subheader("📥 ייצוא NC")
        for idx in order:
            cfg = final_configs[idx]; b = cfg['block']
            nc = ["%", f"(N10 {f_file.name} - {b['t_cnc']})", "N20 G90 G54 G21"]
            n_c = 30
            nc.extend([f"N{n_c} M05", f"N{n_c+5} {b['t_cnc']} M06", f"N{n_c+10} G43 H{b['t_cnc'][1:]}", f"N{n_c+15} S{int(b['s'])} M03"])
            n_c += 20
            for zv in cfg['depths']:
                path = calculate_path_v4811(b['pts'], b['rad'], b['rk'], b['is_pocket'], b['is_boring'])
                c_ramp = 0 if (b['is_pocket'] or b['is_boring']) else ramp_len
                for pi, p in enumerate(path):
                    nx, ny = p[0] + off_x, p[1] + off_y
                    if pi == 0:
                        nc.append(f"N{n_c} G00 X{nx-c_ramp:.3f} Y{ny:.3f}")
                        nc.append(f"N{n_c+5} G01 Z{zv:.3f} X{nx:.3f} F2000")
                        n_c += 10
                    elif not b['is_boring']:
                        nc.append(f"N{n_c} G01 X{nx:.3f} Y{ny:.3f} F{int(b['f'])}")
                        n_c += 5
                nc.append(f"N{n_c} G00 Z36.0"); n_c += 5
            nc.extend([f"N{n_c} M05", f"N{n_c+5} M30", "%"])
            st.download_button(f"הורד {b['t_cnc']} ({b['desc']})", "\n".join(nc), f"{f_file.name}_{b['t_cnc']}.nc", key=f"btn_{idx}_{f_file.name}")

        with col_vis:
            fig = go.Figure()
            # שחזור הזום והשכבות
            fig.update_layout(dragmode='pan', yaxis=dict(scaleanchor="x", scaleratio=1), margin=dict(l=0, r=0, t=0, b=0))
            # פלטה חום
            fig.add_shape(type="rect", x0=off_x, y0=off_y, x1=wp_w+off_x, y1=3050, line=dict(color="BurlyWood", width=3))
            
            for idx in order:
                b = final_configs[idx]['block']
                # גאומטריה מקורית (אדום/כחול)
                ox, oy = zip(*b['pts'])
                fig.add_trace(go.Scatter(x=[x+off_x for x in ox], y=[y+off_y for y in oy], mode='lines', line=dict(color="red" if b['is_pocket'] else "blue", width=2), showlegend=False))
                # מסלול צהוב מרוסק
                path = calculate_path_v4811(b['pts'], b['rad'], b['rk'], b['is_pocket'], b['is_boring'])
                px, py = zip(*path)
                color = "green" if b['is_boring'] else "yellow"
                fig.add_trace(go.Scatter(x=[x+off_x for x in px], y=[y+off_y for y in py], mode='lines+markers' if b['is_boring'] else 'lines', line=dict(color=color, dash="dash", width=1.5), showlegend=False))
            
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})
