import streamlit as st
import re, math
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# Darwish 47.0 - THE SOFTWARE OFFSET MASTER (G40 PRODUCTION)
st.set_page_config(page_title="Darwish 47.0 Production", layout="wide")

# --- 1. ניהול מסד נתוני כלים (Tool Tab) ---
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
    st.session_state.tool_db = st.data_editor(st.session_state.tool_db, num_rows="dynamic", key="master_tools")
    st.info("כאן מעדכנים קטרים אחרי השחזה. האפליקציה תחשב את האופסט בהתאם.")

# --- 2. פונקציות מתמטיות (Software Offset & Ramping) ---
def calculate_offset_path(points, tool_radius):
    if tool_radius <= 0: return points
    pts = np.array(points)
    new_pts = []
    for i in range(len(pts)):
        if i < len(pts) - 1:
            v = pts[i+1] - pts[i]
        else:
            v = pts[i] - pts[i-1]
        dist = np.linalg.norm(v)
        if dist == 0: continue
        # וקטור נורמל לצידוד (G41 - שמאלה מהקו)
        n = np.array([-v[1], v[0]]) / dist
        new_pts.append((pts[i] + n * tool_radius).tolist())
    return new_pts

def clean_txt(s): return str(s).replace("\r", "").replace("\n", "").strip()
def get_f(key, block, default=0.0):
    m = re.search(f'{key}="([^"]*)"', block)
    return float(clean_txt(m.group(1))) if m else default

# --- 3. ממשק ייצור מרכזי ---
st.title("🏭 מרכז ייצור דרוויש 47.0")
col_settings, col_viewer = st.columns([1, 2])

with col_settings:
    st.subheader("הגדרות פלטה")
    rotate_90 = st.checkbox("סובב חלק 90 מעלות", value=True)
    user_off_x = st.number_input("הרחקה ידנית X (מעבר ל-MPR)", value=0.0)
    user_off_y = st.number_input("הרחקה ידנית Y (מעבר ל-MPR)", value=0.0)
    ramp_val = st.slider("אורך נחיתה (Ramp)", 0, 50, 20)
    upl = st.file_uploader("טען קובץ MPR", accept_multiple_files=True)

