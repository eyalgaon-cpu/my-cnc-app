import streamlit as st
import re, math
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# Darwish 47.0 - PRODUCTION MASTER (SW OFFSET + SMART ANCHOR)
st.set_page_config(page_title="Darwish 47.0 Production", layout="wide")

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

with st.expander("🛠️ לשונית כלים (עריכה ידנית)", expanded=False):
    st.session_state.tool_db = st.data_editor(st.session_state.tool_db, num_rows="dynamic", key="tools_edit")

# --- 2. מנוע מתמטי ---
def get_offset_path(pts, r):
    if r == 0: return pts
    pts_arr = np.array(pts)
    new_pts = []
    for i in range(len(pts_arr)):
        if i < len(pts_arr) - 1:
            v = pts_arr[i+1] - pts_arr[i]
        else:
            v = pts_arr[i] - pts_arr[i-1]
        dist = np.linalg.norm(v)
        if dist == 0: continue
        n = np.array([-v[1], v[0]]) / dist # צידוד שמאלה
        new_pts.append((pts_arr[i] + n * r).tolist())
    return new_pts

def clean_txt(s): return str(s).replace("\r", "").replace("\n", "").strip()
def get_f(key, block, default=0.0):
    m = re.search(f'{key}="([^"]*)"', block)
    return float(clean_txt(m.group(1))) if m else default

# --- 3. ממשק משתמש ---
st.title("🏭 מרכז ייצור דרוויש 47.0")
col_cfg, col_vis = st.columns([1, 2])

with col_cfg:
    st.subheader("הגדרות ייצור")
    rotate = st.checkbox("סובב חלק 90 מעלות", value=True)
    normalize = st.checkbox("הצמד לפינת השולחן (0,0)", value=True, help="מתקן מיקומים של חלקים שבורחים הצידה בגלל הסיבוב")
    off_x = st.number_input("הרחקה נוספת X (מילימטר)", value=0.0)
    off_y = st.number_input("הרחקה נוספת Y (מילימטר)", value=0.0)
    ramp = st.slider("אורך נחיתה (Ramp)", 0, 50, 20)
    upl = st.file_uploader("טען קבצי MPR", accept_multiple_files=True)

