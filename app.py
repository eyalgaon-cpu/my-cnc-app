import streamlit as st
import re, math
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# Darwish 47.5 - THE SMART MERGER (PATH IDENTITY + ANCHOR BOX)
st.set_page_config(page_title="Darwish 47.5 Production", layout="wide")

# --- 1. לשונית כלים (עודכן למניעת דריסה) ---
if 'tool_db' not in st.session_state:
    st.session_state.tool_db = pd.DataFrame([
        {"T_CNC": "T1", "MPR_Name": "137", "תיאור": "End Mill 40mm", "קוטר": 40.0, "RPM": 18000, "Feed": 12000},
        {"T_CNC": "T2", "MPR_Name": "142", "תיאור": "End Mill 6mm", "קוטר": 6.0, "RPM": 18000, "Feed": 4500},
        {"T_CNC": "T3", "MPR_Name": "158", "תיאור": "End Mill 8mm", "קוטר": 8.0, "RPM": 18000, "Feed": 4500},
        {"T_CNC": "T4", "MPR_Name": "128", "תיאור": "End Mill 12mm", "קוטר": 12.0, "RPM": 18000, "Feed": 5000},
        {"T_CNC": "T11", "MPR_Name": "140", "תיאור": "End Mill 3mm", "קוטר": 3.0, "RPM": 18000, "Feed": 2500},
        {"T_CNC": "T44", "MPR_Name": "BV5", "תיאור": "Drill 5mm", "קוטר": 5.0, "RPM": 4500, "Feed": 1200}
    ])

with st.expander("🛠️ לשונית כלים (הגדרות מאסטר)", expanded=False):
    st.session_state.tool_db = st.data_editor(st.session_state.tool_db, num_rows="dynamic", key="tools_475")

# --- 2. מנוע מתמטי ---
def calculate_miter_offset(pts, r):
    if r <= 0: return pts
    pts_arr = np.array(pts)
    n_pts = len(pts_arr)
    offset_path = []
    normals = []
    for i in range(n_pts - 1):
        v = pts_arr[i+1] - pts_arr[i]
        mag = np.linalg.norm(v)
        normals.append(np.array([-v[1], v[0]]) / mag if mag != 0 else np.array([0,0]))
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

# --- 3. ממשק ייצור ---
st.title("🏭 מרכז ייצור דרוויש 47.5")
col_cfg, col_vis = st.columns([1, 2])

with col_cfg:
    st.subheader("הגדרות ייצור")
    rotate = st.checkbox("סובב חלק 90 מעלות", value=True)
    off_x = st.number_input("תוספת הרחקה X (מהפינה הפיזית)", value=0.0)
    off_y = st.number_input("תוספת הרחקה Y (מהפינה הפיזית)", value=0.0)
    ramp_len = st.slider("אורך נחיתה (Ramp)", 0, 50, 20)
    upl = st.file_uploader("טען קבצי MPR", accept_multiple_files=True)

