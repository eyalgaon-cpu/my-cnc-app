import streamlit as st
import re, math
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# Darwish 47.4 - PRODUCTION MASTER (NO NORMALIZE + UI PAN/ZOOM + ADDITIVE OFFSET)
st.set_page_config(page_title="Darwish 47.4 Production", layout="wide")

# --- 1. לשונית כלים ---
if 'tool_db' not in st.session_state:
    st.session_state.tool_db = pd.DataFrame([
        {"T_CNC": "T1", "MPR_Name": "137", "תיאור": "End Mill 40mm", "קוטר": 40.0, "RPM": 18000, "Feed": 12000},
        {"T_CNC": "T2", "MPR_Name": "142", "תיאור": "End Mill 6mm", "קוטר": 6.0, "RPM": 18000, "Feed": 4500},
        {"T_CNC": "T3", "MPR_Name": "158", "תיאור": "End Mill 8mm", "קוטר": 8.0, "RPM": 18000, "Feed": 4500},
        {"T_CNC": "T4", "MPR_Name": "128", "תיאור": "End Mill 12mm", "קוטר": 12.0, "RPM": 18000, "Feed": 5000},
        {"T_CNC": "T11", "MPR_Name": "140", "תיאור": "End Mill 3mm", "קוטר": 3.0, "RPM": 18000, "Feed": 2500},
        {"T_CNC": "T44", "MPR_Name": "BV5", "תיאור": "Drill 5mm", "קוטר": 5.0, "RPM": 4500, "Feed": 1200}
    ])

with st.expander("🛠️ לשונית כלים", expanded=False):
    st.session_state.tool_db = st.data_editor(st.session_state.tool_db, num_rows="dynamic", key="tools_474")

# --- 2. מנוע מתמטי (Miter Offset v3) ---
def calculate_miter_offset(pts, r):
    if r <= 0: return pts
    pts = np.array(pts)
    n_pts = len(pts)
    offset_path = []
    normals = []
    for i in range(n_pts - 1):
        v = pts[i+1] - pts[i]
        mag = np.linalg.norm(v)
        if mag == 0: normals.append(np.array([0, 0]))
        else: normals.append(np.array([-v[1], v[0]]) / mag)
    for i in range(n_pts):
        if i == 0: offset_path.append(pts[0] + normals[0] * r)
        elif i == n_pts - 1: offset_path.append(pts[-1] + normals[-1] * r)
        else:
            n1, n2 = normals[i-1], normals[i]
            miter = (n1 + n2)
            miter_mag_sq = np.dot(miter, miter)
            if miter_mag_sq < 1e-6: offset_path.append(pts[i] + n1 * r)
            else:
                scale = 2.0 / miter_mag_sq
                offset_path.append(pts[i] + miter * scale * r)
    return [p.tolist() for p in offset_path]

def get_f(key, block, default=0.0):
    m = re.search(f'{key}="([^"]*)"', block)
    return float(m.group(1).strip()) if m else default

# --- 3. ממשק משתמש ---
st.title("🏭 מרכז ייצור דרוויש 47.4")
col_cfg, col_vis = st.columns([1, 2])

