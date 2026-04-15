import streamlit as st
import re, math
import plotly.graph_objects as go

# Darwish PRO 46.0 - PRODUCTION MASTER (WEIHONG NC60c OFFICIAL)
# Built: 2026-04-15 | Status: Pure Specs Deployment
st.set_page_config(page_title="Darwish 46.0 Production", layout="wide")

# --- הגדרות ליבה וחוקי ברזל ---
TOOL_MAP_BASE = {
    "130": "T13", "137": "T1", "128": "T4", "158": "T3",
    "142": "T2", "140": "T11", "147": "T8",
    "BV35": "T6", "BV15": "T49", "BV8": "T47", "BV5": "T44"
}

if 'profiles' not in st.session_state:
    st.session_state.profiles = {"אבי": {"tools": [
        {"T_CNC": "T1", "קוטר": 40.0}, {"T_CNC": "T2", "קוטר": 6.0},
        {"T_CNC": "T3", "קוטר": 8.0}, {"T_CNC": "T4", "קוטר": 12.0},
        {"T_CNC": "T8", "קוטר": 19.0}, {"T_CNC": "T11", "קוטר": 3.0},
        {"T_CNC": "T13", "קוטר": 0.2}, {"T_CNC": "T6", "קוטר": 35.0},
        {"T_CNC": "T49", "קוטר": 15.0}, {"T_CNC": "T47", "קוטר": 8.0},
        {"T_CNC": "T44", "קוטר": 5.0}, {"T_CNC": "T45", "קוטר": 5.0}
    ], "bed_x": 1300, "bed_y": 3050}}

# --- פונקציות עזר טכניות ---
def clean_txt(s): return str(s).replace("\r", "").replace("\n", "").strip()

def get_f(key, block, default=0.0):
    m = re.search(f'{key}="([^"]*)"', block)
    return float(clean_txt(m.group(1))) if m else default

def optimize_path(items):
    """מיטוב מסלול למניעת תנועות סרק מיותרות"""
    if not items: return []
    res, curr, rem = [], {'x': 0, 'y': 0}, items[:]
    while rem:
        nxt = min(rem, key=lambda i: math.sqrt((curr['x']- (i['pts'][0][0] if 'pts' in i else i['x']))**2 + (curr['y']- (i['pts'][0][1] if 'pts' in i else i['y']))**2))
        res.append(nxt); rem.remove(nxt)
        curr = {'x': nxt['pts'][-1][0], 'y': nxt['pts'][-1][1]} if 'pts' in nxt else nxt
    return res