if upl:
    for f_file in upl:
        mpr = f_file.getvalue().decode('utf-8', errors='ignore')
        thick = get_f('t', mpr, 19.0)
        geos = {}
        parts = re.split(r'\](\d+)', mpr)
        for i in range(1, len(parts), 2):
            pts = []
            for el in re.split(r'\$E\d+', parts[i+1]):
                xm, ym = re.search(r'X=([\d.-]+)', el), re.search(r'Y=([\d.-]+)', el)
                if xm and ym:
                    pts.append([float(ym.group(1)), float(xm.group(1))] if rotate else [float(xm.group(1)), float(ym.group(1))])
            if pts: geos[parts[i]] = pts

        # זיהוי פעולות וייצור מפתח למסלול (לצורך איחוד)
        ops = []
        for m in re.finditer(r'<(102|105|130|181)(.*?)(?=<|\!|\[H)', mpr, re.DOTALL):
            tag, bc = m.group(1), m.group(2)
            t_mpr = re.search(r'(?:TNO|T_|DU)="([^"]*)"', bc).group(1).strip() if re.search(r'(?:TNO|T_|DU)="([^"]*)"', bc) else "142"
            t_info = st.session_state.tool_db[st.session_state.tool_db['MPR_Name'] == t_mpr.replace("BV","")]
            if t_info.empty: t_info = st.session_state.tool_db[st.session_state.tool_db['T_CNC'] == "T2"]
            
            ti_val = get_f('TI', bc) if tag in ['181','102'] else get_f('ZA', bc)
            z_abs = round((thick - ti_val if tag in ['181','102'] else ti_val), 3)
            geoid = re.search(r'EA="(\d+):', bc).group(1).strip() if re.search(r'EA="(\d+):', bc) else None
            pts = geos.get(geoid, [[get_f('XA', bc), get_f('YA', bc)]]) if tag != '102' else [[get_f('XA', bc), get_f('YA', bc)]]
            
            ops.append({
                't_cnc': t_info.iloc[0]['T_CNC'], 'desc': t_info.iloc[0]['תיאור'], 
                'z': z_abs, 'pts': pts, 'rad': t_info.iloc[0]['קוטר']/2, 
                'f': t_info.iloc[0]['Feed'], 's': t_info.iloc[0]['RPM'],
                'final': (z_abs <= 0.2 and tag != '102'), 'path_key': str(pts)
            })

        # --- מנוע איחוד בלוקים חכם (Path Merging) ---
        merged_groups = []
        for op in ops:
            found = False
            for mg in merged_groups:
                # אם הכלי והמסלול זהים - נאחד אותם
                if mg['t_cnc'] == op['t_cnc'] and mg['path_key'] == op['path_key']:
                    mg['items'].append(op); found = True; break
            if not found:
                merged_groups.append({
                    't_cnc': op['t_cnc'], 'path_key': op['path_key'], 'desc': op['desc'],
                    's': op['s'], 'rad': op['rad'], 'items': [op],
                    'is_final': op['final']
                })

        # חישוב עוגן פרויקט (Bounding Box לכל הקיים ב-MPR)
        all_coords = [p for op in ops for p in op['pts']]
        min_x = min(p[0] for p in all_coords) if all_coords else 0
        min_y = min(p[1] for p in all_coords) if all_coords else 0

        with col_cfg:
            st.write(f"### 📦 ניהול בלוקים: {f_file.name}")
            block_configs = []
            for i, group in enumerate(merged_groups):
                # מיון פסיעות: קודם גבוה (פנימי) ואח"כ נמוך (סופי)
                group['items'].sort(key=lambda x: x['z'], reverse=True)
                # אם אחת הפסיעות היא "סופית", כל הבלוק נחשב סופי
                block_final = any(item['final'] for item in group['items'])
                label = "🔴 סופי/משולב" if block_final else "🔵 פנימי"
                
                with st.expander(f"{label}: {group['t_cnc']} ({group['desc']})"):
                    active = st.checkbox("כלול בייצור", value=True, key=f"act_{i}_{f_file.name}")
                    pass_depths = []
                    for pi, item in enumerate(group['items']):
                        d = st.number_input(f"עומק פסיעה {pi+1}", value=item['z'], key=f"z_{i}_{pi}_{f_file.name}")
                        pass_depths.append(d)
                    if st.checkbox("הוסף פסיעה ידנית", key=f"add_{i}_{f_file.name}"):
                        pass_depths.append(st.number_input("עומק פסיעה נוספת", value=0.0, key=f"z_ext_{i}_{f_file.name}"))
                    block_configs.append({'id': i, 'active': active, 'passes': pass_depths, 'final': block_final})

            # סדר כלים אינטראקטיבי
            order_options = [i for i, b in enumerate(block_configs) if b['active'] and not b['final']]
            final_options = [i for i, b in enumerate(block_configs) if b['active'] and b['final']]
            order = st.multiselect("קבע סדר פעולות פנימיות:", options=order_options, default=order_options, format_func=lambda x: f"{merged_groups[x]['t_cnc']} ({merged_groups[x]['desc']})")
            full_order = order + final_options

        # ייצור NC
        nc = ["%", f"(N10 DARWISH 47.5 - {f_file.name})", "N20 G90 G54 G21"]
        n_c = 30
        for b_id in full_order:
            b_cfg = block_configs[b_id]
            m_grp = merged_groups[b_id]
            nc.extend([f"N{n_c} M05", f"N{n_c+5} {m_grp['t_cnc']} M06", f"N{n_c+10} G43 H{m_grp['t_cnc'][1:]}", f"N{n_c+15} S{int(m_grp['s'])} M03"])
            n_c += 20
            for zv in b_cfg['passes']:
                path = calculate_miter_offset(m_grp['items'][0]['pts'], m_grp['rad'])
                for pi, p in enumerate(path):
                    # חישוב עוגן Bounding Box - מוודא שהכל זז כמקשה אחת
                    nx, ny = (p[0] - min_x) + off_x, (p[1] - min_y) + off_y
                    if pi == 0:
                        nc.append(f"N{n_c} G00 X{nx-ramp_len:.3f} Y{ny:.3f}"); n_c += 5
                        nc.append(f"N{n_c} G01 Z{zv:.3f} X{nx:.3f} F2000"); n_c += 5
                    else:
                        nc.append(f"N{n_c} G01 X{nx:.3f} Y{ny:.3f} F{int(m_grp['items'][0]['f'])}"); n_c += 5
                nc.append(f"N{n_c} G00 Z36.0"); n_c += 5
        nc.extend([f"N{n_c} M05", f"N{n_c+5} M30", f"N{n_c+10} M200", "%"])

        with col_vis:
            fig = go.Figure()
            fig.update_layout(
                dragmode='pan', 
                yaxis=dict(scaleanchor="x", scaleratio=1), 
                margin=dict(l=0, r=0, t=0, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            fig.add_shape(type="rect", x0=0, y0=0, x1=1300, y1=3050, line=dict(color="RoyalBlue", width=1))
            
            for b_id in full_order:
                m_grp = merged_groups[b_id]
                pts = m_grp['items'][0]['pts']
                ox, oy = zip(*pts)
                # קווי מקור (אפור מקווקו)
                fig.add_trace(go.Scatter(x=[x-min_x+off_x for x in ox], y=[y-min_y+off_y for y in oy], mode='lines', line=dict(dash='dash', color='gray'), showlegend=False, hoverinfo='skip'))
                # מסלול כלי
                px, py = zip(*calculate_miter_offset(pts, m_grp['rad']))
                fig.add_trace(go.Scatter(
                    x=[x-min_x+off_x for x in px], y=[y-min_y+off_y for y in py], 
                    mode='lines', name=m_grp['t_cnc'], 
                    legendgroup=m_grp['t_cnc'],
                    hovertemplate=f"כלי: {m_grp['t_cnc']}<br>תיאור: {m_grp['desc']}<extra></extra>"
                ))
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': True})
            st.download_button(f"📥 הורד NC (גרסה 47.5)", "\n".join(nc), f"{f_file.name}_v475.nc")