if upl:
    for f in upl:
        mpr_content = f.getvalue().decode('utf-8', errors='ignore')
        thickness = get_f('t', mpr_content, 19.0)
        
        # חילוץ גאומטריות
        geometries = {}
        sections = re.split(r'\](\d+)', mpr_content)
        for i in range(1, len(sections), 2):
            pts = []
            for element in re.split(r'\$E\d+', sections[i+1]):
                x_m, y_m = re.search(r'X=([\d.-]+)', element), re.search(r'Y=([\d.-]+)', element)
                if x_m and y_m:
                    xv, yv = float(x_m.group(1)), float(y_m.group(1))
                    pts.append([yv, xv] if rotate_90 else [xv, yv])
            if pts: geometries[sections[i]] = pts

        # ניתוח פעולות
        ops = []
        for m_match in re.finditer(r'<(102|105|130|181)(.*?)(?=<|\!|\[H)', mpr_content, re.DOTALL):
            tag, bc = m_match.group(1), m_match.group(2)
            t_mpr = clean_txt(re.search(r'(?:TNO|T_|DU)="([^"]*)"', bc).group(1)) if re.search(r'(?:TNO|T_|DU)="([^"]*)"', bc) else "142"
            
            # חיפוש נתוני כלי
            tool_info = st.session_state.tool_db[st.session_state.tool_db['MPR_Name'] == t_mpr.replace("BV","")]
            if tool_info.empty:
                tool_info = st.session_state.tool_db[st.session_state.tool_db['T_CNC'] == "T2"]
            
            ti_val = get_f('TI', bc) if tag in ['181','102'] else get_f('ZA', bc)
            z_abs = round((thickness - ti_val if tag in ['181','102'] else ti_val), 3)
            geoid = clean_txt(re.search(r'EA="(\d+):', bc).group(1)) if re.search(r'EA="(\d+):', bc) else None
            pts = geometries.get(geoid, [[get_f('XA', bc), get_f('YA', bc)]]) if tag != '102' else [[get_f('XA', bc), get_f('YA', bc)]]
            
            ops.append({
                'tag': tag, 't_mpr': t_mpr, 't_cnc': tool_info.iloc[0]['T_CNC'], 
                'desc': tool_info.iloc[0]['תיאור'], 'z_orig': z_abs, 'pts': pts,
                'radius': tool_info.iloc[0]['קוטר'] / 2, 'feed': tool_info.iloc[0]['Feed'],
                'rpm': tool_info.iloc[0]['RPM'], 'is_final': (z_abs <= 0.2 and tag != '102')
            })

        # קיבוץ לבלוקים
        grouped_ops = []
        for op in ops:
            found = False
            for g in grouped_ops:
                if g['t_cnc'] == op['t_cnc'] and g['z_orig'] == op['z_orig'] and g['is_final'] == op['is_final']:
                    g['items'].append(op); found = True; break
            if not found:
                grouped_ops.append({
                    't_cnc': op['t_cnc'], 't_mpr': op['t_mpr'], 'desc': op['desc'], 
                    'z_orig': op['z_orig'], 'is_final': op['is_final'], 'rpm': op['rpm'],
                    'items': [op]
                })

        # תצוגה ועריכה
        with col_settings:
            st.write(f"### 📦 בלוקים: {f.name}")
            block_configs = {}
            sorted_blocks = sorted(grouped_ops, key=lambda x: x['is_final'])
            
            for idx, block in enumerate(sorted_blocks):
                label = "🔴 סופי (Final)" if block['is_final'] else "🔵 פנימי (Internal)"
                with st.expander(f"{label}: {block['t_cnc']} ({block['desc']})", expanded=True):
                    z1 = st.number_input("עומק פסיעה 1", value=block['z_orig'], key=f"z1_{idx}_{f.name}")
                    passes = [z1]
                    if st.checkbox("הוסף פסיעה", key=f"add_{idx}_{f.name}"):
                        z2 = st.number_input("עומק פסיעה 2", value=0.0, key=f"z2_{idx}_{f.name}")
                        passes.append(z2)
                    block_configs[idx] = passes

        # ייצור NC (שימוש במונה פשוט במקום nonlocal)
        current_n = [10]
        def get_n():
            n_str = f"N{current_n[0]}"
            current_n[0] += 10
            return n_str

        nc_parts = ["%", f"({get_n()} DARWISH 47.0 MASTER - {f.name})", f"{get_n()} G90 G54 G21"]
        
        for idx, block in enumerate(sorted_blocks):
            nc_parts.extend([
                f"{get_n()} M05", 
                f"{get_n()} {block['t_cnc']} M06", 
                f"{get_n()} G43 H{block['t_cnc'].replace('T','')}", 
                f"{get_n()} S{int(block['rpm'])} M03"
            ])
            
            for z_val in block_configs[idx]:
                for item in block['items']:
                    # חישוב אופסט תוכנה (G40)
                    path = calculate_offset_path(item['pts'], item['radius'])
                    start = path[0]
                    # נחיתת Ramp
                    nc_parts.append(f"{get_n()} G00 X{start[0] + user_off_x - ramp_val:.3f} Y{start[1] + user_off_y:.3f}")
                    nc_parts.append(f"{get_n()} G01 Z{z_val:.3f} X{start[0] + user_off_x:.3f} F2000")
                    for p in path[1:]:
                        nc_parts.append(f"{get_n()} G01 X{p[0] + user_off_x:.3f} Y{p[1] + user_off_y:.3f} F{int(item['feed'])}")
                    nc_parts.append(f"{get_n()} G00 Z36.0")
        
        nc_parts.extend([f"{get_n()} M05", f"{get_n()} M30", f"{get_n()} M200", "%"])
        
        with col_viewer:
            fig = go.Figure()
            fig.add_shape(type="rect", x0=0, y0=0, x1=1300, y1=3050, line=dict(color="RoyalBlue", width=2))
            for block in sorted_blocks:
                for item in block['items']:
                    orig_x, orig_y = zip(*item['pts'])
                    fig.add_trace(go.Scatter(x=orig_x, y=orig_y, mode='lines', line=dict(dash='dash', color='gray'), hoverinfo='skip'))
                    off_pts = calculate_offset_path(item['pts'], item['radius'])
                    ox, oy = zip(*off_pts)
                    fig.add_trace(go.Scatter(x=ox, y=oy, mode='lines', name=f"{block['t_cnc']}", hovertemplate=f"כלי: {block['t_cnc']}<br>עומק: {block['z_orig']}"))
            
            st.plotly_chart(fig, use_container_width=True)
            st.download_button(f"📥 הורד NC ל-{f.name}", "\n".join(nc_parts), f.name.replace(".mpr", ".nc"))