with col_cfg:
    st.subheader("הגדרות ייצור")
    rotate = st.checkbox("סובב חלק 90 מעלות", value=True)
    off_x = st.number_input("תוספת הרחקה X (מילימטר)", value=0.0)
    off_y = st.number_input("תוספת הרחקה Y (מילימטר)", value=0.0)
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

        ops = []
        for m in re.finditer(r'<(102|105|130|181)(.*?)(?=<|\!|\[H)', mpr, re.DOTALL):
            tag, bc = m.group(1), m.group(2)
            t_mpr = re.search(r'(?:TNO|T_|DU)="([^"]*)"', bc).group(1).strip() if re.search(r'(?:TNO|T_|DU)="([^"]*)"', bc) else "142"
            t_info = st.session_state.tool_db[st.session_state.tool_db['MPR_Name'] == t_mpr.replace("BV","")]
            if t_info.empty: t_info = st.session_state.tool_db[st.session_state.tool_db['T_CNC'] == "T2"]
            z_abs = round((thick - get_f('TI', bc) if tag in ['181','102'] else get_f('ZA', bc)), 3)
            geoid = re.search(r'EA="(\d+):', bc).group(1).strip() if re.search(r'EA="(\d+):', bc) else None
            pts = geos.get(geoid, [[get_f('XA', bc), get_f('YA', bc)]]) if tag != '102' else [[get_f('XA', bc), get_f('YA', bc)]]
            ops.append({
                't_cnc': t_info.iloc[0]['T_CNC'], 'desc': t_info.iloc[0]['תיאור'], 
                'z': z_abs, 'pts': pts, 'rad': t_info.iloc[0]['קוטר']/2, 
                'f': t_info.iloc[0]['Feed'], 's': t_info.iloc[0]['RPM'],
                'final': (z_abs <= 0.2 and tag != '102')
            })

        grouped = []
        for op in ops:
            found = False
            for g in grouped:
                if g['t_cnc'] == op['t_cnc'] and g['z'] == op['z'] and g['final'] == op['final']:
                    g['items'].append(op); found = True; break
            if not found: grouped.append({'t_cnc': op['t_cnc'], 'z': op['z'], 'final': op['final'], 's': op['s'], 'items': [op]})

        with col_cfg:
            st.write(f"### 📦 ניהול בלוקים")
            block_data = []
            for i, b in enumerate(grouped):
                label = "🔴 סופי" if b['final'] else "🔵 פנימי"
                with st.expander(f"{label}: {b['t_cnc']} ({b['z']}mm)"):
                    is_active = st.checkbox("כלול בייצור", value=True, key=f"act_{i}_{f_file.name}")
                    z_v = st.number_input("עומק פסיעה 1", value=b['z'], key=f"z1_{i}_{f_file.name}")
                    passes = [z_v]
                    if st.checkbox("הוסף פסיעה", key=f"p_{i}_{f_file.name}"):
                        passes.append(st.number_input("עומק פסיעה 2", value=0.0, key=f"z2_{i}_{f_file.name}"))
                    block_data.append({'id': i, 'active': is_active, 'passes': passes, 'final': b['final'], 't_cnc': b['t_cnc']})

            internal_ids = [d['id'] for d in block_data if not d['final'] and d['active']]
            final_ids = [d['id'] for d in block_data if d['final'] and d['active']]
            order = st.multiselect("סדר פעולות:", options=internal_ids, default=internal_ids, format_func=lambda x: f"{block_data[x]['t_cnc']} ({block_data[x]['passes'][0]}mm)")
            full_order = order + final_ids

        # ייצור NC
        nc = ["%", f"(N10 DARWISH 47.4 MASTER - {f_file.name})", "N20 G90 G54 G21"]
        n_c = 30
        for b_id in full_order:
            b_cfg = block_data[b_id]
            orig_b = grouped[b_id]
            nc.extend([f"N{n_c} M05", f"N{n_c+5} {orig_b['t_cnc']} M06", f"N{n_c+10} G43 H{orig_b['t_cnc'][1:]}", f"N{n_c+15} S{int(orig_b['s'])} M03"])
            n_c += 20
            for zv in b_cfg['passes']:
                for it in orig_b['items']:
                    path = calculate_miter_offset(it['pts'], it['rad'])
                    for pi, p in enumerate(path):
                        # הרחקה מצטברת ללא נרמול
                        nx, ny = p[0] + off_x, p[1] + off_y
                        if pi == 0:
                            nc.append(f"N{n_c} G00 X{nx-ramp_len:.3f} Y{ny:.3f}"); n_c += 5
                            nc.append(f"N{n_c} G01 Z{zv:.3f} X{nx:.3f} F2000"); n_c += 5
                        else:
                            nc.append(f"N{n_c} G01 X{nx:.3f} Y{ny:.3f} F{int(it['f'])}"); n_c += 5
                    nc.append(f"N{n_c} G00 Z36.0"); n_c += 5
        nc.extend([f"N{n_c} M05", f"N{n_c+5} M30", f"N{n_c+10} M200", "%"])
        
        with col_vis:
            fig = go.Figure()
            fig.update_layout(
                dragmode='pan',
                yaxis=dict(scaleanchor="x", scaleratio=1),
                xaxis=dict(constrain="domain"),
                margin=dict(l=0, r=0, t=0, b=0)
            )
            # שולחן
            fig.add_shape(type="rect", x0=0, y0=0, x1=1300, y1=3050, line=dict(color="RoyalBlue", width=1))
            
            for b_id in full_order:
                tool_shown = False
                for it in grouped[b_id]['items']:
                    ox, oy = zip(*it['pts'])
                    # גאומטריית מקור
                    fig.add_trace(go.Scatter(
                        x=[x + off_x for x in ox], y=[y + off_y for y in oy],
                        mode='lines', line=dict(dash='dash', color='gray'),
                        showlegend=False, hoverinfo='skip'
                    ))
                    # מסלול כלי
                    px, py = zip(*calculate_miter_offset(it['pts'], it['rad']))
                    fig.add_trace(go.Scatter(
                        x=[x + off_x for x in px], y=[y + off_y for y in py],
                        mode='lines', name=f"{grouped[b_id]['t_cnc']} ({grouped[b_id]['z']}mm)",
                        legendgroup=grouped[b_id]['t_cnc'],
                        showlegend=not tool_shown,
                        hovertemplate=f"כלי: {grouped[b_id]['t_cnc']}<br>תיאור: {it['desc']}<br>עומק: {zv}mm<extra></extra>"
                    ))
                    tool_shown = True
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': True})
            st.download_button(f"📥 הורד NC (גרסה 47.4)", "\n".join(nc), f"{f_file.name}_v474.nc")