if upl:
    for f in upl:
        mpr = f.getvalue().decode('utf-8', errors='ignore')
        thick = get_f('t', mpr, 19.0)
        
        # חילוץ גאומטריות
        geos = {}
        parts = re.split(r'\](\d+)', mpr)
        for i in range(1, len(parts), 2):
            pts = []
            for el in re.split(r'\$E\d+', parts[i+1]):
                xm, ym = re.search(r'X=([\d.-]+)', el), re.search(r'Y=([\d.-]+)', el)
                if xm and ym:
                    pts.append([float(ym.group(1)), float(xm.group(1))] if rotate else [float(xm.group(1)), float(ym.group(1))])
            if pts: geos[parts[i]] = pts

        # זיהוי פעולות ופיצול Internal/Final
        ops = []
        for m in re.finditer(r'<(102|105|130|181)(.*?)(?=<|\!|\[H)', mpr, re.DOTALL):
            tag, bc = m.group(1), m.group(2)
            t_mpr = clean_txt(re.search(r'(?:TNO|T_|DU)="([^"]*)"', bc).group(1)) if re.search(r'(?:TNO|T_|DU)="([^"]*)"', bc) else "142"
            t_info = st.session_state.tool_db[st.session_state.tool_db['MPR_Name'] == t_mpr.replace("BV","")]
            if t_info.empty: t_info = st.session_state.tool_db[st.session_state.tool_db['T_CNC'] == "T2"]
            
            z_abs = round((thick - get_f('TI', bc) if tag in ['181','102'] else get_f('ZA', bc)), 3)
            geoid = clean_txt(re.search(r'EA="(\d+):', bc).group(1)) if re.search(r'EA="(\d+):', bc) else None
            pts = geos.get(geoid, [[get_f('XA', bc), get_f('YA', bc)]]) if tag != '102' else [[get_f('XA', bc), get_f('YA', bc)]]
            
            ops.append({
                't_cnc': t_info.iloc[0]['T_CNC'], 'desc': t_info.iloc[0]['תיאור'], 
                'z': z_abs, 'pts': pts, 'rad': t_info.iloc[0]['קוטר']/2, 
                'f': t_info.iloc[0]['Feed'], 's': t_info.iloc[0]['RPM'],
                'final': (z_abs <= 0.2 and tag != '102')
            })

        # מציאת מינימום פרויקט לנירמול
        all_pts = [p for op in ops for p in op['pts']]
        min_x = min(p[0] for p in all_pts) if all_pts else 0
        min_y = min(p[1] for p in all_pts) if all_pts else 0

        # קיבוץ ותצוגה
        grouped = []
        for op in ops:
            found = False
            for g in grouped:
                if g['t_cnc'] == op['t_cnc'] and g['z'] == op['z'] and g['final'] == op['final']:
                    g['items'].append(op); found = True; break
            if not found: grouped.append({'t_cnc': op['t_cnc'], 'z': op['z'], 'final': op['final'], 's': op['s'], 'items': [op]})

        with col_cfg:
            st.write(f"### 📦 בלוקים: {f.name}")
            cfgs = {}
            for i, b in enumerate(sorted(grouped, key=lambda x: x['final'])):
                label = "🔴 סופי" if b['final'] else "🔵 פנימי"
                with st.expander(f"{label}: {b['t_cnc']}"):
                    z_val = st.number_input(f"עומק", value=b['z'], key=f"z_{i}_{f.name}")
                    cfgs[i] = [z_val]
                    if st.checkbox("הוסף פסיעה", key=f"p_{i}_{f.name}"):
                        cfgs[i].append(st.number_input("עומק 2", value=0.0, key=f"z2_{i}_{f.name}"))

        # ייצור NC
        nc = ["%", f"(N10 DARWISH 47.0 MASTER - {f.name})", "N20 G90 G54 G21"]
        n_count = 30
        for i, b in enumerate(sorted(grouped, key=lambda x: x['final'])):
            nc.extend([f"N{n_count} M05", f"N{n_count+10} {b['t_cnc']} M06", f"N{n_count+20} G43 H{b['t_cnc'][1:]}", f"N{n_count+30} S{int(b['s'])} M03"])
            n_count += 40
            for zv in cfgs[i]:
                for item in b['items']:
                    path = get_offset_path(item['pts'], item['rad'])
                    for pi, p in enumerate(path):
                        # נירמול ותוספת הרחקה
                        nx = p[0] - (min_x if normalize else 0) + off_x
                        ny = p[1] - (min_y if normalize else 0) + off_y
                        if pi == 0:
                            nc.append(f"N{n_count} G00 X{nx-ramp:.3f} Y{ny:.3f}")
                            nc.append(f"N{n_count+10} G01 Z{zv:.3f} X{nx:.3f} F2000")
                            n_count += 20
                        else:
                            nc.append(f"N{n_count} G01 X{nx:.3f} Y{ny:.3f} F{int(item['f'])}")
                            n_count += 10
                    nc.append(f"N{n_count} G00 Z36.0"); n_count += 10
        nc.extend([f"N{n_count} M05", f"N{n_count+10} M30", f"N{n_count+20} M200", "%"])
        
        with col_vis:
            fig = go.Figure()
            fig.add_shape(type="rect", x0=0, y0=0, x1=1300, y1=3050, line=dict(color="RoyalBlue", width=2))
            for b in grouped:
                for it in b['items']:
                    ox, oy = zip(*it['pts'])
                    fig.add_trace(go.Scatter(x=[x - (min_x if normalize else 0) + off_x for x in ox], y=[y - (min_y if normalize else 0) + off_y for y in oy], mode='lines', line=dict(dash='dash', color='gray'), hoverinfo='skip'))
                    opth = get_offset_path(it['pts'], it['rad'])
                    px, py = zip(*opth)
                    fig.add_trace(go.Scatter(x=[x - (min_x if normalize else 0) + off_x for x in px], y=[y - (min_y if normalize else 0) + off_y for y in py], mode='lines', name=f"{b['t_cnc']}"))
            st.plotly_chart(fig, use_container_width=True)
            st.download_button(f"📥 הורד NC ל-{f.name}", "\n".join(nc), f.name.replace(".mpr", ".nc"))
