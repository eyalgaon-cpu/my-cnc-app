import streamlit as st
import re, os
import pandas as pd
import math
import plotly.graph_objects as go

# הגדרות דף
st.set_page_config(page_title="Darwish CNC Pro 41.1", layout="wide")

# ניהול פרופילי מכונות ב-Session State
if 'profiles' not in st.session_state:
    st.session_state.profiles = {
        "אבי": {
            "tools": [
                {"T_CNC": "T2", "קוטר": 6.0, "תיאור": "כרסום 6", "צבע": "red", "תיקון_Z": 0.0},
                {"T_CNC": "T47", "קוטר": 8.0, "תיאור": "מקדח 8", "צבע": "green", "תיקון_Z": -1.0},
                {"T_CNC": "T46", "קוטר": 10.0, "תיאור": "מקדח 10", "צבע": "blue", "תיקון_Z": -0.5},
                {"T_CNC": "T6", "קוטר": 35.0, "תיאור": "מקדח 35", "צבע": "orange", "תיקון_Z": -0.1}
            ],
            "z_off": 0.0, "mx": 0.0, "my": 0.0
        },
        "מושיקו": {
            "tools": [
                {"T_CNC": "T10", "קוטר": 12.0, "תיאור": "כרסום 12", "צבע": "purple", "תיקון_Z": 0.0}
            ],
            "z_off": 0.0, "mx": 0.0, "my": 0.0
        }
    }

if 'current_machine' not in st.session_state:
    st.session_state.current_machine = "אבי"

def get_safe_float(key, block, default=0.0):
    match = re.search(f'{key}="([^"]*)"', block)
    if not match: return default
    try: return float(match.group(1))
    except:
        nums = re.findall(r'[\d.-]+', match.group(1))
        return float(nums[0]) if nums else default

def convert_logic(mpr_text, machine_config, rotate_90, zero_nesting, margin_x, margin_y, global_z_off):
    thickness = get_safe_float('t', mpr_text, 19.0)
    tool_df = pd.DataFrame(machine_config['tools'])
    
    # מיפוי כלים מה-MPR (כולל בלוק 105 של פייטה)
    mpr_tools_found = []
    for m in re.finditer(r'<(101|102|105|130)(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        block_type = m.group(1)
        content = m.group(2)
        tno = re.search(r'(TNO|T_CNC|DU)="([^"]*)"', content)
        if tno: mpr_tools_found.append(tno.group(2))

    # בניית מפת כלים (MPR -> Machine)
    unique_mpr = sorted(list(set(mpr_tools_found)))
    
    raw_drills = []
    # סריקת קידוחים (102)
    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1)
        xa, ya, ti = [get_safe_float(k, b) for k in ['XA', 'YA', 'TI']]
        t_mpr = re.search(r'DU="([^"]*)"', b).group(1)
        
        # חיפוש הכלי בטבלה לפי קוטר או מספר
        conf = tool_df[tool_df['קוטר'] == float(t_mpr)].to_dict('records')
        if not conf: continue
        conf = conf[0]
        
        f_z = (thickness - ti) + global_z_off - conf.get("תיקון_Z", 0.0)
        raw_drills.append({'x': xa, 'y': ya, 'z': f_z, 't': conf['T_CNC'], 'desc': conf['תיאור'], 'dia': conf['קוטר'], 'color': conf['צבע']})

    geos = {}
    parts = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(parts), 2):
        pts = []
        for elem in re.split(r'\$E\d+', parts[i+1]):
            x_m, y_m = re.search(r'X=([\d.-]+)', elem), re.search(r'Y=([\d.-]+)', elem)
            if x_m and y_m: pts.append([float(x_m.group(1)), float(y_m.group(1))])
        if pts: geos[parts[i]] = pts

    # סיבוב ועיבוד מידות
    if rotate_90:
        for d in raw_drills: d['x'], d['y'] = -d['y'], d['x']
        for pts in geos.values():
            for p in pts: p[0], p[1] = -p[1], p[0]

    all_x = [d['x'] for d in raw_drills] + [p[0] for pts in geos.values() for p in pts]
    all_y = [d['y'] for d in raw_drills] + [p[1] for pts in geos.values() for p in pts]
    dx, dy = (max(all_x)-min(all_x), max(all_y)-min(all_y)) if all_x else (0,0)

    if zero_nesting and all_x:
        mx_part, my_part = min(all_x), min(all_y)
        for d in raw_drills: d['x'] -= mx_part; d['y'] -= my_part
        for pts in geos.values():
            for p in pts: p[0] -= mx_part; p[1] -= my_part

    for d in raw_drills: d['x'] += margin_x; d['y'] += margin_y
    for pts in geos.values():
        for p in pts: p[0] += margin_x; p[1] += margin_y

    return raw_drills, geos, thickness, dx, dy, unique_mpr

