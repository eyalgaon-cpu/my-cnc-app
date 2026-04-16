import streamlit as st
import re, math
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# Darwish 48.1 - FINAL INDUSTRIAL VERSION
st.set_page_config(page_title="Darwish 48.1 Production", layout="wide")

if 'tool_db' not in st.session_state:
    st.session_state.tool_db = pd.DataFrame([
        {"T_CNC": "T1", "MPR_Name": "137", "תיאור": "End Mill 40mm", "קוטר": 40.0, "RPM": 18000, "Feed": 12000},
        {"T_CNC": "T2", "MPR_Name": "142", "תיאור": "End Mill 6mm", "קוטר": 6.0, "RPM": 18000, "Feed": 4500},
        {"T_CNC": "T3", "MPR_Name": "158", "תיאור": "End Mill 8mm", "קוטר": 8.0, "RPM": 18000, "Feed": 4500},
        {"T_CNC": "T4", "MPR_Name": "128", "תיאור": "End Mill 12mm", "קוטר": 12.0, "RPM": 18000, "Feed": 5000},
        {"T_CNC": "T11", "MPR_Name": "140", "תיאור": "End Mill 3mm", "קוטר": 3.0, "RPM": 18000, "Feed": 2500},
        {"T_CNC": "T44", "MPR_Name": "BV5", "תיאור": "Drill 5mm", "קוטר": 5.0, "RPM": 4500, "Feed": 1200}
    ])

def get_winding(pts):
    area = 0
    for i in range(len(pts)):
        p1, p2 = pts[i], pts[(i + 1) % len(pts)]
        area += (p1[0] * p2[1] - p2[0] * p1[1])
    return area / 2.0

def calculate_miter_offset_v4(pts, r, tool_id, mpr_rk):
    if r <= 0: return pts
    pts_arr = np.array(pts)
    is_ccw = get_winding(pts) > 0
    
    # לוגיקת צידוד תעשייתית:
    # עבור כלים פנימיים (T4, T11) - כוח לכיוון המרכז (Inside)
    if tool_id in ['T4', 'T11']:
        side = 1 if is_ccw else -1
    # עבור כלי סופי (T2) - כוח החוצה (Outside)
    elif tool_id == 'T2':
        side = -1 if is_ccw else 1
    # עבור כלים אחרים - ציות ל-RK
    else:
        side = 1 if "WRKL" in mpr_rk else -1 if "WRKR" in mpr_rk else 0

    n_pts = len(pts_arr)
    offset_path = []
    normals = []
    for i in range(n_pts - 1):
        v = pts_arr[i+1] - pts_arr[i]
        mag = np.linalg.norm(v)
        normals.append(side * np.array([-v[1], v[0]]) / mag if mag != 0 else np.array([0,0]))
    
    for i in range(n_pts):
        if i == 0: offset_path.append(pts_arr[0] + normals[0] * r)
        elif i == n_pts - 1: offset_path.append(pts_arr[-1] + normals[-1] * r)
        else:
            n1, n2 = normals[i-1], normals[i]
            miter = n1 + n2
            m_mag_sq = np.dot(miter, miter)
            scale = 2.0 / m_mag_sq if m_mag_sq > 1e-6 else 1.0
            offset_path.append(pts_arr[i] + miter * scale * r)
    return [p.tolist() for p in offset_path]

def get_f(key, block, default=0.0):
    m = re.search(f'{key}="([^"]*)"', block)
    return float(m.group(1).strip()) if m else default

st.title("🏭 מרכז ייצור דרוויש 48.1")
col_cfg, col_vis = st.columns([1, 2])

with col_cfg:
    st.subheader("הגדרות ייצור")
    rotate = st.checkbox("סובב חלק 90 מעלות (CCW)", value=True)
    off_x = st.number_input("תוספת הרחקה X (מילימטר)", value=0.0)
    off_y = st.number_input("תוספת הרחקה Y (מילימטר)", value=0.0)
    ramp_len = st.slider("אורך נחיתה (Ramp)", 0, 50, 20)
    upl = st.file_uploader("טען קבצי MPR", accept_multiple_files=True)

