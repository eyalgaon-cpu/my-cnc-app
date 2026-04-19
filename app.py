import streamlit as st
import re, math
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# Darwish 48.8 - THE BOUNDARY GUARD (STABILIZED & SCALED)
st.set_page_config(page_title="Darwish 48.8 Production", layout="wide")

# --- 1. מסד כלים מלא (T1-T49) ---
if 'tool_db' not in st.session_state:
    st.session_state.tool_db = pd.DataFrame([
        {"T_CNC": "T1", "MPR_Name": "137", "תיאור": "כרסום 40 מילימטר", "קוטר": 40.0, "RPM": 12000, "Feed": 4000},
        {"T_CNC": "T2", "MPR_Name": "142", "תיאור": "כרסום יהלום 12 מילימטר", "קוטר": 12.0, "RPM": 18000, "Feed": 4000},
        {"T_CNC": "T3", "MPR_Name": "158", "תיאור": "כרסום 8 מילימטר", "קוטר": 8.0, "RPM": 18000, "Feed": 3000},
        {"T_CNC": "T4", "MPR_Name": "128", "תיאור": "כרסום 12 מילימטר", "קוטר": 12.0, "RPM": 18000, "Feed": 3500},
        {"T_CNC": "T6", "MPR_Name": "35", "תיאור": "מקדח צירים 35 מילימטר", "קוטר": 35.0, "RPM": 3000, "Feed": 1000},
        {"T_CNC": "T8", "MPR_Name": "19.0", "תיאור": "כרסום 19 מילימטר", "קוטר": 19.0, "RPM": 16000, "Feed": 3000},
        {"T_CNC": "T10", "MPR_Name": "6.0", "תיאור": "כרסום/מקדח 6 מילימטר", "קוטר": 6.0, "RPM": 18000, "Feed": 2000},
        {"T_CNC": "T11", "MPR_Name": "140", "תיאור": "End Mill 3 מילימטר (T11)", "קוטר": 3.0, "RPM": 18000, "Feed": 2500},
        {"T_CNC": "T13", "MPR_Name": "130", "תיאור": "גירונג 90/45", "קוטר": 0.2, "RPM": 18000, "Feed": 2000},
        {"T_CNC": "T44", "MPR_Name": "5.0", "תיאור": "מקדח 5 מילימטר", "קוטר": 5.0, "RPM": 4500, "Feed": 1200},
        {"T_CNC": "T47", "MPR_Name": "8.0", "תיאור": "מקדח 8 מילימטר", "קוטר": 8.0, "RPM": 4500, "Feed": 1200},
        {"T_CNC": "T49", "MPR_Name": "15.0", "תיאור": "מקדח 15 מילימטר", "קוטר": 15.0, "RPM": 3000, "Feed": 800}
    ])

with st.sidebar:
    with st.expander("🛠️ ניהול כלים (T1-T49)", expanded=False):
        st.session_state.tool_db = st.data_editor(st.session_state.tool_db, num_rows="dynamic", key="tools_v488")

# --- 2. ליבה מתמטית v48.7 (Intersection & Inset Logic) ---
def is_point_in_poly(x, y, poly):
    n = len(poly)
    inside = False
    p1x, p1y = poly[0]
    for i in range(n + 1):
        p2x, p2y = poly[i % n]
        if y > min(p1y, p2y) and y <= max(p1y, p2y):
            if x <= max(p1x, p2x):
                if p1y != p2y:
                    xints = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                if p1x == p2x or x <= xints:
                    inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def calculate_path_v487(pts, r, mpr_rk, is_pocket=False):
    if r <= 0 or len(pts) < 2: return pts
    pts_arr = np.array(pts)
    is_ccw = (sum((pts_arr[i][0] * pts_arr[(i+1)%len(pts_arr)][1] - pts_arr[(i+1)%len(pts_arr)][0] * pts_arr[i][1]) for i in range(len(pts_arr))) / 2.0) > 0
    side = 1 if is_ccw else -1
    if not is_pocket:
        side = 1 if "WRKL" in mpr_rk else -1 if "WRKR" in mpr_rk else 0
        if side == 0: return pts
    shifted_lines = []
    for i in range(len(pts_arr) - 1):
        p1, p2 = pts_arr[i], pts_arr[i+1]
        v = p2 - p1
        mag = np.linalg.norm(v)
        if mag == 0: continue
        normal = side * np.array([-v[1], v[0]]) / mag
        shifted_lines.append((p1 + normal * r, p2 + normal * r))
    if not shifted_lines: return pts
    def intersect(l1, l2):
        x1, y1 = l1[0]; x2, y2 = l1[1]
        x3, y3 = l2[0]; x4, y4 = l2[1]
        den = (y4-y3)*(x2-x1) - (x4-x3)*(y2-y1)
        if abs(den) < 1e-6: return l1[1]
        ua = ((x4-x3)*(y1-y3) - (y4-y3)*(x1-x3)) / den
        return np.array([x1 + ua*(x2-x1), y1 + ua*(y2-y1)])
    new_path = [tuple(shifted_lines[0][0])]
    for i in range(len(shifted_lines)-1):
        new_path.append(tuple(intersect(shifted_lines[i], shifted_lines[i+1])))
    new_path.append(tuple(shifted_lines[-1][1]))
    if len(new_path) > 2 and is_pocket: new_path.append(new_path[0])
    return new_path