# --- מנוע המרה מרכזי ---
def convert_mpr_to_nc_v46(mpr_text, rotate_90, anchor_x, anchor_y, z_global_offset, tool_mapping, block_z_dict, tool_order, filename):
    thickness = get_f('t', mpr_text, 19.0)
    drills, mills, geometries = [], [], {}

    # 1. חילוץ גאומטריות (Polylines)
    sections = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(sections), 2):
        pts = []
        for element in re.split(r'\$E\d+', sections[i+1]):
            x_m, y_m = re.search(r'X=([\d.-]+)', element), re.search(r'Y=([\d.-]+)', element)
            if x_m and y_m:
                xv, yv = float(x_m.group(1)), float(y_m.group(1))
                pts.append([yv, xv] if rotate_90 else [xv, yv])
        if pts: geometries[sections[i]] = pts

    # 2. מנוע קידוחים (<102) - ללא פשרות
    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1); ti = get_f('TI', b)
        t_mpr = clean_txt(re.search(r'DU="([^"]*)"', b).group(1)) if re.search(r'DU="([^"]*)"', b) else "5"
        xa, ya = (get_f('YA', b), get_f('XA', b)) if rotate_90 else (get_f('XA', b), get_f('YA', b))
        drills.append({
            'x': xa, 'y': ya, 
            'z': round((thickness - ti) + z_global_offset, 3), 
            't': tool_mapping.get(t_mpr, "T44")
        })

    # 3. מנוע כרסום (<105, <130, <181) - שיטת Pure Specs
    for op_idx, m_match in enumerate(re.finditer(r'<(105|130|181)(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL)):
        bc, tag = m_match.group(2), m_match.group(1)
        t_mpr = clean_txt(re.search(r'(?:TNO|T_)="([^"]*)"', bc).group(1)) if re.search(r'(?:TNO|T_)="([^"]*)"', bc) else "142"
        ti_val = get_f('TI', bc) if tag == '181' else get_f('ZA', bc)
        z_abs = (thickness - ti_val if tag == '181' else ti_val) + z_global_offset
        geoid = clean_txt(re.search(r'EA="(\d+):', bc).group(1)) if re.search(r'EA="(\d+):', bc) else None
        if geoid in geometries:
            mills.append({
                'id': op_idx, 
                't': tool_mapping.get(t_mpr, "T2"), 
                'z': round(z_abs, 3), 
                'pts': [p[:] for p in geometries[geoid]]
            })

    # 4. נורמליזציה לעוגן
    all_x = [d['x'] for d in drills] + [p[0] for m in mills for p in m['pts']]
    all_y = [d['y'] for d in drills] + [p[1] for m in mills for p in m['pts']]
    min_x, min_y = min(all_x) if all_x else 0, min(all_y) if all_y else 0
    for d in drills: d['x'] = d['x'] - min_x + anchor_x; d['y'] = d['y'] - min_y + anchor_y
    for m in mills:
        for p in m['pts']: p[0] = p[0] - min_x + anchor_x; p[1] = p[1] - min_y + anchor_y

    # 5. ייצור קוד NC (Syntax: WEIHONG NC60c)
    line_num = 10
    def n(): nonlocal line_num; r = f"N{line_num}"; line_num += 10; return r

    nc = ["%", f"({n()} DARWISH 46.0 PRODUCTION - {filename})", f"{n()} G90 G54 G21"]
    
    for t_id in tool_order:
        t_drills = optimize_path([d for d in drills if d['t'] == t_id])
        t_mills = optimize_path([m for m in mills if m['t'] == t_id])
        
        if t_drills or t_mills:
            nc.extend([
                f"{n()} M05", 
                f"{n()} {t_id} M06", 
                f"{n()} G00 G43 H{t_id.replace('T','')}", # פיצוי אורך קשיח מה-PDF
                f"{n()} S18000 M03"
            ])
            
            # ביצוע קידוחים
            if t_drills:
                for d in t_drills:
                    nc.extend([
                        f"{n()} G00 X{d['x']:.3f} Y{d['y']:.3f}", 
                        f"{n()} G01 Z{d['z']:.3f} F1000", 
                        f"{n()} G00 Z36.0"
                    ])
            
            # ביצוע כרסומים עם צידוד (G41/G42)
            if t_mills:
                for m in t_mills:
                    # שימוש בעומק מותאם אישית מהממשק אם קיים
                    z_list = block_z_dict.get(f"{filename}_{m['id']}", [m['z']])
                    for z_val in z_list:
                        sx, sy = m['pts'][0][0], m['pts'][0][1]
                        # Lead-in אלכסוני לבטיחות הצידוד
                        nc.extend([
                            f"{n()} G00 X{sx-20:.3f} Y{sy-20:.3f}", 
                            f"{n()} G01 Z{z_val:.3f} F2000"
                        ])
                        
                        # הפעלת צידוד רדיוס
                        comp = "G41" if t_id == "T2" else "G42"
                        d_word = f"D{t_id.replace('T','')}"
                        nc.append(f"{n()} {comp} {d_word} G01 X{sx:.3f} Y{sy:.3f} F3000")
                        
                        for p in m['pts'][1:]:
                            nc.append(f"{n()} G01 X{p[0]:.3f} Y{p[1]:.3f} F3000")
                        
                        nc.extend([f"{n()} G40", f"{n()} G00 Z36.0"])

    nc.extend([f"{n()} M05", f"{n()} M30", f"{n()} M200", "%"])
    return "\n".join(nc), drills, mills

# --- ממשק משתמש (Streamlit Frontend) ---
st.sidebar.title("🛠️ Darwish PRO 46.0")
cfg = st.session_state.profiles["אבי"]
rot = st.sidebar.checkbox("סובב חלק 90 מעלות", value=True)
z_off = st.sidebar.slider("כיול Z גלובלי (מילימטר)", -3.0, 3.0, 0.0, 0.1)

upl = st.file_uploader("טען קבצי MPR לייצור", accept_multiple_files=True)

if upl:
    for f in upl:
        content = f.getvalue().decode('utf-8', errors='ignore')
        with st.sidebar.expander(f"⚙️ הגדרות: {f.name}", expanded=True):
            ax = st.number_input("עוגן X (מיקום על השולחן)", value=30.0, key=f"ax_{f.name}")
            ay = st.number_input("עוגן Y (מיקום על השולחן)", value=30.0, key=f"ay_{f.name}")
            
            # זיהוי כלים אוטומטי מהקובץ
            mpr_tools = sorted(list(set(re.findall(r'(?:TNO|T_|DU)="([^"]*)"', content))))
            t_map = {}
            for tid in mpr_tools:
                suggested = TOOL_MAP_BASE.get(tid.replace("BV",""), "T2")
                opts = [t['T_CNC'] for t in cfg['tools']]
                t_map[tid] = st.selectbox(f"מיפוי כלי {tid}:", opts, index=opts.index(suggested) if suggested in opts else 0, key=f"m_{f.name}_{tid}")
            
            # חישוב מקדים לתצוגת בלוקים
            _, temp_d, temp_m = convert_mpr_to_nc_v46(content, rot, ax, ay, z_off, t_map, {}, [], f.name)
            
            # עריכת עומקים פרטנית
            bz_dict = {}
            for m in temp_m:
                bz_dict[f"{f.name}_{m['id']}"] = [st.number_input(f"עומק בלוק {m['id']} (Z):", value=m['z'], key=f"z_{f.name}_{m['id']}")]
            
            # ניהול סדר עבודה
            avail = sorted(list(set([m['t'] for m in temp_m] + [d['t'] for d in temp_d])))
            order = st.multiselect("סדר עבודה כלים:", avail, default=avail, key=f"o_{f.name}")

        final_nc, d_list, m_list = convert_mpr_to_nc_v46(content, rot, ax, ay, z_off, t_map, bz_dict, order, f.name)
        
        # תצוגה גרפית אינטראקטיבית
        fig = go.Figure()
        fig.add_shape(type="rect", x0=0, y0=0, x1=cfg['bed_x'], y1=cfg['bed_y'], line=dict(color="RoyalBlue", width=2))
        for m in m_list:
            xp, yp = zip(*m['pts'])
            fig.add_trace(go.Scatter(x=xp, y=yp, mode='lines', name=f"Milling {m['t']}"))
        for d in d_list:
            fig.add_trace(go.Scatter(x=[d['x']], y=[d['y']], mode='markers', name=f"Drill {d['t']}", marker=dict(size=10)))
        
        fig.update_layout(width=750, height=850, title=f"תצוגה מקדימה: {f.name}", xaxis_title="X", yaxis_title="Y")
        st.plotly_chart(fig, use_container_width=True)
        
        st.download_button(f"📥 הורד NC (גרסה 46.0 Production)", final_nc, f.name.replace(".mpr", ".nc"))

else:
    st.info("ממתין לטעינת קבצי MPR...")
