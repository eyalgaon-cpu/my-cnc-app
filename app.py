import streamlit as st
import re, math
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# Darwish 48.18 - THE FOUNDATION FIX
st.set_page_config(page_title="Darwish 48.18 Fix", layout="wide")

# --- 1. מסד כלים אינטראקטיבי ---
if 'tool_db' not in st.session_state:
    st.session_state.tool_db = pd.DataFrame([
        {"T_CNC": "T1", "MPR_Name": "137", "תיאור": "כרסום 40 מילימטר", "קוטר": 40.0, "RPM": 18000, "Feed": 12000},
        {"T_CNC": "T2", "MPR_Name": "142", "תיאור": "כרסום 6 מילימטר", "קוטר": 6.0, "RPM": 18000, "Feed": 4500},
        {"T_CNC": "T3", "MPR_Name": "158", "תיאור": "כרסום 8 מילימטר", "קוטר": 8.0, "RPM": 18000, "Feed": 4500},
        {"T_CNC": "T4", "MPR_Name": "128", "תיאור": "כרסום 12 מילימטר", "קוטר": 12.0, "RPM": 18000, "Feed": 5000},
        {"T_CNC": "T8", "MPR_Name": "147", "תיאור": "כרסום 20 מילימטר", "קוטר": 20.0, "RPM": 16000, "Feed": 6000},
        {"T_CNC": "T11", "MPR_Name": "140", "תיאור": "כרסום 3 מילימטר", "קוטר": 3.0, "RPM": 18000, "Feed": 2500},
        {"T_CNC": "T13", "MPR_Name": "130", "תיאור": "כרסום V", "קוטר": 0.2, "RPM": 16000, "Feed": 3000},
        {"T_CNC": "T6", "MPR_Name": "35", "תיאור": "מקדח 35 מילימטר", "קוטר": 35.0, "RPM": 4500, "Feed": 1200},
        {"T_CNC": "T49", "MPR_Name": "15", "תיאור": "מקדח 15 מילימטר", "קוטר": 15.0, "RPM": 4500, "Feed": 1200},
        {"T_CNC": "T47", "MPR_Name": "8", "תיאור": "מקדח 8 מילימטר", "קוטר": 8.0, "RPM": 4500, "Feed": 1200},
        {"T_CNC": "T44", "MPR_Name": "5", "תיאור": "מקדח 5 מילימטר", "קוטר": 5.0, "RPM": 4500, "Feed": 1200},
        {"T_CNC": "T45", "MPR_Name": "5", "תיאור": "מקדח 5 עובר", "קוטר": 5.0, "RPM": 4500, "Feed": 1000}
    ])

st.session_state.tool_db = st.data_editor(st.session_state.tool_db, num_rows="dynamic", key="tools_4818")

def get_f(key, block, default=0.0):
    m = re.search(f'{key}="([^"]*)"', block)
    return float(m.group(1).strip()) if m else default

# --- 2. ליבה מתמטית מעודכנת ---
def calculate_path_v4818(pts, r, mpr_rk, is_pocket=False, is_boring=False):
    if is_boring or r <= 0 or len(pts) < 2: return pts
    pts_arr = np.array(pts)
    is_ccw = (sum((pts_arr[i][0] * pts_arr[(i+1)%len(pts_arr)][1] - pts_arr[(i+1)%len(pts_arr)][0] * pts_arr[i][1]) for i in range(len(pts_arr))) / 2.0) > 0
    side = 1 if is_ccw else -1
    if not is_pocket:
        side = 1 if "WRKL" in mpr_rk else -1 if "WRKR" in mpr_rk else 0
        if side == 0: return pts
    
    n = len(pts_arr); shifted_lines = []
    for i in range(n - 1):
        p1, p2 = pts_arr[i], pts_arr[i+1]
        v = p2 - p1; mag = np.linalg.norm(v)
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
        new_path.append(intersect(l1, l2).tolist())
    if len(new_path) > 2: new_path.append(new_path[0])
    return new_path

# --- 3. ממשק עיבוד ---
col_cfg, col_vis = st.columns([1, 2])