def get_f(key, block, default=0.0):
    m = re.search(f'{key}="([^"]*)"', block)
    return float(m.group(1).strip()) if m else default

# --- 3. ממשק הפקה ---
st.title("🏭 דרוויש 48.8 - THE BOUNDARY GUARD")
col_cfg, col_vis = st.columns([1, 2])

with col_cfg:
    st.subheader("הגדרות פרויקט")
    rotate = st.checkbox("סובב חלק 90 מעלות (CCW)", value=True)
    off_x = st.number_input("תוספת הרחקה X (מילימטר)", value=0.0)
    off_y = st.number_input("תוספת הרחקה Y (מילימטר)", value=0.0)
    ramp_len = st.slider("אורך נחיתה (Ramp)", 0, 50, 20)
    upl = st.file_uploader("טען קבצי MPR", accept_multiple_files=True)

if upl:
    for f_file in upl:
        mpr = f_file.getvalue().decode('utf-8', errors='ignore')
        wp_block = re.search(r'\[001(.*?)\]', mpr, re.DOTALL)
        wp_w = get_f('w', wp_block.group(1)) if wp_block else 1220.0
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

        ops = []
        for m in re.finditer(r'<(102|105|130|181)(.*?)(?=<|\!|\[H)', mpr, re.DOTALL):
            tag, bc = m.group(1), m.group(2)
            t_mpr = re.search(r'(?:TNO|T_|DU)="([^"]*)"', bc).group(1).strip() if re.search(r'(?:TNO|T_|DU)="([^"]*)"', bc) else "142"
            t_id = re.sub(r'[^0-9.]', '', t_mpr) if tag == '102' else t_mpr.replace("BV","")
            t_info = st.session_state.tool_db[st.session_state.tool_db['MPR_Name'] == t_id]
            if t_info.empty: t_info = st.session_state.tool_db[st.session_state.tool_db['T_CNC'] == "T2"]
            
            if tag in ['181', '102']: z_abs = round((thick - get_f('TI', bc)), 3)
            else: z_abs = round(get_f('ZA', bc), 3)
            
            geoid = re.search(r'EA="(\d+):', bc).group(1).strip() if re.search(r'EA="(\d+):', bc) else None
            raw_pts = geos.get(geoid, [[get_f('XA', bc), get_f('YA', bc)]]) if tag != '102' else [[wp_w - get_f('YA', bc), get_f('XA', bc)] if rotate else [get_f('XA', bc), get_f('YA', bc)]]
            
            ops.append({
                't_cnc': t_info.iloc[0]['T_CNC'], 'desc': t_info.iloc[0]['תיאור'], 
                'z': z_abs, 'pts': raw_pts, 'rad': t_info.iloc[0]['קוטר']/2, 
                'f': t_info.iloc[0]['Feed'], 's': t_info.iloc[0]['RPM'],
                'rk': re.search(r'RK="([^"]*)"', bc).group(1) if re.search(r'RK="([^"]*)"', bc) else "WRKL",
                'is_pocket': (tag == '181'), 'final': (z_abs <= 0.2 and tag != '102'), 'type': tag
            })

        tool_groups = {}
        for op in ops:
            key = (op['t_cnc'], op['final'])
            if key not in tool_groups:
                tool_groups[key] = {'t_cnc': op['t_cnc'], 'desc': op['desc'], 'final': op['final'], 'items': [], 's': op['s']}
            tool_groups[key]['items'].append(op)

        with col_cfg:
            st.write(f"### 📦 ניהול בלוקים: {f_file.name}")
            block_configs = []
            for i, (key, group) in enumerate(tool_groups.items()):
                label = "🔴 סופי" if group['final'] else "🔵 פנימי"
                with st.expander(f"{label}: {group['t_cnc']} ({group['desc']})"):
                    active = st.checkbox("כלול בייצור", value=True, key=f"act_{i}")
                    depths = sorted(list(set(it['z'] for it in group['items'])), reverse=True)
                    final_depths = [st.number_input(f"עומק פסיעה {di+1}", value=d, key=f"z_{i}_{di}") for di, d in enumerate(depths)]
                    block_configs.append({'id': i, 'active': active, 'passes': final_depths, 'key': key})
            order = st.multiselect("סדר עבודה:", options=[i for i, b in enumerate(block_configs) if b['active']], default=[i for i, b in enumerate(block_configs) if b['active']], format_func=lambda x: f"{block_configs[x]['key'][0]}")

        # ייצור NC
        nc = ["%", f"(N10 DARWISH 48.8 - MASTER FIX)", "N20 G90 G54 G21"]
        n_c = 30
        for b_id in order:
            b_cfg = block_configs[b_id]; group = tool_groups[b_cfg['key']]
            nc.extend([f"N{n_c} M05", f"N{n_c+5} {group['t_cnc']} M06", f"N{n_c+10} G43 H{group['t_cnc'][1:]}", f"N{n_c+15} S{int(group['s'])} M03"])
            n_c += 20
            for zv in b_cfg['passes']:
                for it in group['items']:
                    if it['type'] == '102': # קידוח
                        nc.append(f"N{n_c} G00 X{it['pts'][0][0]+off_x:.3f} Y{it['pts'][0][1]+off_y:.3f}"); n_c += 5
                        nc.append(f"N{n_c} G01 Z{zv:.3f} F{int(it['f'])}"); n_c += 5
                    else: # כרסום
                        path = calculate_path_v487(it['pts'], it['rad'], it['rk'], it['is_pocket'])
                        current_ramp = 0 if it['is_pocket'] else ramp_len
                        for pi, p in enumerate(path):
                            nx, ny = p[0] + off_x, p[1] + off_y
                            if pi == 0:
                                nc.append(f"N{n_c} G00 X{nx-current_ramp:.3f} Y{ny:.3f}"); n_c += 5
                                nc.append(f"N{n_c} G01 Z{zv:.3f} X{nx:.3f} F2000"); n_c += 5
                            else:
                                nc.append(f"N{n_c} G01 X{nx:.3f} Y{ny:.3f} F{int(it['f'])}"); n_c += 5
                    nc.append(f"N{n_c} G00 Z36.0"); n_c += 5
        nc.extend([f"N{n_c} M05", f"N{n_c+5} M30", "%"])
        
        with col_vis:
            fig = go.Figure()
            fig.update_layout(dragmode='pan', xaxis=dict(scaleanchor="y", scaleratio=1), yaxis=dict(scaleanchor="x", scaleratio=1), margin=dict(l=0, r=0, t=0, b=0))
            fig.add_shape(type="rect", x0=off_x, y0=off_y, x1=wp_w+off_x, y1=3050, line=dict(color="BurlyWood", width=3), fillcolor="rgba(222, 184, 135, 0.05)")
            for b_id in order:
                group = tool_groups[block_configs[b_id]['key']]
                for it in group['items']:
                    ox, oy = zip(*it['pts'])
                    color = "blue" if it['t_cnc'].startswith('T') else "red"
                    if it['type'] == '102' or len(it['pts']) < 2:
                        fig.add_trace(go.Scatter(x=[x+off_x for x in ox], y=[y+off_y for y in oy], mode='markers', marker=dict(size=10, color="green")))
                    else:
                        fig.add_trace(go.Scatter(x=[x+off_x for x in ox], y=[y+off_y for y in oy], mode='lines', line=dict(color=color, width=2), showlegend=False))
                        path = calculate_path_v487(it['pts'], it['rad'], it['rk'], it['is_pocket'])
                        px, py = zip(*path)
                        fig.add_trace(go.Scatter(x=[x+off_x for x in px], y=[y+off_y for y in py], mode='lines', line=dict(color="yellow", dash="dash", width=1.5)))
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})
     
        st.download_button(f"📥 הורד NC (גרסה 48.8)", "\n".join(nc), f"{f_file.name}_v488.nc")