def plot_2d_pro(drills, geos, thickness, dx, dy, filename):
    st.markdown(f"### 📄 קובץ: {filename}")
    st.info(f"📏 **מידות:** {dx:.2f} × {dy:.2f} מילימטר | עובי: {thickness:.2f} מילימטר")
    
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=1300, y1=3050, fillcolor="whitesmoke", line=dict(color="black", width=2), layer="below")
    
    for bid, pts in geos.items():
        if len(pts) > 1:
            x_p, y_p = zip(*pts)
            c_dx, c_dy = max(x_p) - min(x_p), max(y_p) - min(y_p)
            fig.add_trace(go.Scatter(x=x_p, y=y_p, mode='lines', line=dict(color='red', width=2), name=f"קונטור {bid}", text=f"חלק: {c_dx:.2f} × {c_dy:.2f} מילימטר", hoverinfo="text+name"))

    for d in drills:
        fig.add_trace(go.Scatter(
            x=[d['x']], y=[d['y']], mode='markers',
            marker=dict(size=d['dia'], color=d['color'], line=dict(width=1, color='black')),
            text=[d['desc']], customdata=[[d['t'], thickness - d['z']]],
            hovertemplate="<span style='font-size:16px;'><b>%{customdata[0]}</b></span><br>כלי: %{text}<br>עומק: %{customdata[1]:.2f} מילימטר<extra></extra>"
        ))

    fig.update_xaxes(title="ציר X (מילימטר)", range=[-100, 1400], showline=True, mirror=True)
    fig.update_yaxes(title="ציר Y (מילימטר)", range=[-100, 3150], scaleanchor="x", scaleratio=1, showline=True, mirror=True)
    fig.update_layout(width=900, height=850, template="plotly_white", showlegend=False)
    # החזרת הזום עם גלגלת העכבר
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

# ממשק משתמש
st.sidebar.title("🛠️ ממשק דרוויש 41.1")
machine_names = list(st.session_state.profiles.keys())
selected_machine = st.sidebar.selectbox("בחר מכונה:", machine_names, index=machine_names.index(st.session_state.current_machine))
st.session_state.current_machine = selected_machine
cfg = st.session_state.profiles[selected_machine]

st.sidebar.markdown("---")
nest = st.sidebar.checkbox("צמד לפינה (Nesting)", value=True)
rot = st.sidebar.checkbox("סובב Portrait (90°)", value=True)
# עדכון לוגיקה: שלילי מעמיק, חיובי מרים
gz_off = st.sidebar.slider("כיול Z גלובלי (מילימטר)", -5.0, 5.0, cfg['z_off'], 0.1)
mx = st.sidebar.number_input("מרג'ין X (מילימטר)", value=cfg['mx'])
my = st.sidebar.number_input("מרג'ין Y (מילימטר)", value=cfg['my'])

# שמירת הגדרות סיידבר לפרופיל
if st.sidebar.button("שמור כיולים למכונה זו"):
    st.session_state.profiles[selected_machine].update({"z_off": gz_off, "mx": mx, "my": my})
    st.sidebar.success("הכיולים נשמרו.")

st.markdown(f"### 🧰 ניהול מכונה: {selected_machine}")
with st.expander("ערוך רשימת כלים"):
    edited_df = st.data_editor(pd.DataFrame(cfg['tools']), num_rows="dynamic")
    if st.button("עדכן טבלת כלים"):
        st.session_state.profiles[selected_machine]['tools'] = edited_df.to_dict('records')

uploaded = st.file_uploader("טען קבצי MPR", accept_multiple_files=True)
if uploaded:
    for f in uploaded:
        drills, geos, thick, dx, dy, mpr_tools = convert_logic(f.getvalue().decode('utf-8', errors='ignore'), cfg, rot, nest, mx, my, gz_off)
        
        # מפת כלים (MPR vs Machine)
        st.warning(f"🔍 כלים שזוהו ב-MPR: {', '.join(mpr_tools)}")
        plot_2d_pro(drills, geos, thick, dx, dy, f.name)