with col_cfg:
    st.subheader("⚙️ הגדרות ייצור")
    rotate = st.checkbox("סובב חלק 90 מעלות (CCW)", value=True)
    off_x = st.number_input("תוספת הרחקה X מילימטר", value=0.0)
    off_y = st.number_input("תוספת הרחקה Y מילימטר", value=0.0)
    ramp_len = st.slider("אורך נחיתה מילימטר (Ramp)", 0, 50, 20)
    upl = st.file_uploader("טען קבצי MPR", accept_multiple_files=True)

if upl:
    for f_file in upl:
        mpr = f_file.getvalue().decode('utf-8', errors='ignore')
        wp_block = re.search(r'\[001(.*?)\]', mpr, re.DOTALL)
        wp_w = get_f('w', wp_block.group(1)) if wp_block else 1220.0
        wp_l = get_f('l', wp_block.group(1)) if wp_block else 3050.0
        thick = get_f('t', mpr, 19.0)
        
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

        raw_ops = []
        for m in re.finditer(r'<(100|102|105|130|181)(.*?)(?=<|\!|\[H)', mpr, re.DOTALL):
            tag, bc = m.group(1), m.group(2)
            t_match = re.search(r'(?:TNO|T_|DU)="([^"]*)"', bc)
            t_mpr_raw = t_match.group(1).strip() if t_match else "142"
            # ניקוי שם הכלי (למשל 5.0000 הופך ל-5)
            t_mpr_clean = str(int(float(t_mpr_raw))) if t_mpr_raw.replace(".","").isdigit() else t_mpr_raw.replace("BV","")
            
            t_info = st.session_state.tool_db[st.session_state.tool_db['MPR_Name'] == t_mpr_clean]
            if t_info.empty: t_info = st.session_state.tool_db[st.session_state.tool_db['T_CNC'] == "T2"]
            
            z_abs = round((thick - get_f('TI', bc)), 3) if tag in ['181', '102', '100'] else round(get_f('ZA', bc), 3)
            geoid = re.search(r'EA="(\d+):', bc).group(1).strip() if re.search(r'EA="(\d+):', bc) else "Drill"
            xa, ya = get_f('XA', bc), get_f('YA', bc)
            pts = geos.get(geoid, [[wp_w - ya, xa] if rotate else [xa, ya]])
            if tag in ['100', '102']: pts = [[wp_w - ya, xa] if rotate else [xa, ya]]

            is_boring_bit = tag in ['100', '102'] or t_info.iloc[0]['T_CNC'] in ['T6', 'T49', 'T47', 'T44', 'T45']
            purpose = "Drill" if is_boring_bit else ("Final" if z_abs <= 0.05 and tag != '102' else "Inside")
            
            raw_ops.append({
                't_cnc': t_info.iloc[0]['T_CNC'], 'z': z_abs, 'pts': pts, 'rad': t_info.iloc[0]['קוטר']/2, 
                'f': t_info.iloc[0]['Feed'], 's': t_info.iloc[0]['RPM'], 'is_boring': is_boring_bit,
                'rk': re.search(r'RK="([^"]*)"', bc).group(1) if re.search(r'RK="([^"]*)"', bc) else "WRKL",
                'purpose': purpose, 'tag': tag
            })

        tool_blocks = {}
        for op in raw_ops:
            key = (op['t_cnc'], op['purpose'])
            if key not in tool_blocks: tool_blocks[key] = {'t_cnc': op['t_cnc'], 'purpose': op['purpose'], 'items': [], 's': op['s']}
            tool_blocks[key]['items'].append(op)

        with col_cfg:
            st.write(f"### 📦 ניהול בלוקים: {f_file.name}")
            final_configs = []
            for i, (key, b) in enumerate(tool_blocks.items()):
                label = "🟢 Drill" if b['purpose']=="Drill" else "🔴 Final" if b['purpose']=="Final" else "🔵 Inside"
                with st.expander(f"{label}: {b['t_cnc']}"):
                    active = st.checkbox("כלול בייצור", value=True, key=f"act_{i}_{f_file.name}")
                    all_depths = sorted(list(set(it['z'] for it in b['items'])), reverse=True)
                    depth_controls = []
                    for di, d in enumerate(all_depths):
                        c1, c2 = st.columns([1, 4])
                        with c1: use = st.checkbox("", value=True, key=f"use_{i}_{di}_{f_file.name}")
                        with c2: val = st.number_input(f"עומק {di+1}", value=float(round(d, 3)), format="%.3f", key=f"z_{i}_{di}_{f_file.name}")
                        depth_controls.append({'use': use, 'val': val})
                    final_configs.append({'active': active, 'depths': depth_controls, 'block': b, 'id': i})
            order = st.multiselect("סדר עבודה:", options=[c['id'] for c in final_configs if c['active']], default=[c['id'] for c in final_configs if c['active']], format_func=lambda x: f"{final_configs[x]['block']['t_cnc']} {final_configs[x]['block']['purpose']}")

        nc_full = ["%", f"(N10 {f_file.name} - DARWISH 48.18 MASTER)", "N20 G90 G54 G21"]
        n_c, current_t = 30, ""
        for idx in order:
            cfg = final_configs[idx]; b = cfg['block']
            if b['t_cnc'] != current_t:
                nc_full.extend([f"N{n_c} M05", f"N{n_c+5} {b['t_cnc']} M06", f"N{n_c+10} G43 H{b['t_cnc'][1:]}", f"N{n_c+15} S{int(b['s'])} M03"])
                n_c += 20; current_t = b['t_cnc']
            for depth_item in cfg['depths']:
                if not depth_item['use']: continue
                for it in b['items']:
                    path = calculate_path_v4818(it['pts'], it['rad'], it['rk'], False, it['is_boring'])
                    c_ramp = 0 if it['is_boring'] else ramp_len
                    for pi, p in enumerate(path):
                        nx, ny = p[0] + off_x, p[1] + off_y
                        if pi == 0:
                            nc_full.append(f"N{n_c} G00 X{nx-c_ramp:.3f} Y{ny:.3f}")
                            nc_full.append(f"N{n_c+5} G01 Z{depth_item['val']:.3f} X{nx:.3f} F2000")
                            n_c += 10
                        else:
                            nc_full.append(f"N{n_c} G01 X{nx:.3f} Y{ny:.3f} F{int(it['f'])}"); n_c += 5
                    nc_full.append(f"N{n_c} G00 Z36.0"); n_c += 5
        nc_full.extend([f"N{n_c} M05", f"N{n_c+5} M30", "%"])
        st.download_button("🚀 המר והורד קובץ NC סופי", "\n".join(nc_full), f"{f_file.name}_master.nc")

        with col_vis:
            fig = go.Figure()
            # שולחן המכונה של אבי (3000x1220)
            fig.add_shape(type="rect", x0=0, y0=0, x1=1220, y1=3000, line=dict(color="Gray", width=1), fillcolor="rgba(128, 128, 128, 0.05)")
            # הפלטה (Workpiece)
            fig.add_shape(type="rect", x0=off_x, y0=off_y, x1=(wp_w if rotate else wp_l)+off_x, y1=(wp_l if rotate else wp_w)+off_y, line=dict(color="BurlyWood", width=3))
            
            for cfg in final_configs:
                if cfg['active']:
                    for it in cfg['block']['items']:
                        ox, oy = zip(*it['pts'])
                        color = "green" if it['is_boring'] else "blue" if cfg['block']['purpose']=="Inside" else "red"
                        # ציור גאומטריית מקור
                        fig.add_trace(go.Scatter(x=[x+off_x for x in ox], y=[y+off_y for y in oy], mode='lines+markers' if it['is_boring'] else 'lines', marker=dict(size=10 if it['is_boring'] else 1), line=dict(color=color, width=1), showlegend=False))
                        # ציור מסלול כלי (צהוב)
                        path = calculate_path_v4818(it['pts'], it['rad'], it['rk'], False, it['is_boring'])
                        px, py = zip(*path)
                        fig.add_trace(go.Scatter(x=[x+off_x for x in px], y=[y+off_y for y in py], mode='markers' if it['is_boring'] else 'lines', marker=dict(size=5, color="yellow"), line=dict(color="yellow", dash="dash"), showlegend=False))
            
            fig.update_layout(dragmode='pan', yaxis=dict(scaleanchor="x", scaleratio=1), margin=dict(l=0, r=0, t=0, b=0), height=800)
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})