if upl:
    for f_file in upl:
        mpr = f_file.getvalue().decode('utf-8', errors='ignore')
        wp_block = re.search(r'\[001(.*?)\]', mpr, re.DOTALL)
        wp_l = get_f('l', wp_block.group(1)) if wp_block else 2440.0
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
            t_info = st.session_state.tool_db[st.session_state.tool_db['MPR_Name'] == t_mpr.replace("BV","")]
            if t_info.empty: t_info = st.session_state.tool_db[st.session_state.tool_db['T_CNC'] == "T2"]
            
            ti_val = get_f('TI', bc) if tag in ['181','102'] else get_f('ZA', bc)
            z_abs = round((thick - ti_val if tag in ['181','102'] else ti_val), 3)
            geoid = re.search(r'EA="(\d+):', bc).group(1).strip() if re.search(r'EA="(\d+):', bc) else None
            
            if tag == '102':
                xa, ya = get_f('XA', bc), get_f('YA', bc)
                raw_pts = [[wp_w - ya, xa]] if rotate else [[xa, ya]]
            else:
                raw_pts = geos.get(geoid, [[get_f('XA', bc), get_f('YA', bc)]])
            
            rk_val = re.search(r'RK="([^"]*)"', bc)
            mpr_rk = rk_val.group(1).strip() if rk_val else "WRKL"

            ops.append({
                't_cnc': t_info.iloc[0]['T_CNC'], 'desc': t_info.iloc[0]['תיאור'], 
                'z': z_abs, 'pts': raw_pts, 'rad': t_info.iloc[0]['קוטר']/2, 
                'f': t_info.iloc[0]['Feed'], 's': t_info.iloc[0]['RPM'],
                'final': (z_abs <= 0.2 and tag != '102'), 'rk': mpr_rk
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
                    active = st.checkbox("כלול בייצור", value=True, key=f"act_{i}_{f_file.name}")
                    depths = sorted(list(set(it['z'] for it in group['items'])), reverse=True)
                    final_depths = [st.number_input(f"עומק פסיעה {di+1}", value=d, key=f"z_{i}_{di}_{f_file.name}") for di, d in enumerate(depths)]
                    block_configs.append({'id': i, 'active': active, 'passes': final_depths, 'final': group['final'], 'key': key})

            order = st.multiselect("סדר כלים:", options=[i for i, b in enumerate(block_configs) if b['active']], default=[i for i, b in enumerate(block_configs) if b['active']], format_func=lambda x: f"{block_configs[x]['key'][0]} ({block_configs[x]['key'][1]})")

        # ייצור NC
        nc = ["%", f"(N10 DARWISH 48.1 FINAL)", "N20 G90 G54 G21"]
        n_c = 30
        for b_id in order:
            b_cfg = block_configs[b_id]; group = tool_groups[b_cfg['key']]
            nc.extend([f"N{n_c} M05", f"N{n_c+5} {group['t_cnc']} M06", f"N{n_c+10} G43 H{group['t_cnc'][1:]}", f"N{n_c+15} S{int(group['s'])} M03"])
            n_c += 20
            for zv in b_cfg['passes']:
                for it in group['items']:
                    path = calculate_miter_offset_v4(it['pts'], it['rad'], group['t_cnc'], it['rk'])
                    for pi, p in enumerate(path):
                        nx, ny = p[0] + off_x, p[1] + off_y
                        if pi == 0:
                            nc.append(f"N{n_c} G00 X{nx-ramp_len:.3f} Y{ny:.3f}"); n_c += 5
                            nc.append(f"N{n_c} G01 Z{zv:.3f} X{nx:.3f} F2000"); n_c += 5
                        else:
                            nc.append(f"N{n_c} G01 X{nx:.3f} Y{ny:.3f} F{int(it['f'])}"); n_c += 5
                    nc.append(f"N{n_c} G00 Z36.0"); n_c += 5
        nc.extend([f"N{n_c} M05", f"N{n_c+5} M30", "%"])
        
        with col_vis:
            fig = go.Figure()
            fig.update_layout(dragmode='pan', yaxis=dict(scaleanchor="x", scaleratio=1), margin=dict(l=0, r=0, t=0, b=0))
            
            pl, pw = (wp_w, wp_l) if rotate else (wp_l, wp_w)
            fig.add_shape(type="rect", x0=off_x, y0=off_y, x1=pl+off_x, y1=pw+off_y, line=dict(color="BurlyWood", width=3), fillcolor="rgba(222, 184, 135, 0.05)")
            fig.add_shape(type="rect", x0=0, y0=0, x1=1300, y1=3050, line=dict(color="RoyalBlue", width=1, dash="dot"))

            for b_id in order:
                group = tool_groups[block_configs[b_id]['key']]
                for it in group['items']:
                    ox, oy = zip(*it['pts'])
                    color = "blue" if group['final'] else "red"
                    fig.add_trace(go.Scatter(x=[x+off_x for x in ox], y=[y+off_y for y in oy], mode='lines', line=dict(color=color, width=2.5), name=f"גאומטריה: {group['t_cnc']}", showlegend=False))
                    px, py = zip(*calculate_miter_offset_v4(it['pts'], it['rad'], group['t_cnc'], it['rk']))
                    fig.add_trace(go.Scatter(x=[x+off_x for x in px], y=[y+off_y for y in py], mode='lines', line=dict(color="yellow", dash="dash", width=1.5), name=f"מסלול: {group['t_cnc']}"))
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})
            st.download_button(f"📥 הורד NC (גרסה 48.1)", "\n".join(nc), f"{f_file.name}_v481.nc")
