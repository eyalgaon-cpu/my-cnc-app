import streamlit as st
import re, math, json, os
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from shapely.geometry import Polygon

# Darwish 56.1 - MPR + DXF + CIX Support
# 56.0: הוספת ייצוא CIX (SCM/Biesse Maestro), תיקון DS=1 בחישוב מרכז קשת
# 54.0: שקלול קאנטים (Edge Banding)
# 53.73: תיקון h_d_sq (floating point בסמי-קשת), offset ב-hover text
# 53.70: תיקון DS off-by-one; 53.69: 128 נקודות + bbox אנליטי
st.set_page_config(page_title="Darwish 56.1 Local", layout="wide")

CONFIG_FILE = "darwish_config.json"

DEFAULT_TOOLS_ALON = [
    # --- מקדחים ---
    {"T_CNC": "T1",  "MPR_Name": "10.0",    "DXF_Name": "10 mm",   "תיאור": "מקדח 10 מילימטר (ארוך)",     "קוטר": 10.0,  "Z_Offset": 0.0, "RPM": 3500, "Feed": 2800},
    {"T_CNC": "T2",  "MPR_Name": "MISSING",  "DXF_Name": "",        "תיאור": "מקדח 19 מילימטר",            "קוטר": 19.0,  "Z_Offset": 0.0, "RPM": 3500, "Feed": 2000},
    {"T_CNC": "T3",  "MPR_Name": "8.0",      "DXF_Name": "8 mm",    "תיאור": "מקדח 8 מילימטר",             "קוטר": 8.0,   "Z_Offset": 0.0, "RPM": 3500, "Feed": 2800},
    {"T_CNC": "T4",  "MPR_Name": "3.0",      "DXF_Name": "3 mm",    "תיאור": "מקדח 3 מילימטר",             "קוטר": 3.0,   "Z_Offset": 0.0, "RPM": 3500, "Feed": 2300},
    {"T_CNC": "T5",  "MPR_Name": "6.0",      "DXF_Name": "6 mm",    "תיאור": "מקדח 6 מילימטר",             "קוטר": 6.0,   "Z_Offset": 0.0, "RPM": 3500, "Feed": 2800},
    {"T_CNC": "T6",  "MPR_Name": "35.0",     "DXF_Name": "35 mm",   "תיאור": "מקדח צירים 35 מילימטר",      "קוטר": 35.0,  "Z_Offset": 0.0, "RPM": 4000, "Feed": 1000},
    {"T_CNC": "T7",  "MPR_Name": "5.0",      "DXF_Name": "5 mm",    "תיאור": "מקדח 5 מילימטר (שפיץ)",      "קוטר": 5.0,   "Z_Offset": 0.0, "RPM": 3500, "Feed": 2800},
    {"T_CNC": "T8",  "MPR_Name": "MISSING",  "DXF_Name": "",        "תיאור": "מקדח 26 מילימטר",            "קוטר": 26.0,  "Z_Offset": 0.0, "RPM": 3500, "Feed": 1500},
    {"T_CNC": "T9",  "MPR_Name": "5.0",      "DXF_Name": "5 mm",    "תיאור": "מקדח 5 מילימטר",             "קוטר": 5.0,   "Z_Offset": 0.0, "RPM": 3500, "Feed": 2800},
    {"T_CNC": "T10", "MPR_Name": "15.0",     "DXF_Name": "15 mm",   "תיאור": "מקדח 15 מילימטר (ימין)",     "קוטר": 15.0,  "Z_Offset": 0.0, "RPM": 4000, "Feed": 2800},
    # --- כרסומים ---
    {"T_CNC": "vid_6",      "MPR_Name": "142",    "DXF_Name": "CUT 6",  "תיאור": "כרסום 6 מילימטר",                          "קוטר": 6.0,  "Z_Offset": 0.0, "RPM": 18000, "Feed": 12000},
    {"T_CNC": "vid_8",      "MPR_Name": "158",    "DXF_Name": "CUT 8",  "תיאור": "כרסום 8 מילימטר",                          "קוטר": 8.0,  "Z_Offset": 0.0, "RPM": 18000, "Feed": 12000},
    {"T_CNC": "Di_12_mdf",  "MPR_Name": "128",    "DXF_Name": "CUT 12", "תיאור": "כרסום 12 מילימטר MDF (עם שואב, עד 19מ-מ)", "קוטר": 12.0, "Z_Offset": 0.0, "RPM": 24000, "Feed": 18000},
    {"T_CNC": "Nesting_12", "MPR_Name": "MISSING","DXF_Name": "",       "תיאור": "כרסום 12 מילימטר נסטינג (עם שואב, עד 17מ-מ)","קוטר": 12.0, "Z_Offset": 0.0, "RPM": 18000, "Feed": 10000},
]

DEFAULT_TOOLS = [
    {"T_CNC": "T1",      "MPR_Name": "137",     "DXF_Name": "",        "תיאור": "כרסום 40 מילימטר (ניקוי פוקט)",        "קוטר": 40.0,  "Z_Offset": 0.0, "RPM": 18000, "Feed": 8000},
    {"T_CNC": "T2",      "MPR_Name": "142",     "DXF_Name": "CUT 6",   "תיאור": "כרסום יהלום 6 מילימטר",               "קוטר": 6.0,   "Z_Offset": 0.0, "RPM": 17000, "Feed": 14000},
    {"T_CNC": "T3",      "MPR_Name": "158",     "DXF_Name": "CUT 8",   "תיאור": "כרסום 8 מילימטר",                     "קוטר": 8.0,   "Z_Offset": 0.0, "RPM": 22000, "Feed": 13000},
    {"T_CNC": "T4",      "MPR_Name": "128",     "DXF_Name": "CUT 12",  "תיאור": "כרסום 12 מילימטר",                    "קוטר": 12.0,  "Z_Offset": 0.0, "RPM": 22000, "Feed": 13000},
    {"T_CNC": "T8",      "MPR_Name": "MISSING", "DXF_Name": "CUT 18",  "תיאור": "כרסום 19 מילימטר",                    "קוטר": 18.0,  "Z_Offset": 0.0, "RPM": 22000, "Feed": 12000},
    {"T_CNC": "T11",     "MPR_Name": "140",     "DXF_Name": "CUT 3",   "תיאור": "כרסום 3 מילימטר",                     "קוטר": 3.0,   "Z_Offset": 0.0, "RPM": 20000, "Feed": 9000},
    {"T_CNC": "T12",     "MPR_Name": "MISSING", "DXF_Name": "",        "תיאור": "כרסום 76 מילימטר (ניקוי פוקט גדול)", "קוטר": 76.2,  "Z_Offset": 0.0, "RPM": 12000, "Feed": 2000},
    {"T_CNC": "T15",     "MPR_Name": "MISSING", "DXF_Name": "CUT 5",   "תיאור": "כרסום 5 מילימטר",                    "קוטר": 5.0,   "Z_Offset": 0.0, "RPM": 22000, "Feed": 12000},
    {"T_CNC": "T23",     "MPR_Name": "MISSING", "DXF_Name": "",        "תיאור": "כרסום ארוך 12.7 מילימטר",            "קוטר": 12.7,  "Z_Offset": 0.0, "RPM": 20000, "Feed": 6000},
    {"T_CNC": "T13",     "MPR_Name": "130",     "DXF_Name": "",        "תיאור": "וי-ביט 90 מעלות - גירונג",            "קוטר": 38.0,  "Z_Offset": 0.0, "RPM": 20000, "Feed": 10000},
    {"T_CNC": "T14",     "MPR_Name": "MISSING", "DXF_Name": "",        "תיאור": "וי-ביט 120 מעלות",                   "קוטר": 32.0,  "Z_Offset": 0.0, "RPM": 18000, "Feed": 10000},
    {"T_CNC": "T6",      "MPR_Name": "35.0",    "DXF_Name": "35 mm",   "תיאור": "מקדח צירים 35 מילימטר",              "קוטר": 35.0,  "Z_Offset": 0.0, "RPM": 4000,  "Feed": 1000},
    {"T_CNC": "T44",     "MPR_Name": "5.0",     "DXF_Name": "5 mm",    "תיאור": "מקדח 5 מילימטר",                     "קוטר": 5.0,   "Z_Offset": 0.0, "RPM": 3500,  "Feed": 2800},
    {"T_CNC": "T45",     "MPR_Name": "MISSING", "DXF_Name": "",        "תיאור": "מקדח 5 מילימטר (חור עובר)",          "קוטר": 5.0,   "Z_Offset": 0.0, "RPM": 3500,  "Feed": 2800},
    {"T_CNC": "T47",     "MPR_Name": "8.0",     "DXF_Name": "8 mm",    "תיאור": "מקדח 8 מילימטר",                     "קוטר": 8.0,   "Z_Offset": 0.0, "RPM": 3500,  "Feed": 2800},
    {"T_CNC": "T48",     "MPR_Name": "3.0",     "DXF_Name": "3 mm",    "תיאור": "מקדח 3 מילימטר",                     "קוטר": 3.0,   "Z_Offset": 0.0, "RPM": 3500,  "Feed": 2300},
    {"T_CNC": "T49",     "MPR_Name": "15.0",    "DXF_Name": "15 mm",   "תיאור": "מקדח 15 מילימטר",                    "קוטר": 15.0,  "Z_Offset": 0.0, "RPM": 4000,  "Feed": 2800},
    {"T_CNC": "T42",     "MPR_Name": "MISSING", "DXF_Name": "",        "תיאור": "מקדח 5 מילימטר (שלישייה)",           "קוטר": 4.98,  "Z_Offset": 0.0, "RPM": 3500,  "Feed": 2800},
    {"T_CNC": "T46",     "MPR_Name": "MISSING", "DXF_Name": "10 mm",   "תיאור": "מקדח 10 מילימטר",                    "קוטר": 10.0,  "Z_Offset": 0.0, "RPM": 3500,  "Feed": 2800},
    {"T_CNC": "MISSING", "MPR_Name": "136",     "DXF_Name": "",        "תיאור": "כרסום 16 מילימטר (חסר במכונה)",      "קוטר": 16.0,  "Z_Offset": 0.0, "RPM": 18000, "Feed": 2000},
    {"T_CNC": "MISSING", "MPR_Name": "139",     "DXF_Name": "",        "תיאור": "כרסום 10 מילימטר (חסר במכונה)",      "קוטר": 10.0,  "Z_Offset": 0.0, "RPM": 18000, "Feed": 3000},
]

def save_config_auto():
    # שימוש בעותק נפרד כדי לא לשנות את ה-DataFrames ב-session_state
    profiles_raw = {}
    for name, df in st.session_state.get('machine_profiles', {'אבי': DEFAULT_TOOLS}).items():
        profiles_raw[name] = df.to_dict('records') if isinstance(df, pd.DataFrame) else df
    cfg = {
        "machine_profiles": profiles_raw,
        "active_machine": st.session_state.get('active_machine', 'אבי'),
        "safety_h": st.session_state.get('safety_h', 35.0),
        "off_x": st.session_state.get('off_x', 0.0),
        "off_y": st.session_state.get('off_y', 0.0),
        "gz": st.session_state.get('gz', 0.0)
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

def load_config_auto():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            profiles = cfg.get("machine_profiles", {'אבי': DEFAULT_TOOLS})
            st.session_state.machine_profiles = {k: pd.DataFrame(v) for k, v in profiles.items()}
            st.session_state.active_machine = cfg.get("active_machine", 'אבי')
            st.session_state.safety_h = cfg.get("safety_h", 35.0)
            st.session_state.off_x = cfg.get("off_x", 0.0)
            st.session_state.off_y = cfg.get("off_y", 0.0)
            st.session_state.gz = cfg.get("gz", 0.0)
            return True
    return False

# --- 2. אתחול ---
if 'machine_profiles' not in st.session_state:
    if not load_config_auto():
        st.session_state.machine_profiles = {
            'אבי':  pd.DataFrame(DEFAULT_TOOLS),
            'אלון': pd.DataFrame(DEFAULT_TOOLS_ALON),
        }
        st.session_state.active_machine = 'אבי'

with st.sidebar:
    st.header("🛠️ ניהול ייצור (Local Sync)")

    # --- בחירת מכונה ---
    profiles = st.session_state.machine_profiles
    machine_names = list(profiles.keys())
    active = st.session_state.get('active_machine', machine_names[0])
    if active not in machine_names: active = machine_names[0]

    col_m1, col_m2 = st.columns([2, 1])
    with col_m1:
        selected_machine = st.selectbox("🏭 מכונה פעילה:", machine_names, index=machine_names.index(active))
        if selected_machine != st.session_state.get('active_machine'):
            st.session_state.active_machine = selected_machine
            save_config_auto()
            st.rerun()
    with col_m2:
        st.write("")
        new_machine_name = st.text_input("שם חדש:", placeholder="מושיקו", label_visibility="collapsed", key="new_machine_input")
        if st.button("➕ הוסף", key="add_machine"):
            if new_machine_name and new_machine_name not in profiles:
                st.session_state.machine_profiles[new_machine_name] = pd.DataFrame(DEFAULT_TOOLS)
                st.session_state.active_machine = new_machine_name
                save_config_auto()
                st.rerun()

    # כפתור מחיקת מכונה (לא מאפשר למחוק את האחרונה)
    if len(machine_names) > 1:
        if st.button(f"🗑️ מחק '{selected_machine}'", key="del_machine"):
            del st.session_state.machine_profiles[selected_machine]
            st.session_state.active_machine = list(st.session_state.machine_profiles.keys())[0]
            save_config_auto()
            st.rerun()

    st.divider()

    # --- טבלת כלים של המכונה הנבחרת ---
    with st.expander(f"כלים: {selected_machine}", expanded=False):
        tool_db = st.session_state.machine_profiles[selected_machine]
        if not isinstance(tool_db, pd.DataFrame):
            tool_db = pd.DataFrame(tool_db)
            st.session_state.machine_profiles[selected_machine] = tool_db
        new_df = st.data_editor(tool_db, num_rows="dynamic", key=f"tools_{selected_machine}")
        if not isinstance(new_df, pd.DataFrame):
            new_df = pd.DataFrame(new_df)
        if not new_df.equals(tool_db):
            st.session_state.machine_profiles[selected_machine] = new_df
            save_config_auto()
        if st.button("אפס להגדרות יצרן", key="reset_tools"):
            st.session_state.machine_profiles[selected_machine] = pd.DataFrame(DEFAULT_TOOLS)
            save_config_auto()
            st.rerun()

    st.divider()
    safety_h = st.number_input("גובה בטיחות Z (מילימטר)", value=st.session_state.get('safety_h', 35.0), key='safety_h_in')
    off_x = st.number_input("הזזת פלטה ציר X (מילימטר)", value=st.session_state.get('off_x', 0.0), key='off_x_in')
    off_y = st.number_input("הזזת פלטה ציר Y (מילימטר)", value=st.session_state.get('off_y', 0.0), key='off_y_in')
    gz = st.number_input("תיקון Z גלובלי (מילימטר)", value=st.session_state.get('gz', 0.0), key='gz_in')

    if (safety_h != st.session_state.get('safety_h') or off_x != st.session_state.get('off_x') or
        off_y != st.session_state.get('off_y') or gz != st.session_state.get('gz')):
        st.session_state.safety_h = safety_h
        st.session_state.off_x = off_x
        st.session_state.off_y = off_y
        st.session_state.gz = gz
        save_config_auto()

# --- 3. ליבה מתמטית v52.2 ---
def _safe_float(val):
    try: return float(re.sub(r'[^0-9.\-]', '', str(val)))
    except: return 0.0

def rotate_pt_v518(x, y, angle_deg):
    rad = math.radians(angle_deg)
    return x * math.cos(rad) - y * math.sin(rad), x * math.sin(rad) + y * math.cos(rad)

def find_tool_numeric(mpr_id, df):
    try:
        target = round(_safe_float(mpr_id), 1)
        for _, row in df.iterrows():
            if round(_safe_float(row['MPR_Name']), 1) == target:
                is_missing = (row['T_CNC'] == "MISSING")
                return row, is_missing
    except: pass
    return {"T_CNC": "MISSING", "תיאור": f"כלי {mpr_id} לא מזוהה בטבלה", "קוטר": 6.0, "Z_Offset": 0.0, "RPM": 12000, "Feed": 2000}, True

def optimize_drill_path_v518(ops):
    if not ops: return ops
    optimized = [ops.pop(0)]
    while ops:
        last = optimized[-1]['pts'][0]
        next_idx = min(range(len(ops)), key=lambda i: (ops[i]['pts'][0][0]-last[0])**2 + (ops[i]['pts'][0][1]-last[1])**2)
        optimized.append(ops.pop(next_idx))
    return optimized

def apply_geo_offset(pts, offset):
    """Expand/shrink polygon by offset mm using shapely buffer (handles arcs correctly)."""
    if abs(offset) < 1e-9 or not pts or len(pts) < 3:
        return pts
    try:
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        expanded = poly.buffer(offset)
        if expanded.is_empty:
            return pts
        new_pts = [list(c) for c in expanded.exterior.coords]
        return new_pts
    except Exception:
        return pts

def apply_partial_edge_offset(pts, eb_thickness, sides):
    """Apply edge banding offset only to specified sides (rectangular parts only).
    sides: dict with keys top/bottom/left/right, True = has kant (shrink), False = no kant (keep).
    """
    if not pts or eb_thickness < 1e-9:
        return pts
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    new_min_x = min_x + (eb_thickness if sides.get('left',   True) else 0)
    new_max_x = max_x - (eb_thickness if sides.get('right',  True) else 0)
    new_min_y = min_y + (eb_thickness if sides.get('bottom', True) else 0)
    new_max_y = max_y - (eb_thickness if sides.get('top',    True) else 0)
    return [[new_min_x, new_min_y], [new_max_x, new_min_y],
            [new_max_x, new_max_y], [new_min_x, new_max_y],
            [new_min_x, new_min_y]]

def calculate_path_v518(pts, r, mpr_rk, is_pocket=False):
    if r <= 0 or len(pts) < 2: return pts
    pts_arr = np.array(pts); n = len(pts_arr)
    area = sum((pts_arr[i][0]*pts_arr[(i+1)%n][1] - pts_arr[(i+1)%n][0]*pts_arr[i][1]) for i in range(n))/2.0
    side = (1 if area > 0 else -1) if is_pocket else (1 if "WRKL" in mpr_rk else -1 if "WRKR" in mpr_rk else 0)
    if side == 0: return pts

    shifted = []
    for i in range(n-1):
        p1, p2 = pts_arr[i], pts_arr[i+1]; v = p2-p1; mag = np.linalg.norm(v)
        if mag == 0: continue
        normal = side * np.array([-v[1], v[0]]) / mag
        shifted.append((p1 + normal*r, p2 + normal*r))

    if not shifted: return pts

    def intersect(l1, l2):
        x1,y1=l1[0]; x2,y2=l1[1]; x3,y3=l2[0]; x4,y4=l2[1]
        den = (y4-y3)*(x2-x1)-(x4-x3)*(y2-y1)
        if abs(den)<1e-6: return l1[1]
        ua = ((x4-x3)*(y1-y3)-(y4-y3)*(x1-x3))/den
        return np.array([x1+ua*(x2-x1), y1+ua*(y2-y1)])

    def point_inside_polygon(p, poly):
        """בדיקה אם נקודה בתוך פולגון (ray casting)."""
        x, y = p[0], p[1]
        n_p = len(poly)
        inside = False
        j = n_p - 1
        for i_p in range(n_p):
            xi, yi = poly[i_p][0], poly[i_p][1]
            xj, yj = poly[j][0], poly[j][1]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
                inside = not inside
            j = i_p
        return inside

    def clamp_to_polygon(p, poly, r_g):
        """אם נקודה חורגת מגבול הפולגון, מחזיר את הנקודה הקרובה על הגבול."""
        if point_inside_polygon(p, poly):
            return p
        # נקודה על הקטע הקרוב ביותר
        best = p; best_dist = float('inf')
        n_p = len(poly)
        for i_p in range(n_p - 1):
            a = np.array(poly[i_p]); b = np.array(poly[i_p+1])
            ab = b - a; t = np.dot(p - a, ab) / (np.dot(ab, ab) + 1e-12)
            t = np.clip(t, 0, 1)
            proj = a + t * ab
            # הזזה פנימה ב-r_g
            edge_dir = ab / (np.linalg.norm(ab) + 1e-12)
            inward = np.array([-edge_dir[1], edge_dir[0]])
            if np.dot(inward, np.array(poly[0]) - proj) < 0:
                inward = -inward
            candidate = proj + inward * r_g
            dist = np.linalg.norm(p - proj)
            if dist < best_dist:
                best_dist = dist; best = candidate
        return best

    poly_pts = [list(pts_arr[i]) for i in range(len(pts_arr))]
    r_guard = r + 0.1

    # חישוב פינת סגירה
    closing_pt = intersect(shifted[-1], shifted[0])
    if is_pocket:
        closing_pt = clamp_to_polygon(closing_pt, poly_pts, r_guard)

    new_path = [tuple(closing_pt)]

    for i in range(len(shifted)-1):
        p_inter = intersect(shifted[i], shifted[i+1])
        if is_pocket:
            p_inter = clamp_to_polygon(p_inter, poly_pts, r_guard)
        new_path.append(tuple(p_inter))

    new_path.append(tuple(closing_pt))
    return new_path


# ============================================================
# DXF - פרסור והמרה לops (אותו פורמט כמו MPR)
# ============================================================

def parse_dxf_to_entities(text):
    """פרסור קובץ DXF עם תמיכה ב-POLYLINE+VERTEX+SEQEND.
    מסנן face-definition vertices (flag & 64 == 0).
    מחזיר dict: {layer_name: [list_of_point_lists]}"""
    lines = text.strip().splitlines()
    polys_by_layer = {}
    current_layer = ''
    in_poly = False
    in_vertex = False
    pts = []
    vx, vy = None, None
    vertex_flag = 0
    i = 0
    while i < len(lines) - 1:
        code = lines[i].strip()
        val  = lines[i+1].strip()
        i += 2
        if code == '0':
            if val == 'POLYLINE':
                in_poly = True; in_vertex = False
                pts = []; current_layer = ''
                vx, vy = None, None; vertex_flag = 0
            elif val == 'VERTEX' and in_poly:
                # שמור נקודה קודמת רק אם position vertex (flag bit6=64)
                if vx is not None and vy is not None and (vertex_flag & 64):
                    pts.append([vx, vy])
                in_vertex = True; vx, vy = None, None; vertex_flag = 0
            elif val == 'SEQEND' and in_poly:
                if vx is not None and vy is not None and (vertex_flag & 64):
                    pts.append([vx, vy])
                if current_layer and pts:
                    polys_by_layer.setdefault(current_layer, []).append(pts[:])
                in_poly = False; in_vertex = False
                pts = []; vx, vy = None, None; vertex_flag = 0
        elif code == '8' and in_poly and not in_vertex and not current_layer:
            current_layer = val
        elif code == '70' and in_vertex:
            try: vertex_flag = int(val)
            except: pass
        elif code == '10' and in_vertex:
            try: vx = float(val)
            except: pass
        elif code == '20' and in_vertex:
            try: vy = float(val)
            except: pass
    return polys_by_layer

def get_dxf_board_and_offset(polys_by_layer):
    """מזהה את הפלטה (הצורה המלבנית הגדולה ביותר),
    מחזיר (wp_l, wp_w, off_x, off_y) — מידות ואופסט לנרמול."""
    best_area = 0
    best = (2440.0, 1220.0, 0.0, 0.0)
    for layer, shapes in polys_by_layer.items():
        for pts in shapes:
            if len(pts) < 3: continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            w = max(xs) - min(xs)
            h = max(ys) - min(ys)
            area = w * h
            if area > best_area:
                best_area = area
                # wp_l = הממד הארוך, wp_w = הממד הקצר
                if w >= h:
                    best = (w, h, min(xs), min(ys))
                else:
                    best = (h, w, min(xs), min(ys))
    return best  # (wp_l, wp_w, off_x, off_y)

def identify_dxf_layer(layer_name):
    """זיהוי שכבה לפי שם. מחזיר dict עם kind ו-depth, או None."""
    ln = layer_name.strip().upper()
    m = re.match(r'^([\d.]+)\s*MM\s*D\s*([\d.]+)$', ln)
    if m:
        return {'kind': 'DRILL', 'diam': float(m.group(1)), 'depth': float(m.group(2))}
    m = re.match(r'^CUT\s*([\d.]+)$', ln)
    if m:
        return {'kind': 'CUT', 'diam': float(m.group(1)), 'depth': None}
    m = re.match(r'^POCKET\s*([\d.]+)$', ln)
    if m:
        return {'kind': 'POCKET', 'diam': float(m.group(1)), 'depth': None}
    # פורמט עם עומק: POCKET 3 D5
    m = re.match(r'^POCKET\s+([\d.]+)\s+D\s*([\d.]+)$', ln)
    if m:
        return {'kind': 'POCKET', 'diam': float(m.group(1)), 'depth': float(m.group(2))}
    return None

def find_tool_by_dxf_name(layer_name, tool_db):
    """מחפש כלי בטבלה לפי DXF_Name. מחזיר (row, is_missing)."""
    if not isinstance(tool_db, pd.DataFrame):
        tool_db = pd.DataFrame(tool_db)
    if 'DXF_Name' not in tool_db.columns:
        return None, True
    ln = layer_name.strip().upper()
    for _, row in tool_db.iterrows():
        dxf_n = str(row.get('DXF_Name', '')).strip().upper()
        if dxf_n and dxf_n == ln:
            return row, (row['T_CNC'] == 'MISSING')
    return None, True

def dxf_shapes_to_ops(layer_name, shapes, tool_db, rotate, wp_w, wp_l, thick, off_x, off_y):
    """ממיר רשימת צורות של שכבה לרשימת ops (פורמט MPR)."""
    identified = identify_dxf_layer(layer_name)
    tool_row, is_missing = find_tool_by_dxf_name(layer_name, tool_db)
    tdb = tool_db if isinstance(tool_db, pd.DataFrame) else pd.DataFrame(tool_db)

    # חיפוש כלי לפי קוטר — רק אם לא נמצא לפי DXF_Name
    if tool_row is None and identified:
        diam_id = identified['diam']
        if identified['kind'] == 'DRILL':
            # קידוח: חפש רק כלים שה-MPR_Name שלהם הוא מספר עשרוני (מקדחים)
            drill_mask = tdb['MPR_Name'].apply(lambda v: '.' in str(v) and str(v).replace('.','').isdigit())
            match = tdb[drill_mask & (abs(tdb['קוטר'] - diam_id) < 0.1)]
        else:
            # כרסום/פוקט: חפש לפי קוטר בין כלים עם DXF_Name שמתחיל ב-CUT
            cut_mask = tdb['DXF_Name'].astype(str).str.upper().str.startswith('CUT')
            match = tdb[cut_mask & (abs(tdb['קוטר'] - diam_id) < 0.1)]
            if match.empty:
                match = tdb[abs(tdb['קוטר'] - diam_id) < 0.1]
        if not match.empty:
            tool_row = match.iloc[0]
            is_missing = (tool_row['T_CNC'] == 'MISSING')

    if tool_row is None:
        tool_row = pd.Series({"T_CNC": "MISSING", "תיאור": f"שכבה: {layer_name}",
                               "קוטר": 6.0, "Z_Offset": 0.0, "RPM": 12000, "Feed": 2000})
        is_missing = True

    kind  = identified['kind'] if identified else 'CUT'
    diam  = float(tool_row['קוטר'])
    rad   = diam / 2
    depth = identified['depth'] if (identified and identified['depth']) else thick / 2
    z_abs = round(thick - depth, 3)

    def to_nc(x, y):
        # נרמול לאפס הפלטה
        nx, ny = x - off_x, y - off_y
        if rotate:
            return [wp_w - ny, nx]
        return [nx, ny]

    ops = []
    for pts in shapes:
        if not pts: continue
        nc_pts = [to_nc(p[0], p[1]) for p in pts]

        if kind == 'DRILL':
            # קידוח — מרכז הצורה
            xs = [p[0] for p in nc_pts]
            ys = [p[1] for p in nc_pts]
            cx = (max(xs) + min(xs)) / 2
            cy = (max(ys) + min(ys)) / 2
            # חיפוש כלי לפי קוטר האמיתי של הצורה — רק בין מקדחים
            actual_diam = round((max(xs) - min(xs) + max(ys) - min(ys)) / 2, 1)
            drill_mask = tdb['MPR_Name'].apply(lambda v: '.' in str(v) and str(v).replace('.','').isdigit())
            match = tdb[drill_mask & (abs(tdb['קוטר'] - actual_diam) < 0.5)]
            if not match.empty:
                t_row = match.iloc[0]
                is_miss = (t_row['T_CNC'] == 'MISSING')
            else:
                t_row = tool_row; is_miss = is_missing
            ops.append({
                't_cnc': t_row['T_CNC'], 'desc': t_row['תיאור'],
                'z': z_abs, 'ti': depth, 'z_off': float(t_row['Z_Offset']),
                'pts': [[cx, cy]], 'rad': float(t_row['קוטר'])/2,
                'diam': float(t_row['קוטר']),
                'f': float(t_row['Feed']), 's': float(t_row['RPM']),
                'type': '102', 'ea': f"DXF_DRILL_{round(cx,1)}_{round(cy,1)}",
                'rk': 'WRKL', 'is_pocket': False, 'missing': is_miss
            })
        else:
            # קונטור / פוקט — סגירה אוטומטית
            if nc_pts[0] != nc_pts[-1]:
                nc_pts.append(nc_pts[0])
            is_pock = (kind == 'POCKET')
            ops.append({
                't_cnc': tool_row['T_CNC'], 'desc': tool_row['תיאור'],
                'z': z_abs, 'ti': depth, 'z_off': float(tool_row['Z_Offset']),
                'pts': nc_pts, 'rad': rad, 'diam': diam,
                'f': float(tool_row['Feed']), 's': float(tool_row['RPM']),
                'type': '181' if is_pock else '105',
                'ea': f"DXF_{layer_name}_{round(nc_pts[0][0],1)}",
                'rk': 'WRKR', 'is_pocket': is_pock, 'missing': is_missing
            })
    return ops


def _block_wh(v_block):
    """מחזיר (min_dim, max_dim) — מעדיף orig_w/orig_h (לפני סיבוב) לדיוק מקסימלי.
    מנרמל ל-1dp כדי לוודא זיהוי זהה גם עם הפרשים זעירים בנקודה צפה."""
    try:
        ow = v_block.get('orig_w')
        oh = v_block.get('orig_h')
        if ow is not None and oh is not None and (ow > 0 or oh > 0):
            return tuple(sorted([round(ow, 1), round(oh, 1)]))
        pts = v_block['paths'][0]['pts']
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        w = round(max(xs)-min(xs), 1)
        h = round(max(ys)-min(ys), 1)
        return tuple(sorted([w, h]))
    except:
        return (0, 0)

def _geo_analytical_bbox(geo_text):
    """מחשב bbox אנליטי של גיאומטריה במרחב MPR (לפני סיבוב).
    לקשתות: בודק זוויות קרדינליות (0/90/180/270°) לדיוק מקסימלי.
    DS נשמר בכל node בזמן הפרסור כדי להימנע מטעות off-by-one בין nodes לelements."""
    elements = re.split(r'\$E\d+', geo_text)
    nodes = []
    for el in elements:
        xm = re.search(r'X=([\d.\-]+)', el)
        ym = re.search(r'Y=([\d.\-]+)', el)
        if not xm or not ym:
            continue
        r_m = re.search(r'R=([\d.\-]+)', el)
        ds_m = re.search(r'DS=(\d+)', el)
        nodes.append({
            'x': float(xm.group(1)), 'y': float(ym.group(1)),
            'kind': 'KA' if 'KA' in el else 'KL',
            'r': _safe_float(r_m.group(1)) if r_m else 0.0,
            'ds': int(ds_m.group(1)) if ds_m else 1
        })
    if not nodes:
        return 0, 0
    all_pts = [[nodes[0]['x'], nodes[0]['y']]]
    for i in range(1, len(nodes)):
        cur, prev = nodes[i], nodes[i-1]
        all_pts.append([cur['x'], cur['y']])
        if cur['kind'] == 'KA' and cur['r'] > 0:
            x1, y1, x2, y2, r = prev['x'], prev['y'], cur['x'], cur['y'], cur['r']
            dx, dy = x2 - x1, y2 - y1
            d = math.sqrt(dx*dx + dy*dy)
            if d < 1e-6:
                continue
            r = round(r, 1)   # normalize e.g. R=8.5002 → 8.5 for exact bbox
            h_d_sq = r*r - (d/2)**2
            if h_d_sq < -1e-6:  # r genuinely too small for this chord
                continue
            h_d = math.sqrt(max(0.0, h_d_sq))
            ds = cur['ds']
            cx = (x1+x2)/2 + h_d*(-dy/d)
            cy = (y1+y2)/2 + h_d*(dx/d)
            a1 = math.atan2(y1-cy, x1-cx)
            a2 = math.atan2(y2-cy, x2-cx)
            if ds == 3:
                if a2 < a1: a2 += 2*math.pi
            else:
                if a2 > a1: a2 -= 2*math.pi
            for ac_base, ex, ey in [(0, cx+r, cy), (math.pi/2, cx, cy+r),
                                     (math.pi, cx-r, cy), (3*math.pi/2, cx, cy-r)]:
                for k in range(-2, 3):
                    ac = ac_base + k*2*math.pi
                    if (a2 <= a1 and a2 <= ac <= a1) or (a2 > a1 and a1 <= ac <= a2):
                        all_pts.append([ex, ey]); break
    xs = [p[0] for p in all_pts]; ys = [p[1] for p in all_pts]
    return round(max(xs)-min(xs), 2), round(max(ys)-min(ys), 2)

def get_f(key, block, default=0.0):
    m = re.search(f'{key}="?([^"\\s]+)"?', block)
    return _safe_float(m.group(1)) if m else default

def parse_geo_with_arcs(geo_text, rotate, wp_w, n_arc_pts=128):
    """פרסור גאומטריה עם תמיכה ב-KL (קו ישר) וב-KA (קשת).
    מחזיר רשימת נקודות שמייצגות את הנתיב כולל קירוב קשתות לנקודות."""
    elements = re.split(r'\$E\d+', geo_text)
    nodes = []
    for el in elements:
        xm = re.search(r'X=([\d.\-]+)', el)
        ym = re.search(r'Y=([\d.\-]+)', el)
        if not xm or not ym:
            continue
        x_raw = float(xm.group(1))
        y_raw = float(ym.group(1))
        kind = 'KA' if 'KA' in el else 'KL'
        r_val = _safe_float(re.search(r'R=([\d.\-]+)', el).group(1)) if re.search(r'R=([\d.\-]+)', el) else 0.0
        nodes.append({'x': x_raw, 'y': y_raw, 'kind': kind, 'r': r_val})

    if not nodes:
        return []

    def to_nc(x_raw, y_raw):
        if rotate:
            return [wp_w - y_raw, x_raw]
        return [x_raw, y_raw]

    pts = [to_nc(nodes[0]['x'], nodes[0]['y'])]

    for i in range(1, len(nodes)):
        cur = nodes[i]
        prev = nodes[i-1]
        if cur['kind'] == 'KA' and cur['r'] > 0:
            # חישוב מרכז הקשת: המרכז נמצא במרחק R מ-prev וגם מ-cur
            x1, y1 = prev['x'], prev['y']
            x2, y2 = cur['x'], cur['y']
            r = round(cur['r'], 1)   # normalize R=8.5002 → 8.5
            # מרכז הקשת: אמצע הקורד + פרפנדיקולר
            mx_mid = (x1 + x2) / 2
            my_mid = (y1 + y2) / 2
            dx = x2 - x1
            dy = y2 - y1
            d = math.sqrt(dx*dx + dy*dy)
            if d < 1e-6 or r < d/2:
                pts.append(to_nc(x2, y2))
                continue
            h = math.sqrt(r*r - (d/2)**2)
            # שני מרכזים אפשריים - DS=3 מציין כיוון
            ds_match = re.search(r'DS=(\d+)', list(re.split(r'\$E\d+', geo_text))[i] if i < len(re.split(r'\$E\d+', geo_text)) else '')
            ds = int(ds_match.group(1)) if ds_match else 1
            # DS=3 = ימין, DS=1 = שמאל (ביחס לכיוון התנועה)
            perp_x = -dy / d
            perp_y = dx / d
            if ds == 3:
                # DS=3: מרכז ימינה ביחס לכיוון התנועה
                cx = mx_mid + h * perp_x
                cy = my_mid + h * perp_y
            else:
                # DS=1: מרכז שמאלה ביחס לכיוון התנועה (הצד הנגדי)
                cx = mx_mid - h * perp_x
                cy = my_mid - h * perp_y
            # זוויות התחלה וסיום
            a1 = math.atan2(y1 - cy, x1 - cx)
            a2 = math.atan2(y2 - cy, x2 - cx)
            # כיוון הקשת לפי DS
            if ds == 3:
                if a2 > a1:
                    a2 -= 2 * math.pi
            else:
                if a2 < a1:
                    a2 += 2 * math.pi
            for j in range(1, n_arc_pts + 1):
                t = j / n_arc_pts
                angle = a1 + t * (a2 - a1)
                ax = cx + r * math.cos(angle)
                ay = cy + r * math.sin(angle)
                pts.append(to_nc(ax, ay))
        else:
            pts.append(to_nc(cur['x'], cur['y']))

    return pts

# ============================================================
# CIX — פונקציות ייצוא לפורמט SCM/Biesse Maestro
# ============================================================

def get_cix_entities(geo_text, rotate, wp_w, global_off_x, global_off_y):
    """ממיר גיאומטריית MPR גולמית לרשימת ישויות CIX (START/LINE/ARC).
    שומר קשתות כ-ARC_EPCE אמיתי במקום 128 קווים — DS מטפל בצד המרכז ובכיוון."""
    if not geo_text:
        return []
    elements = re.split(r'\$E\d+', geo_text)
    nodes = []
    for el in elements:
        xm = re.search(r'X=([\d.\-]+)', el)
        ym = re.search(r'Y=([\d.\-]+)', el)
        if not xm or not ym:
            continue
        kind = 'KA' if 'KA' in el else 'KL'
        r_val = _safe_float(re.search(r'R=([\d.\-]+)', el).group(1)) if re.search(r'R=([\d.\-]+)', el) else 0.0
        ds_m = re.search(r'DS=(\d+)', el)
        ds = int(ds_m.group(1)) if ds_m else 1
        nodes.append({'x': float(xm.group(1)), 'y': float(ym.group(1)), 'kind': kind, 'r': r_val, 'ds': ds})
    if not nodes:
        return []

    def to_nc(x_raw, y_raw):
        if rotate:
            return [wp_w - y_raw + global_off_x, x_raw + global_off_y]
        return [x_raw + global_off_x, y_raw + global_off_y]

    sp = to_nc(nodes[0]['x'], nodes[0]['y'])
    entities = [{'type': 'START', 'x': sp[0], 'y': sp[1]}]

    for i in range(1, len(nodes)):
        cur = nodes[i]
        prev = nodes[i-1]
        p_end = to_nc(cur['x'], cur['y'])

        if cur['kind'] == 'KA' and cur['r'] > 0:
            x1, y1 = prev['x'], prev['y']
            x2, y2 = cur['x'], cur['y']
            r = round(cur['r'], 1)
            dx = x2 - x1; dy = y2 - y1
            d = math.sqrt(dx*dx + dy*dy)
            if d < 1e-6 or r < d/2:
                entities.append({'type': 'LINE', 'x': p_end[0], 'y': p_end[1]})
                continue
            h = math.sqrt(r*r - (d/2)**2)
            perp_x = -dy / d; perp_y = dx / d
            mx = (x1 + x2) / 2; my = (y1 + y2) / 2
            if cur['ds'] == 3:
                # DS=3: מרכז ימינה, כיוון CW
                cx = mx + h * perp_x; cy = my + h * perp_y
                cix_dir = 'dirCW'
            else:
                # DS=1: מרכז שמאלה, כיוון CCW
                cx = mx - h * perp_x; cy = my - h * perp_y
                cix_dir = 'dirCCW'
            c_nc = to_nc(cx, cy)
            entities.append({'type': 'ARC', 'x': p_end[0], 'y': p_end[1],
                             'cx': c_nc[0], 'cy': c_nc[1], 'dir': cix_dir})
        else:
            entities.append({'type': 'LINE', 'x': p_end[0], 'y': p_end[1]})

    return entities


def generate_cix_output(order, block_configs, wp_l, wp_w, thick, geo_texts, rotate):
    """מייצר קובץ CIX מלא לפורמט SCM/Biesse Maestro 5.0.
    dp_val = thick - z_val (עומק נקי מפני הפלטה, ללא gz/z_off שהם תיקוני NC בלבד)."""
    cix = ["BEGIN ID CIX\n\tREL= 5.0\nEND ID\n"]
    cix.append(f"BEGIN MAINDATA\n\tLPX={wp_l}\n\tLPY={wp_w}\n\tLPZ={thick}\n\tORLST=\"0\"\nEND MAINDATA\n")
    cid = 1000

    for b_id in order:
        b_cfg = block_configs[b_id]
        v_block = b_cfg['v_block']
        it = v_block['paths'][0]
        t_name = v_block['t_cnc']
        eff_rk = b_cfg.get('rk_override', it.get('rk', 'WRKL'))
        crc_val = 1 if eff_rk == 'WRKL' else (2 if eff_rk == 'WRKR' else 0)

        for p_idx, z_val in enumerate(b_cfg['passes']):
            # DP = עומק מפני הפלטה — ללא z_off/gz שהם תיקוני NC בלבד
            dp_val = round(thick - z_val, 3)

            if v_block['is_dr']:
                for drill_op in v_block['paths']:
                    pt = drill_op['pts'][0]
                    cid += 1
                    cix.append(
                        f"BEGIN MACRO\n\tNAME=BV\n"
                        f"\tPARAM,NAME=SIDE,VALUE=0\n"
                        f"\tPARAM,NAME=CRN,VALUE=\"1\"\n"
                        f"\tPARAM,NAME=X,VALUE={pt[0]+st.session_state.off_x:.2f}\n"
                        f"\tPARAM,NAME=Y,VALUE={pt[1]+st.session_state.off_y:.2f}\n"
                        f"\tPARAM,NAME=Z,VALUE=0\n"
                        f"\tPARAM,NAME=DP,VALUE={dp_val}\n"
                        f"\tPARAM,NAME=DIA,VALUE={it['diam']}\n"
                        f"\tPARAM,NAME=ID,VALUE=\"P{cid}\"\n"
                        f"\tPARAM,NAME=LAY,VALUE=\"BG\"\n"
                        f"\tPARAM,NAME=TTP,VALUE={1 if dp_val >= thick - 0.2 else 0}\n"
                        f"\tPARAM,NAME=OPT,VALUE=1\n"
                        f"END MACRO\n"
                    )
            else:
                cid += 1
                cix.append(
                    f"BEGIN MACRO\n\tNAME=ROUT\n"
                    f"\tPARAM,NAME=ID,VALUE=\"P{cid}\"\n"
                    f"\tPARAM,NAME=SIDE,VALUE=0\n"
                    f"\tPARAM,NAME=CRN,VALUE=\"1\"\n"
                    f"\tPARAM,NAME=DP,VALUE={dp_val}\n"
                    f"\tPARAM,NAME=DIA,VALUE={it['diam']}\n"
                    f"\tPARAM,NAME=WSP,VALUE={int(it.get('s', 12000))}\n"
                    f"\tPARAM,NAME=SHP,VALUE=0\n"
                    f"\tPARAM,NAME=CRC,VALUE={crc_val}\n"
                    f"\tPARAM,NAME=TNM,VALUE=\"{t_name}\"\n"
                    f"\tPARAM,NAME=TTP,VALUE=100\n"
                    f"\tPARAM,NAME=THR,VALUE=NO\n"
                    f"END MACRO\n"
                )
                ea_id = it.get('ea', '')
                raw_geo = geo_texts.get(ea_id, '')
                entities = get_cix_entities(raw_geo, rotate, wp_w,
                                            st.session_state.off_x, st.session_state.off_y)
                if not entities:
                    # fallback: נקודות מחושבות (ללא קשתות)
                    pts = it['pts']
                    entities = [{'type': 'START',
                                 'x': pts[0][0] + st.session_state.off_x,
                                 'y': pts[0][1] + st.session_state.off_y}]
                    for p in pts[1:]:
                        entities.append({'type': 'LINE',
                                         'x': p[0] + st.session_state.off_x,
                                         'y': p[1] + st.session_state.off_y})
                for ent in entities:
                    cid += 1
                    if ent['type'] == 'START':
                        cix.append(
                            f"BEGIN MACRO\n\tNAME=START_POINT\n"
                            f"\tPARAM,NAME=ID,VALUE=\"{cid}\"\n"
                            f"\tPARAM,NAME=X,VALUE={ent['x']:.2f}\n"
                            f"\tPARAM,NAME=Y,VALUE={ent['y']:.2f}\n"
                            f"\tPARAM,NAME=Z,VALUE=0\n"
                            f"END MACRO\n"
                        )
                    elif ent['type'] == 'LINE':
                        cix.append(
                            f"BEGIN MACRO\n\tNAME=LINE_EP\n"
                            f"\tPARAM,NAME=ID,VALUE=\"P{cid}\"\n"
                            f"\tPARAM,NAME=XE,VALUE={ent['x']:.2f}\n"
                            f"\tPARAM,NAME=YE,VALUE={ent['y']:.2f}\n"
                            f"\tPARAM,NAME=ZS,VALUE=0\n"
                            f"\tPARAM,NAME=ZE,VALUE=0\n"
                            f"END MACRO\n"
                        )
                    elif ent['type'] == 'ARC':
                        cix.append(
                            f"BEGIN MACRO\n\tNAME=ARC_EPCE\n"
                            f"\tPARAM,NAME=ID,VALUE={cid}\n"
                            f"\tPARAM,NAME=XE,VALUE={ent['x']:.2f}\n"
                            f"\tPARAM,NAME=YE,VALUE={ent['y']:.2f}\n"
                            f"\tPARAM,NAME=XC,VALUE={ent['cx']:.2f}\n"
                            f"\tPARAM,NAME=YC,VALUE={ent['cy']:.2f}\n"
                            f"\tPARAM,NAME=ZS,VALUE=0\n"
                            f"\tPARAM,NAME=ZE,VALUE=0\n"
                            f"\tPARAM,NAME=DIR,VALUE={ent['dir']}\n"
                            f"END MACRO\n"
                        )
                cid += 1
                cix.append(f"BEGIN MACRO\n\tNAME=ENDPATH\n\tPARAM,NAME=ID,VALUE=\"{cid}\"\nEND MACRO\n")

    return "".join(cix)



st.title("🏭 דרוויש 56.1 - MPR + DXF + CIX")

# הגדרות גלובליות בשורה אחת
col_g1, col_g2, col_g3, col_g4 = st.columns([1, 1, 1, 2])
with col_g1:
    rotate = st.checkbox("סובב חלק 90 מעלות (CCW)", value=True)
with col_g2:
    flip_180 = st.checkbox("סובב פלטה 180°", value=False)
with col_g3:
    ramp_len_global = st.slider("אורך נחיתה (Ramp)", 0, 50, 20)
    st.session_state.ramp_len_global = ramp_len_global
with col_g4:
    upl_col_mpr, upl_col_dxf = st.columns(2)
    with upl_col_mpr:
        upl = st.file_uploader("טען קבצי MPR", accept_multiple_files=True, type=['mpr'])
    with upl_col_dxf:
        upl_dxf = st.file_uploader("טען קבצי DXF", accept_multiple_files=True, type=['dxf'])

# --- שקלול קאנטים (Edge Banding) ---
col_eb1, col_eb2, col_eb3 = st.columns([1, 1, 4])
with col_eb1:
    eb_active = st.checkbox("🪵 שקלול קאנטים", value=st.session_state.get('eb_active', False), key='eb_active_cb')
    st.session_state.eb_active = eb_active
with col_eb2:
    eb_thickness = st.number_input("עובי קאנט (מ\"מ)", value=st.session_state.get('eb_thickness', 1.0),
                                   min_value=0.0, max_value=5.0, step=0.1, key='eb_thick_inp',
                                   disabled=not eb_active)
    st.session_state.eb_thickness = eb_thickness
with col_eb3:
    if eb_active:
        st.info(f"✂️ קאנט פעיל: {eb_thickness} מ\"מ — כל ניתוקי החלקים יוקטנו ב-{eb_thickness} מ\"מ מכל צד")

def write_block_at_depth(b_cfg, v_block, zv_final, it, nc, n_c, last_tool_id):
    if v_block['t_cnc'] != last_tool_id:
        if last_tool_id is not None:
            nc.append(f"N{n_c} M05"); n_c += 5
        nc.extend([f"N{n_c} {v_block['t_cnc']} M06", f"N{n_c+5} G43 H{v_block['t_cnc'][1:] if v_block['t_cnc'] != 'MISSING' else '101'}", f"N{n_c+10} S{int(v_block['s'])} M03"]); n_c += 15
        last_tool_id = v_block['t_cnc']
    if v_block['is_dr']:
        for drill_op in v_block['paths']:
            pt = drill_op['pts'][0]
            nc.append(f"N{n_c} G00 X{pt[0]+st.session_state.off_x:.3f} Y{pt[1]+st.session_state.off_y:.3f} Z{st.session_state.safety_h:.3f}"); n_c += 5
            nc.append(f"N{n_c} G01 Z{zv_final:.3f} F{int(it['f'])}"); n_c += 5
            nc.append(f"N{n_c} G00 Z{st.session_state.safety_h:.3f}"); n_c += 5
    else:
        eff_rk = b_cfg.get('rk_override', it['rk'])
        path = calculate_path_v518(it['pts'], it['rad'], eff_rk, it['is_pocket'])
        for pi, p in enumerate(path):
            if pi == 0:
                if (it['is_pocket'] or len(path) < 2 or st.session_state.get('ramp_len_global', 20) == 0):
                    nc.append(f"N{n_c} G00 X{p[0]+st.session_state.off_x:.3f} Y{p[1]+st.session_state.off_y:.3f} Z{st.session_state.safety_h:.3f}"); n_c += 5
                    nc.append(f"N{n_c} G01 Z{zv_final:.3f} F1500"); n_c += 5
                else:
                    ramp = st.session_state.get('ramp_len_global', 20)
                    p0, p1 = np.array(path[0]), np.array(path[1])
                    vec = p1 - p0; mag = np.linalg.norm(vec)
                    if mag > 0:
                        unit_v = vec / mag; r_start = p0 - (unit_v * ramp)
                        nc.append(f"N{n_c} G00 X{r_start[0]+st.session_state.off_x:.3f} Y{r_start[1]+st.session_state.off_y:.3f} Z{st.session_state.safety_h:.3f}"); n_c += 5
                        nc.append(f"N{n_c} G01 X{p[0]+st.session_state.off_x:.3f} Y{p[1]+st.session_state.off_y:.3f} Z{zv_final:.3f} F1500"); n_c += 5
                    else:
                        nc.append(f"N{n_c} G00 X{p[0]+st.session_state.off_x:.3f} Y{p[1]+st.session_state.off_y:.3f} Z{st.session_state.safety_h:.3f}"); n_c += 5
                        nc.append(f"N{n_c} G01 Z{zv_final:.3f} F1500"); n_c += 5
            else:
                nc.append(f"N{n_c} G01 X{p[0]+st.session_state.off_x:.3f} Y{p[1]+st.session_state.off_y:.3f} F{int(it['f'])}"); n_c += 5
        nc.append(f"N{n_c} G00 Z{st.session_state.safety_h:.3f}"); n_c += 5
    return nc, n_c, last_tool_id

# טבלת כלים פעילה
tool_db = st.session_state.machine_profiles[st.session_state.get('active_machine', 'אבי')]

# שמירת נתוני הדמיה לכל קובץ
if 'fig_data' not in st.session_state:
    st.session_state.fig_data = {}
if 'file_info' not in st.session_state:
    st.session_state.file_info = {}

# לשוניות לכל קובץ MPR
if upl:
    tab_names = [f.name for f in upl]
    tabs = st.tabs(tab_names)
else:
    tabs = []

if upl:
    for tab_idx, (f_file, tab) in enumerate(zip(upl, tabs)):
      with tab:
        col_cfg, col_vis = st.columns([1, 2])
        mpr = f_file.getvalue().decode('utf-8', errors='ignore')
        wp_match = re.search(r'\[001(.*?)\]', mpr, re.DOTALL); wp_block = wp_match.group(1) if wp_match else ""
        wp_l, wp_w = get_f('l', wp_block, 2440.0), get_f('w', wp_block, 1220.0); thick = get_f('t', mpr, 19.0)

        geos = {}
        parts = re.split(r'\](\d+)', mpr)
        for i in range(1, len(parts), 2):
            pts = parse_geo_with_arcs(parts[i+1], rotate, wp_w)
            if pts: geos[parts[i]] = pts

        geo_texts = {}
        for i in range(1, len(parts), 2):
            geo_texts[parts[i]] = parts[i+1]

        ops = []
        for m in re.finditer(r'<(102|105|112|130|181)(.*?)(?=<|\!|\[H)', mpr, re.DOTALL):
            tag, bc = m.group(1), m.group(2)
            t_mpr = re.search(r'(?:TNO|T_|DU)="?([^"\\s]+)"?', bc).group(1).strip() if re.search(r'(?:TNO|T_|DU)="?([^"\\s]+)"?', bc) else "142"
            t_info, is_missing = find_tool_numeric(t_mpr, tool_db)
            ti_val = get_f('TI', bc); z_abs = round((thick - ti_val), 3) if tag in ['102', '181', '112'] else round(get_f('ZA', bc), 3)

            if tag == '102':
                xa, ya, an, ab, xr, yr = get_f('XA', bc), get_f('YA', bc), int(get_f('AN', bc, 1)), get_f('AB', bc, 0.0), get_f('XR', bc, 1.0), get_f('YR', bc, 0.0)
                for i in range(an):
                    curr_xa, curr_ya = xa + (i*ab*xr), ya + (i*ab*yr)
                    ops.append({'t_cnc': t_info['T_CNC'], 'desc': t_info['תיאור'], 'z': z_abs, 'ti': ti_val, 'z_off': t_info['Z_Offset'], 'pts': [[wp_w - curr_ya, curr_xa]] if rotate else [[curr_xa, curr_ya]], 'rad': t_info['קוטר']/2, 'diam': t_info['קוטר'], 'f': t_info['Feed'], 's': t_info['RPM'], 'type': tag, 'ea': f"DRILL_{round(curr_xa,1)}", 'rk': "WRKL", 'is_pocket': False, 'missing': is_missing, 'orig_w': 0, 'orig_h': 0})
            elif tag == '112':
                xa, ya, la, br, wi = get_f('XA', bc), get_f('YA', bc), get_f('LA', bc), get_f('BR', bc), get_f('WI', bc)
                rect_local = [(-la/2, -br/2), (la/2, -br/2), (la/2, br/2), (-la/2, br/2), (-la/2, -br/2)]
                f_pts = [[wp_w - (rotate_pt_v518(px, py, wi)[1] + ya), rotate_pt_v518(px, py, wi)[0] + xa] if rotate else [rotate_pt_v518(px, py, wi)[0] + xa, rotate_pt_v518(px, py, wi)[1] + ya] for px, py in rect_local]
                ops.append({'t_cnc': t_info['T_CNC'], 'desc': t_info['תיאור'], 'z': z_abs, 'ti': ti_val, 'z_off': t_info['Z_Offset'], 'pts': f_pts, 'rad': t_info['קוטר']/2, 'diam': t_info['קוטר'], 'f': t_info['Feed'], 's': t_info['RPM'], 'type': tag, 'ea': "TASCHE", 'rk': "WRKL", 'is_pocket': True, 'missing': is_missing, 'orig_w': round(la, 2), 'orig_h': round(br, 2)})
            else:
                geoid = re.search(r'EA="?(\d+):?', bc).group(1).strip() if re.search(r'EA="?(\d+):?', bc) else "FREE"
                f_pts = geos.get(geoid) if geos.get(geoid) else [[wp_w - get_f('YA', bc), get_f('XA', bc)] if rotate else [get_f('XA', bc), get_f('YA', bc)]]
                _geo_txt = geo_texts.get(geoid, '')
                if _geo_txt:
                    _orig_w, _orig_h = _geo_analytical_bbox(_geo_txt)
                else:
                    _orig_w = 0; _orig_h = 0
                ops.append({'t_cnc': t_info['T_CNC'], 'desc': t_info['תיאור'], 'z': z_abs, 'ti': thick-z_abs, 'z_off': t_info['Z_Offset'], 'pts': f_pts, 'rad': t_info['קוטר']/2, 'diam': t_info['קוטר'], 'f': t_info['Feed'], 's': t_info['RPM'], 'type': tag, 'ea': geoid, 'rk': re.search(r'RK="([^"]*)"', bc).group(1) if re.search(r'RK="([^"]*)"', bc) else "WRKL", 'is_pocket': (tag == '181'), 'missing': is_missing, 'orig_w': _orig_w, 'orig_h': _orig_h})

        if flip_180:
            nc_bx = wp_w if rotate else wp_l
            nc_by = wp_l if rotate else wp_w
            for op in ops:
                op['pts'] = [[nc_bx - p[0], nc_by - p[1]] for p in op['pts']]

        visual_blocks = {}
        for op in ops:
            v_key = (op['t_cnc'], op['type'], tuple(tuple(p) for p in op['pts'])) if op['type'] != '102' else (op['t_cnc'], op['type'])
            if v_key not in visual_blocks: visual_blocks[v_key] = {'t_cnc': op['t_cnc'], 'desc': op['desc'], 'type': op['type'], 'is_dr': op['type'] == '102', 'paths': [], 's': op['s'], 'f': op['f'], 'diam': op['diam'], 'ea_id': op['ea'], 'missing': is_missing, 'orig_w': op.get('orig_w', 0), 'orig_h': op.get('orig_h', 0)}
            visual_blocks[v_key]['paths'].append(op)

        for vk in visual_blocks:
            if visual_blocks[vk]['is_dr']: visual_blocks[vk]['paths'] = optimize_drill_path_v518(visual_blocks[vk]['paths'])

        # --- קיבוץ אוטומטי של כלים (Tool Grouping) ---
        # שלב 1: חישוב אם כל בלוק הוא ניתוק (sep) או לא
        blocks_list = []
        for v_key, v_block in visual_blocks.items():
            z_vals = sorted(list(set(p['z'] for p in v_block['paths'])), reverse=True)
            is_sep = any(z <= 0.2 for z in z_vals)
            blocks_list.append((v_key, v_block, z_vals, is_sep))

        # שלב 2: קיבוץ - כלים לא-ניתוק לפי כלי, ניתוק בסוף
        tool_groups = {}  # כלי -> רשימת בלוקים לא-ניתוק לפי סדר הופעה
        sep_blocks = []   # בלוקי ניתוק
        for item in blocks_list:
            v_key, v_block, z_vals, is_sep = item
            t = v_block['t_cnc']
            if is_sep:
                sep_blocks.append(item)
            else:
                if t not in tool_groups: tool_groups[t] = []
                tool_groups[t].append(item)

        # שלב 3: בניית הסדר הסופי - כלים מקובצים + ניתוק בסוף
        ordered_blocks = []
        seen_tools = []
        for item in blocks_list:
            t = item[1]['t_cnc']
            if not item[3] and t not in seen_tools:  # לא ניתוק ולא נראה עדיין
                seen_tools.append(t)
                ordered_blocks.extend(tool_groups[t])
        ordered_blocks.extend(sep_blocks)

        # שלב 4: חישוב def_idx לפי הסדר החדש
        def_idx_map = {}
        sep_counter = 1000
        reg_counter = 10
        for item in ordered_blocks:
            v_key = item[0]
            is_sep = item[3]
            if is_sep:
                def_idx_map[v_key] = sep_counter
                sep_counter += 10
            else:
                def_idx_map[v_key] = reg_counter
                reg_counter += 10

        # שמירת מידע על הפלטה
        st.session_state.file_info[f_file.name] = {
            'l': wp_l, 'w': wp_w, 't': thick,
            'n_parts': len([k for k in geos if k != '1'])
        }

        # מיפוי מוקדם של חלקי ניתוך לפי סדר — לשימוש בשקלול קאנטים
        sep_v_key_to_part_idx = {}
        _sep_ctr = 0
        for item in ordered_blocks:
            if item[3]:  # is_sep
                sep_v_key_to_part_idx[item[0]] = _sep_ctr
                _sep_ctr += 1

        # אתחול ברירת מחדל
        block_configs = []
        order = []

        with col_cfg:
            info = st.session_state.file_info[f_file.name]
            st.info(f"📐 {info['l']} × {info['w']} מילימטר | עובי: {info['t']} מילימטר | חלקים: {info['n_parts']}")

            with st.container(height=550):
                with st.expander(f"📦 ניהול בלוקים: {f_file.name}", expanded=False):
                        block_configs = []
                        all_blocks_raw = []
                        for i, (v_key, v_block) in enumerate(visual_blocks.items()):
                            z_vals = sorted(list(set(p['z'] for p in v_block['paths'])), reverse=True)
                            pass_key = f"passes_{i}_{f_file.name}"
                            if pass_key not in st.session_state:
                                st.session_state[pass_key] = [float(z) for z in z_vals]
                            def_idx = def_idx_map.get(v_key, 500 + i*10)
                            is_sep_val = any(z <= 0.2 for z in st.session_state.get(pass_key, z_vals))
                            active_key = f"active_{i}_{f_file.name}"
                            if active_key not in st.session_state:
                                st.session_state[active_key] = not v_block['missing']
                            current_idx = st.session_state.get(f"idx_{i}_{f_file.name}", def_idx)
                            all_blocks_raw.append((i, v_key, v_block, z_vals, is_sep_val, def_idx, pass_key, current_idx))

                        all_blocks_sorted = sorted(all_blocks_raw, key=lambda x: x[7])

                        for i, v_key, v_block, z_vals, is_sep_val, def_idx, pass_key, current_idx in all_blocks_sorted:
                            current_passes_for_icon = st.session_state.get(pass_key, z_vals)
                            is_sep_val = any(z <= 0.2 for z in current_passes_for_icon)
                            z_str = " → ".join([str(z) for z in current_passes_for_icon])
                            sep_icon = "🔴" if is_sep_val else "🔵"
                            missing_icon = "❌ " if v_block['missing'] else ""
                            expander_label = f"[{current_idx}] {sep_icon} {missing_icon}{v_block['t_cnc']} | {v_block['desc']} | {z_str}"
                            with st.expander(expander_label, expanded=False):
                                active = st.checkbox("כלול בייצור", value=st.session_state[f"active_{i}_{f_file.name}"], key=f"act_{i}_{f_file.name}")
                                st.session_state[f"active_{i}_{f_file.name}"] = active
                                order_idx = st.number_input("סדר ביצוע", value=def_idx, key=f"idx_{i}_{f_file.name}")
                                if not v_block['is_dr']:
                                    rk_key = f"rk_{i}_{f_file.name}"
                                    default_rk = v_block['paths'][0]['rk'] if v_block['paths'] else 'WRKR'
                                    rk_map = {'WRKR': 'R — ימין (חיצוני)', 'WRKL': 'L — שמאל (פנימי)', 'NoWRK': 'C — על הקו'}
                                    rk_opts = list(rk_map.values())
                                    rk_def = rk_map.get(default_rk, rk_opts[0])
                                    if rk_key not in st.session_state:
                                        st.session_state[rk_key] = rk_def
                                    sel_rk = st.selectbox("כיוון סכין", rk_opts, index=rk_opts.index(st.session_state[rk_key]) if st.session_state[rk_key] in rk_opts else 0, key=f"rk_sel_{i}_{f_file.name}")
                                    st.session_state[rk_key] = sel_rk
                                    rk_val = {v: k for k, v in rk_map.items()}.get(sel_rk, default_rk)
                                else:
                                    rk_val = 'WRKL'
                                current_passes = st.session_state[pass_key]
                                f_z = []
                                to_delete = None
                                for zi, z_val in enumerate(current_passes):
                                    is_cut = z_val <= 0.2
                                    col_z, col_del = st.columns([4, 1])
                                    with col_z:
                                        label = f"{'🔴 ניתוק' if is_cut else '🔵 פסיעה'} {zi+1}"
                                        new_val = st.number_input(label, value=float(z_val), key=f"z_{i}_{zi}_{f_file.name}")
                                        f_z.append(new_val)
                                    with col_del:
                                        st.write("")
                                        if st.button("✕", key=f"del_{i}_{zi}_{f_file.name}", help="מחק פסיעה"):
                                            to_delete = zi
                                if to_delete is not None:
                                    st.session_state[pass_key].pop(to_delete)
                                    st.rerun()
                                if st.button("➕ הוסף פסיעה", key=f"add_{i}_{f_file.name}"):
                                    last_z = st.session_state[pass_key][-1] if st.session_state[pass_key] else 2.0
                                    st.session_state[pass_key].append(max(0.5, last_z - 2.0) if last_z > 0.2 else 2.0)
                                    st.rerun()
                                if not v_block['is_dr']:
                                    cur_wh = _block_wh(v_block)
                                    btn_label = f"⚡ החל על כל {v_block['t_cnc']} | {cur_wh[0]}×{cur_wh[1]}"
                                    if st.button(btn_label, key=f"apply_all_{i}_{f_file.name}"):
                                        for j2, v_key2, v_block2, z_vals2, _, _, pass_key2, _ in all_blocks_sorted:
                                            if j2 != i and not v_block2['is_dr'] and _block_wh(v_block2) == cur_wh:
                                                st.session_state[pass_key2] = list(f_z)
                                                for _zi2, _z2 in enumerate(f_z):
                                                    st.session_state[f"z_{j2}_{_zi2}_{f_file.name}"] = _z2
                                                st.session_state[f"rk_{j2}_{f_file.name}"] = rk_val
                                                st.session_state[f"rk_sel_{j2}_{f_file.name}"] = sel_rk
                                        st.rerun()
                                    # כפתור שני: החל על כל ניתוקי אותו כלי (ללא קשר למידות)
                                    # כפתור 3: החל על כל בלוקי אותו כלי + WRKR
                                    if rk_val == 'WRKR' and st.button(f"⚡ החל T2 | W×H ועוד", key=f"apply_wrkr_{i}_{f_file.name}"):
                                        for j2, v_key2, v_block2, z_vals2, _, _, pass_key2, _ in all_blocks_sorted:
                                            if j2 != i and not v_block2['is_dr'] and v_block2['t_cnc'] == v_block['t_cnc']:
                                                rk2 = st.session_state.get(f"rk_{j2}_{f_file.name}", 'WRKR')
                                                if rk2 in ('WRKR', 'R — ימין (חיצוני)'):
                                                    st.session_state[pass_key2] = list(f_z)
                                                    st.session_state[f"rctr_{j2}_{f_file.name}"] = st.session_state.get(f"rctr_{j2}_{f_file.name}", 0) + 1
                                        st.rerun()
                                    cur_has_cut = any(z <= 0.2 for z in f_z)
                                    btn_label2 = f"⚡⚡ החל על כל ניתוקי {v_block['t_cnc']}"
                                    if cur_has_cut and st.button(btn_label2, key=f"apply_cuts_{i}_{f_file.name}"):
                                        for j2, v_key2, v_block2, z_vals2, _, _, pass_key2, _ in all_blocks_sorted:
                                            if j2 != i and not v_block2['is_dr'] and v_block2['t_cnc'] == v_block['t_cnc']:
                                                cur_is_cut2 = any(z <= 0.2 for z in st.session_state.get(pass_key2, z_vals2))
                                                if cur_is_cut2 and rk_val in ('WRKR', 'R — ימין (חיצוני)'):
                                                    st.session_state[pass_key2] = list(f_z)
                                                    for _zi2, _z2 in enumerate(f_z):
                                                        st.session_state[f"z_{j2}_{_zi2}_{f_file.name}"] = _z2
                                                    st.session_state[f"rk_{j2}_{f_file.name}"] = rk_val
                                                    st.session_state[f"rk_sel_{j2}_{f_file.name}"] = sel_rk
                                        st.rerun()
                                if not v_block['is_dr']:
                                    geo_off_key = f"geo_off_{i}_{f_file.name}"
                                    _col_off1, _col_off2 = st.columns([2, 1])
                                    with _col_off1:
                                        new_geo_off = st.number_input("Offset (mm)", value=st.session_state.get(geo_off_key, 0.0), step=0.1, key=f"geo_off_inp_{i}_{f_file.name}")
                                    with _col_off2:
                                        st.write("")
                                        if st.button("📐 החל על זהים", key=f"geo_off_btn_{i}_{f_file.name}"):
                                            _cur_wh = _block_wh(v_block)
                                            for j2, v_key2, v_block2, _, _, _, _, _ in all_blocks_sorted:
                                                if not v_block2['is_dr'] and _block_wh(v_block2) == _cur_wh:
                                                    st.session_state[f"geo_off_{j2}_{f_file.name}"] = new_geo_off
                                            st.rerun()
                                    st.session_state[geo_off_key] = new_geo_off
                                if f_z: st.session_state[pass_key] = f_z
                                is_sep_val = any(z <= 0.2 for z in f_z)
                                if not v_block['is_dr']:
                                    # Store original bbox before offsets (for edge banding figure)
                                    if is_sep_val:
                                        _raw_pts = v_block['paths'][0]['pts']
                                        _orig_bbox = (
                                            min(p[0] for p in _raw_pts), max(p[0] for p in _raw_pts),
                                            min(p[1] for p in _raw_pts), max(p[1] for p in _raw_pts)
                                        )
                                    else:
                                        _orig_bbox = None
                                    _geo_off = st.session_state.get(f"geo_off_{i}_{f_file.name}", 0.0)
                                    if abs(_geo_off) > 1e-9:
                                        for _path_op in v_block['paths']:
                                            _path_op['pts'] = apply_geo_offset(_path_op['pts'], _geo_off)
                                    # שקלול קאנטים — אופסט חלקי משל צלעות
                                    if is_sep_val and eb_active and eb_thickness > 1e-9:
                                        _part_idx = sep_v_key_to_part_idx.get(v_key)
                                        if _part_idx is not None:
                                            _sides = {s: st.session_state.get(f"eb_edge_{f_file.name}_{_part_idx}_{s}", True)
                                                      for s in ['top', 'bottom', 'left', 'right']}
                                            if all(_sides.values()):
                                                for _path_op in v_block['paths']:
                                                    _path_op['pts'] = apply_geo_offset(_path_op['pts'], -eb_thickness)
                                            else:
                                                for _path_op in v_block['paths']:
                                                    _path_op['pts'] = apply_partial_edge_offset(_path_op['pts'], eb_thickness, _sides)
                                else:
                                    _orig_bbox = None
                                _geo_off_final = st.session_state.get(f"geo_off_{i}_{f_file.name}", 0.0)
                                block_configs.append({'id': i, 'active': active, 'order_idx': order_idx, 'passes': f_z, 'orig_z': z_vals, 'v_block': v_block, 'is_sep': is_sep_val, 'rk_override': rk_val, 'geo_off': _geo_off_final, 'orig_bbox': _orig_bbox})

            sorted_blocks = sorted([bc for bc in block_configs if bc['active']], key=lambda x: x['order_idx'])
            order = [b['id'] for b in sorted_blocks]

        # --- ייצור NC ---
        nc = ["%", "(DARWISH 56.1 - MPR + DXF)", f"N10 G90 G54 G21 G17"]; n_c = 20
        last_tool_id = None

        pass  # write_block_at_depth מוגדרת ברמת המודול

        if order:
            # הפרדה: בלוקים עם ניתוק vs בלי ניתוק
            # בלוק "עם ניתוק" = יש לו לפחות פסיעה אחת ≤ 0.2
            cutting_ids = [b_id for b_id in order if block_configs[b_id]['is_sep']]
            non_cutting_ids = [b_id for b_id in order if not block_configs[b_id]['is_sep']]

            # שלב 1: בלוקים ללא ניתוק - כל הפסיעות שלהם רצות ברצף
            for b_id in non_cutting_ids:
                b_cfg = block_configs[b_id]; v_block = b_cfg['v_block']
                it = v_block['paths'][0]
                for zv in b_cfg['passes']:
                    zv_final = zv - it['z_off'] - st.session_state.gz
                    nc, n_c, last_tool_id = write_block_at_depth(b_cfg, v_block, zv_final, it, nc, n_c, last_tool_id)

            # שלב 2: בלוקים עם ניתוק - לוגיקת גלים (כל הפסיעות חוץ מהאחרונה על כולם, ואז ניתוק)
            if cutting_ids:
                max_waves = max(len(block_configs[b_id]['passes']) for b_id in cutting_ids)
                for wave_idx in range(max_waves):
                    for b_id in cutting_ids:
                        b_cfg = block_configs[b_id]; v_block = b_cfg['v_block']
                        if wave_idx < len(b_cfg['passes']):
                            it = v_block['paths'][0]
                            zv_final = b_cfg['passes'][wave_idx] - it['z_off'] - st.session_state.gz
                            nc, n_c, last_tool_id = write_block_at_depth(b_cfg, v_block, zv_final, it, nc, n_c, last_tool_id)

        nc.extend([f"N{n_c} M30", "%"])
        with col_cfg:
            st.download_button(f"📥 הורד NC (גרסה 56.1)", "\n".join(nc), f"{f_file.name}.nc")
            # --- ייצור CIX ---
            cix_data = generate_cix_output(order, block_configs, wp_l, wp_w, thick, geo_texts, rotate)
            st.download_button(f"📥 הורד CIX (גרסה 56.1)", cix_data, f"{f_file.name}.cix",
                               key=f"dl_cix_{f_file.name}")

        # שמירת הגרף ב-session_state
        fig = go.Figure(); fig.update_layout(dragmode='pan', xaxis=dict(scaleanchor="y", scaleratio=1), yaxis=dict(scaleanchor="x", scaleratio=1), margin=dict(l=0, r=0, t=0, b=0), height=650)
        fig.add_shape(type="rect", x0=0, y0=0, x1=1300, y1=3050, line=dict(color="Gray", width=2), fillcolor="rgba(128,128,128,0.1)")
        fig.add_shape(type="rect", x0=st.session_state.off_x, y0=st.session_state.off_y, x1=wp_w+st.session_state.off_x, y1=wp_l+st.session_state.off_y, line=dict(color="Sienna", width=3), fillcolor="rgba(139, 69, 19, 0.4)")
        for b_id in order:
            b_cfg = block_configs[b_id]; v_block = b_cfg['v_block']
            order_idx = b_cfg['order_idx']
            for it in v_block['paths']:
                zv_calc = it['z']
                if it['z'] in b_cfg['orig_z']:
                    idx = b_cfg['orig_z'].index(it['z'])
                    if idx < len(b_cfg['passes']):
                        zv_calc = b_cfg['passes'][idx]
                    elif b_cfg['passes']:
                        zv_calc = b_cfg['passes'][-1]
                ti_calc = round(thick - (zv_calc - it['z_off'] - st.session_state.gz), 3)
                h_text = f"<b>[{order_idx}] {v_block['t_cnc']}</b>: {v_block['desc']}<br>קוטר: {it['diam']} מילימטר<br>TI: {ti_calc:.3f} מילימטר"
                ox, oy = zip(*it['pts']); color = "red" if v_block['missing'] else ("green" if v_block['is_dr'] else ("red" if b_cfg['is_sep'] else "blue"))
                if v_block['is_dr']:
                    # ציור עיגולים גיאומטריים אמיתיים בקואורדינטות מילימטר
                    r = it['diam'] / 2
                    theta = np.linspace(0, 2*np.pi, 32)
                    for pt in it['pts']:
                        cx = pt[0] + st.session_state.off_x
                        cy = pt[1] + st.session_state.off_y
                        circle_x = list(cx + r * np.cos(theta)) + [None]
                        circle_y = list(cy + r * np.sin(theta)) + [None]
                        fig.add_trace(go.Scatter(
                            x=circle_x, y=circle_y,
                            mode='lines',
                            line=dict(color=color, width=1.5),
                            fill='toself',
                            fillcolor=f'rgba(0,180,0,0.3)' if color == 'green' else f'rgba(255,0,0,0.3)',
                            hoverinfo="text", text=h_text, showlegend=False
                        ))
                else:
                    pts_list = it['pts']
                    _ow = v_block.get('orig_w', 0)
                    _oh = v_block.get('orig_h', 0)
                    _off = b_cfg.get('geo_off', 0.0)
                    _eb_off = -eb_thickness if (b_cfg['is_sep'] and eb_active and eb_thickness > 1e-9) else 0.0
                    if _ow > 0 or _oh > 0:
                        raw_w = round(_ow + 2*_off + 2*_eb_off, 1)
                        raw_h = round(_oh + 2*_off + 2*_eb_off, 1)
                        w_part = raw_h if rotate else raw_w
                        h_part = raw_w if rotate else raw_h
                    else:
                        w_part = round(max(p[0] for p in pts_list) - min(p[0] for p in pts_list), 1)
                        h_part = round(max(p[1] for p in pts_list) - min(p[1] for p in pts_list), 1)
                    h_text_with_dims = h_text + f"<br>📐 {w_part} × {h_part} מילימטר"
                    fig.add_trace(go.Scatter(x=[x+st.session_state.off_x for x in ox]+[ox[0]+st.session_state.off_x], y=[y+st.session_state.off_y for y in oy]+[oy[0]+st.session_state.off_y], mode='lines', line=dict(color=color, width=2), hoverinfo="text", text=h_text_with_dims, hoveron='fills+points+points', showlegend=False))
                    eff_rk = b_cfg.get('rk_override', it['rk'])
                    s_p = calculate_path_v518(it['pts'], it['rad'], eff_rk, it['is_pocket'])
                    fig.add_trace(go.Scatter(x=[p[0]+st.session_state.off_x for p in s_p]+[None], y=[p[1]+st.session_state.off_y for p in s_p]+[None], mode='lines+markers', marker=dict(size=3, opacity=0.5), line=dict(color="yellow", dash="dash"), hoverinfo="text", text=h_text_with_dims, hoveron='fills+points', showlegend=False))
        with col_vis:
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

        # --- הדמיית קאנטים --- מופיעה רק כש שקלול פעיל
        if eb_active and block_configs:
            sep_bcs = sorted([bc for bc in block_configs if bc['is_sep'] and bc['active'] and bc.get('orig_bbox')],
                             key=lambda x: x['order_idx'])
            if sep_bcs:
                st.markdown('---')
                st.markdown('##### מפת קאנטים — לחץ על צלע כדי לבטל קאנט')
                eb_fig = go.Figure()
                eb_fig.update_layout(
                    xaxis=dict(scaleanchor='y', scaleratio=1, showgrid=False),
                    yaxis=dict(scaleanchor='x', scaleratio=1, showgrid=False),
                    margin=dict(l=0, r=0, t=30, b=0), height=550,
                    dragmode='select', plot_bgcolor='rgba(30,30,30,0.8)',
                    clickmode='event+select'
                )
                eb_fig.add_shape(type='rect', x0=st.session_state.off_x, y0=st.session_state.off_y,
                                 x1=wp_w+st.session_state.off_x, y1=wp_l+st.session_state.off_y,
                                 line=dict(color='sienna', width=2), fillcolor='rgba(139,69,19,0.3)')
                trace_map = []  # (part_idx, side)
                for part_idx, bc in enumerate(sep_bcs):
                    bb = bc['orig_bbox']  # (min_x, max_x, min_y, max_y)
                    ox = st.session_state.off_x; oy = st.session_state.off_y
                    mn_x, mx_x, mn_y, mx_y = bb[0]+ox, bb[1]+ox, bb[2]+oy, bb[3]+oy
                    cx = (mn_x + mx_x) / 2; cy = (mn_y + mx_y) / 2
                    sides_def = [
                        ('top',    [[mn_x, mx_y], [mx_x, mx_y]]),
                        ('bottom', [[mn_x, mn_y], [mx_x, mn_y]]),
                        ('left',   [[mn_x, mn_y], [mn_x, mx_y]]),
                        ('right',  [[mx_x, mn_y], [mx_x, mx_y]]),
                    ]
                    for side, coords in sides_def:
                        sk = f"eb_edge_{f_file.name}_{part_idx}_{side}"
                        active_side = st.session_state.get(sk, True)
                        clr = '#22c55e' if active_side else '#555555'
                        lw = 8 if active_side else 3
                        mid_x = (coords[0][0] + coords[1][0]) / 2
                        mid_y = (coords[0][1] + coords[1][1]) / 2
                        hover_txt = f"חלק {part_idx+1} | הצלע: {side} | {'\xd7\x9c\xd7\x97\xd7\xa5 \xd7\x9c\xd7\x91\xd7\x99\xd7\x98\xd7\x95\xd7\x9c \xd7\xa7\xd7\x90\xd7\xa0\xd7\x98' if active_side else '\xd7\x9c\xd7\x97\xd7\xa5 \xd7\x9c\xd7\x94\xd7\xa4\xd7\xa2\xd7\x9c\xd7\xaa \xd7\xa7\xd7\x90\xd7\xa0\xd7\x98'}"
                        # Visual line (not selectable)
                        eb_fig.add_trace(go.Scatter(
                            x=[c[0] for c in coords], y=[c[1] for c in coords],
                            mode='lines', line=dict(color=clr, width=lw),
                            hoverinfo='skip', showlegend=False
                        ))
                        trace_map.append((part_idx, 'line'))  # visual only
                        # Clickable marker at midpoint
                        eb_fig.add_trace(go.Scatter(
                            x=[mid_x], y=[mid_y],
                            mode='markers',
                            marker=dict(size=18, color=clr, opacity=0.85, symbol='square',
                                        line=dict(color='white', width=1.5)),
                            name=f'eb_{part_idx}_{side}',
                            hoverinfo='text', text=hover_txt,
                            showlegend=False
                        ))
                        trace_map.append((part_idx, side))
                    # מספר במרכז
                    eb_fig.add_trace(go.Scatter(
                        x=[cx], y=[cy], mode='text',
                        text=[str(part_idx+1)],
                        textfont=dict(size=16, color='white'),
                        hoverinfo='skip', showlegend=False
                    ))
                    trace_map.append((part_idx, 'label'))

                last_sel_key = f"last_eb_sel_{f_file.name}"
                eb_event = st.plotly_chart(
                    eb_fig, use_container_width=True,
                    config={'scrollZoom': True},
                    on_select='rerun',
                    key=f'eb_plot_{f_file.name}'
                )
                if eb_event and eb_event.selection and eb_event.selection.points:
                    sel_sig = str([(p.get('curve_number'), p.get('point_number'))
                                   for p in eb_event.selection.points])
                    if sel_sig != st.session_state.get(last_sel_key, ''):
                        st.session_state[last_sel_key] = sel_sig
                        for pt in eb_event.selection.points:
                            curve_num = pt.get('curve_number', -1)
                            if 0 <= curve_num < len(trace_map):
                                p_idx, side = trace_map[curve_num]
                                if side != 'label':
                                    k = f"eb_edge_{f_file.name}_{p_idx}_{side}"
                                    st.session_state[k] = not st.session_state.get(k, True)
                        st.rerun()


# ============================================================
# לשוניות DXF — אותה תשתית בדיוק כמו MPR
# ============================================================
if upl_dxf:
    st.divider()
    st.subheader("📐 קבצי DXF")
    tool_db_dxf = st.session_state.machine_profiles[st.session_state.get('active_machine', 'אבי')]
    if not isinstance(tool_db_dxf, pd.DataFrame):
        tool_db_dxf = pd.DataFrame(tool_db_dxf)

    dxf_tab_names = [f.name for f in upl_dxf]
    dxf_tabs = st.tabs(dxf_tab_names)

    for dxf_file, dxf_tab in zip(upl_dxf, dxf_tabs):
        with dxf_tab:
            dxf_text = dxf_file.getvalue().decode('utf-8', errors='ignore')
            polys_by_layer = parse_dxf_to_entities(dxf_text)

            # זיהוי פלטה ואופסט
            dxf_wp_l, dxf_wp_w, dxf_off_x, dxf_off_y = get_dxf_board_and_offset(polys_by_layer)

            # שכבת פלטה = הגדולה ביותר — סינון שכבות פעולה
            board_layer = None
            best_area = 0
            for lname, shapes in polys_by_layer.items():
                for pts in shapes:
                    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
                    area = (max(xs)-min(xs)) * (max(ys)-min(ys))
                    if area > best_area:
                        best_area = area; board_layer = lname

            op_layers = [l for l in polys_by_layer if l != board_layer and
                       (identify_dxf_layer(l) or find_tool_by_dxf_name(l, tool_db_dxf)[0] is not None)]

            # שדה עובי ידני (DXF הוא דו-מימדי)
            thick_key = f"dxf_thick_{dxf_file.name}"
            if thick_key not in st.session_state:
                st.session_state[thick_key] = 18.0

            col_cfg_d, col_vis_d = st.columns([1, 2])
            with col_cfg_d:
                dxf_thick = st.number_input("עובי פלטה מ-מ",
                    value=st.session_state[thick_key], step=0.5,
                    key=f"thick_inp_{dxf_file.name}")
                st.session_state[thick_key] = dxf_thick
                st.info(f"📐 {dxf_wp_l:.1f} x {dxf_wp_w:.1f} מ-מ | עובי: {dxf_thick} מ-מ | שכבות: {len(op_layers)}")

            # בניית ops מכל השכבות
            dxf_ops = []
            for lname in op_layers:
                shapes = polys_by_layer.get(lname, [])
                ops_l = dxf_shapes_to_ops(lname, shapes, tool_db_dxf,
                                          rotate, dxf_wp_w, dxf_wp_l,
                                          dxf_thick, dxf_off_x, dxf_off_y)
                dxf_ops.extend(ops_l)

            if flip_180:
                nc_bx_d = dxf_wp_w if rotate else dxf_wp_l
                nc_by_d = dxf_wp_l if rotate else dxf_wp_w
                for op in dxf_ops:
                    op['pts'] = [[nc_bx_d - p[0], nc_by_d - p[1]] for p in op['pts']]

            # visual_blocks — זהה למבנה MPR
            dxf_visual_blocks = {}
            for op in dxf_ops:
                v_key = (op['t_cnc'], op['type'], op['ea'])
                if v_key not in dxf_visual_blocks:
                    dxf_visual_blocks[v_key] = {
                        't_cnc': op['t_cnc'], 'desc': op['desc'], 'type': op['type'],
                        'is_dr': op['type'] == '102', 'paths': [],
                        's': op['s'], 'f': op['f'], 'diam': op['diam'],
                        'ea_id': op['ea'], 'missing': op['missing']
                    }
                dxf_visual_blocks[v_key]['paths'].append(op)

            for vk in dxf_visual_blocks:
                if dxf_visual_blocks[vk]['is_dr']:
                    dxf_visual_blocks[vk]['paths'] = optimize_drill_path_v518(dxf_visual_blocks[vk]['paths'])

            # קיבוץ וסדר — זהה ל-MPR
            dxf_blocks_list = []
            for v_key, v_block in dxf_visual_blocks.items():
                z_vals = sorted(list(set(p['z'] for p in v_block['paths'])), reverse=True)
                is_sep = any(z <= 0.2 for z in z_vals)
                dxf_blocks_list.append((v_key, v_block, z_vals, is_sep))

            dxf_tool_groups = {}; dxf_sep_blocks = []
            for item in dxf_blocks_list:
                t = item[1]['t_cnc']
                if item[3]: dxf_sep_blocks.append(item)
                else:
                    dxf_tool_groups.setdefault(t, []).append(item)

            dxf_ordered = []
            seen = []
            for item in dxf_blocks_list:
                t = item[1]['t_cnc']
                if not item[3] and t not in seen:
                    seen.append(t); dxf_ordered.extend(dxf_tool_groups[t])
            dxf_ordered.extend(dxf_sep_blocks)

            dxf_def_idx_map = {}
            sep_c = 1000; reg_c = 10
            for item in dxf_ordered:
                if item[3]: dxf_def_idx_map[item[0]] = sep_c; sep_c += 10
                else:        dxf_def_idx_map[item[0]] = reg_c;  reg_c += 10

            dxf_block_configs = []
            dxf_order = []

            with col_cfg_d:
                with st.container(height=500):
                    with st.expander(f"📦 ניהול בלוקים: {dxf_file.name}", expanded=False):
                        dxf_all_raw = []
                        for i, (v_key, v_block) in enumerate(dxf_visual_blocks.items()):
                            z_vals = sorted(list(set(p['z'] for p in v_block['paths'])), reverse=True)
                            pass_key = f"dxf_passes_{i}_{dxf_file.name}"
                            if pass_key not in st.session_state:
                                st.session_state[pass_key] = [float(z) for z in z_vals]
                            def_idx = dxf_def_idx_map.get(v_key, 500+i*10)
                            is_sep_val = any(z <= 0.2 for z in st.session_state.get(pass_key, z_vals))
                            active_key = f"dxf_active_{i}_{dxf_file.name}"
                            if active_key not in st.session_state:
                                st.session_state[active_key] = not v_block['missing']
                            cur_idx = st.session_state.get(f"dxf_idx_{i}_{dxf_file.name}", def_idx)
                            dxf_all_raw.append((i, v_key, v_block, z_vals, is_sep_val, def_idx, pass_key, cur_idx))

                        dxf_all_sorted = sorted(dxf_all_raw, key=lambda x: x[7])

                        for i, v_key, v_block, z_vals, is_sep_val, def_idx, pass_key, cur_idx in dxf_all_sorted:
                            current_passes_for_icon = st.session_state.get(pass_key, z_vals)
                            is_sep_val = any(z <= 0.2 for z in current_passes_for_icon)
                            z_str = " -> ".join([str(z) for z in current_passes_for_icon])
                            sep_icon = "🔴" if is_sep_val else "🔵"
                            miss_icon = "❌ " if v_block['missing'] else ""
                            label = f"[{cur_idx}] {sep_icon} {miss_icon}{v_block['t_cnc']} | {v_block['desc']} | {z_str}"
                            with st.expander(label, expanded=False):
                                active = st.checkbox("כלול בייצור",
                                    value=st.session_state[f"dxf_active_{i}_{dxf_file.name}"],
                                    key=f"dxf_act_{i}_{dxf_file.name}")
                                st.session_state[f"dxf_active_{i}_{dxf_file.name}"] = active
                                order_idx = st.number_input("סדר ביצוע", value=def_idx,
                                    key=f"dxf_idx_{i}_{dxf_file.name}")
                                if not v_block['is_dr']:
                                    rk_key_d = f"dxf_rk_{i}_{dxf_file.name}"
                                    default_rk_d = v_block['paths'][0]['rk'] if v_block['paths'] else 'WRKR'
                                    rk_map_d = {'WRKR': 'R — ימין (חיצוני)', 'WRKL': 'L — שמאל (פנימי)', 'NoWRK': 'C — על הקו'}
                                    rk_opts_d = list(rk_map_d.values())
                                    rk_def_d = rk_map_d.get(default_rk_d, rk_opts_d[0])
                                    if rk_key_d not in st.session_state:
                                        st.session_state[rk_key_d] = rk_def_d
                                    sel_rk_d = st.selectbox("כיוון סכין", rk_opts_d, index=rk_opts_d.index(st.session_state[rk_key_d]) if st.session_state[rk_key_d] in rk_opts_d else 0, key=f"dxf_rk_sel_{i}_{dxf_file.name}")
                                    st.session_state[rk_key_d] = sel_rk_d
                                    rk_val_d = {v: k for k, v in rk_map_d.items()}.get(sel_rk_d, default_rk_d)
                                else:
                                    rk_val_d = 'WRKL'
                                cur_passes = st.session_state[pass_key]
                                f_z = []; to_delete = None
                                for zi, z_val in enumerate(cur_passes):
                                    is_cut = z_val <= 0.2
                                    col_z, col_del = st.columns([4, 1])
                                    with col_z:
                                        lbl = f"{'🔴 ניתוק' if is_cut else '🔵 פסיעה'} {zi+1}"
                                        _dxf_rctr = st.session_state.get(f"dxf_rctr_{i}_{dxf_file.name}", 0)
                                        new_val = st.number_input(lbl, value=float(z_val),
                                            key=f"dxf_z_{i}_{zi}_{dxf_file.name}_r{_dxf_rctr}")
                                        f_z.append(new_val)
                                    with col_del:
                                        st.write("")
                                        if st.button("✕", key=f"dxf_del_{i}_{zi}_{dxf_file.name}"):
                                            to_delete = zi
                                if to_delete is not None:
                                    st.session_state[pass_key].pop(to_delete); st.rerun()
                                if st.button("➕ הוסף פסיעה", key=f"dxf_add_{i}_{dxf_file.name}"):
                                    last_z = st.session_state[pass_key][-1] if st.session_state[pass_key] else 2.0
                                    st.session_state[pass_key].append(max(0.5, last_z - 2.0) if last_z > 0.2 else 2.0); st.rerun()
                                if not v_block['is_dr']:
                                    cur_wh_d = _block_wh(v_block)
                                    btn_label_d = f"⚡ החל על כל {v_block['t_cnc']} | {cur_wh_d[0]}×{cur_wh_d[1]}"
                                    if st.button(btn_label_d, key=f"dxf_apply_all_{i}_{dxf_file.name}"):
                                        for j2, v_key2, v_block2, z_vals2, _, _, pass_key2, _ in dxf_all_sorted:
                                            if j2 != i and not v_block2['is_dr'] and _block_wh(v_block2) == cur_wh_d:
                                                st.session_state[pass_key2] = list(f_z)
                                                for _zi2, _z2 in enumerate(f_z):
                                                    st.session_state[f"dxf_z_{j2}_{_zi2}_{dxf_file.name}"] = _z2
                                                st.session_state[f"dxf_rk_{j2}_{dxf_file.name}"] = rk_val_d
                                                st.session_state[f"dxf_rk_sel_{j2}_{dxf_file.name}"] = sel_rk_d
                                        st.rerun()
                                    # כפתור 3: החל על כל בלוקי אותו כלי + WRKR (ללא תנאי גיאומטריה)
                                    if rk_val_d == 'WRKR' and st.button(f"⚡ החל {v_block['t_cnc']} על כולם (WRKR)", key=f"dxf_apply_wrkr_{i}_{dxf_file.name}"):
                                        for j2, v_key2, v_block2, z_vals2, _, _, pass_key2, _ in dxf_all_sorted:
                                            if j2 != i and not v_block2['is_dr'] and v_block2['t_cnc'] == v_block['t_cnc']:
                                                rk2_d = st.session_state.get(f"dxf_rk_{j2}_{dxf_file.name}", 'WRKR')
                                                if rk2_d in ('WRKR', 'R — ימין (חיצוני)'):
                                                    st.session_state[pass_key2] = list(f_z)
                                                    st.session_state[f"dxf_rctr_{j2}_{dxf_file.name}"] = st.session_state.get(f"dxf_rctr_{j2}_{dxf_file.name}", 0) + 1
                                        st.rerun()
                                    cur_has_cut_d = any(z <= 0.2 for z in f_z)
                                    btn_label2_d = f"⚡⚡ החל על כל ניתוקי {v_block['t_cnc']}"
                                    if cur_has_cut_d and st.button(btn_label2_d, key=f"dxf_apply_cuts_{i}_{dxf_file.name}"):
                                        for j2, v_key2, v_block2, z_vals2, _, _, pass_key2, _ in dxf_all_sorted:
                                            if j2 != i and not v_block2['is_dr'] and v_block2['t_cnc'] == v_block['t_cnc']:
                                                cur_is_cut2 = any(z <= 0.2 for z in st.session_state.get(pass_key2, z_vals2))
                                                if cur_is_cut2 and rk_val_d in ('WRKR', 'R — ימין (חיצוני)'):
                                                    st.session_state[pass_key2] = list(f_z)
                                                    st.session_state[f"dxf_rctr_{j2}_{dxf_file.name}"] = st.session_state.get(f"dxf_rctr_{j2}_{dxf_file.name}", 0) + 1
                                                    st.session_state[f"dxf_rk_{j2}_{dxf_file.name}"] = rk_val_d
                                                    st.session_state[f"dxf_rk_sel_{j2}_{dxf_file.name}"] = sel_rk_d
                                        st.rerun()
                                if not v_block['is_dr']:
                                    dxf_geo_off_key = f"dxf_geo_off_{i}_{dxf_file.name}"
                                    _col_doff1, _col_doff2 = st.columns([2, 1])
                                    with _col_doff1:
                                        new_dxf_geo_off = st.number_input("Offset (mm)", value=st.session_state.get(dxf_geo_off_key, 0.0), step=0.1, key=f"dxf_geo_off_inp_{i}_{dxf_file.name}")
                                    with _col_doff2:
                                        st.write("")
                                        if st.button("📐 החל על זהים", key=f"dxf_geo_off_btn_{i}_{dxf_file.name}"):
                                            _cur_wh_d = _block_wh(v_block)
                                            for j2, v_key2, v_block2, _, _, _, _, _ in dxf_all_sorted:
                                                if not v_block2['is_dr'] and _block_wh(v_block2) == _cur_wh_d:
                                                    st.session_state[f"dxf_geo_off_{j2}_{dxf_file.name}"] = new_dxf_geo_off
                                            st.rerun()
                                    st.session_state[dxf_geo_off_key] = new_dxf_geo_off
                                if f_z: st.session_state[pass_key] = f_z
                                is_sep_val = any(z <= 0.2 for z in f_z)
                                if not v_block['is_dr']:
                                    _dxf_geo_off = st.session_state.get(f"dxf_geo_off_{i}_{dxf_file.name}", 0.0)
                                    if abs(_dxf_geo_off) > 1e-9:
                                        for _path_op in v_block['paths']:
                                            _path_op['pts'] = apply_geo_offset(_path_op['pts'], _dxf_geo_off)
                                    # שקלול קאנטים — מקטין ניתוקים ו-CUT בעובי הקאנט
                                    is_eb_candidate = is_sep_val or (v_block.get('type') == '105')
                                    if is_eb_candidate and eb_active and eb_thickness > 1e-9:
                                        for _path_op in v_block['paths']:
                                            _path_op['pts'] = apply_geo_offset(_path_op['pts'], -eb_thickness)
                                _dxf_geo_off_final = st.session_state.get(f"dxf_geo_off_{i}_{dxf_file.name}", 0.0)
                                dxf_block_configs.append({
                                    'id': i, 'active': active, 'order_idx': order_idx,
                                    'passes': f_z, 'orig_z': z_vals,
                                    'v_block': v_block, 'is_sep': is_sep_val,
                                    'rk_override': rk_val_d, 'geo_off': _dxf_geo_off_final
                                })

                dxf_sorted_blocks = sorted([bc for bc in dxf_block_configs if bc['active']], key=lambda x: x['order_idx'])
                dxf_order = [b['id'] for b in dxf_sorted_blocks]

                # NC — אותה לוגיקה כמו MPR
                dxf_nc = ['%', '(DARWISH 56.1 - DXF)', 'N10 G90 G54 G21 G17']
                dxf_n_c = 20; dxf_last_tool = None

                if dxf_order:
                    cut_ids = [b for b in dxf_order if dxf_block_configs[b]['is_sep']]
                    non_cut_ids = [b for b in dxf_order if not dxf_block_configs[b]['is_sep']]
                    for b_id in non_cut_ids:
                        b_cfg = dxf_block_configs[b_id]; vb = b_cfg['v_block']; it = vb['paths'][0]
                        for zv in b_cfg['passes']:
                            zv_f = zv - it['z_off'] - st.session_state.gz
                            dxf_nc, dxf_n_c, dxf_last_tool = write_block_at_depth(b_cfg, vb, zv_f, it, dxf_nc, dxf_n_c, dxf_last_tool)
                    if cut_ids:
                        max_w = max(len(dxf_block_configs[b]['passes']) for b in cut_ids)
                        for wi in range(max_w):
                            for b_id in cut_ids:
                                b_cfg = dxf_block_configs[b_id]; vb = b_cfg['v_block']
                                if wi < len(b_cfg['passes']):
                                    it = vb['paths'][0]; zv_f = b_cfg['passes'][wi] - it['z_off'] - st.session_state.gz
                                    dxf_nc, dxf_n_c, dxf_last_tool = write_block_at_depth(b_cfg, vb, zv_f, it, dxf_nc, dxf_n_c, dxf_last_tool)

                dxf_nc.extend([f"N{dxf_n_c} M30", "%"])
                st.download_button(f"📥 הורד NC (DXF — 56.0)",
                    "\n".join(dxf_nc), f"{dxf_file.name}.nc",
                    key=f"dl_dxf_{dxf_file.name}")
                # --- ייצור CIX ל-DXF ---
                dxf_cix_data = generate_cix_output(
                    dxf_order, dxf_block_configs, dxf_wp_l, dxf_wp_w, dxf_thick, {}, rotate)
                st.download_button(f"📥 הורד CIX (DXF — 56.0)", dxf_cix_data,
                    f"{dxf_file.name}.cix", key=f"dl_cix_dxf_{dxf_file.name}")

            with col_vis_d:
                fig_d = go.Figure()
                fig_d.update_layout(dragmode='pan',
                    xaxis=dict(scaleanchor="y", scaleratio=1),
                    yaxis=dict(scaleanchor="x", scaleratio=1),
                    margin=dict(l=0,r=0,t=0,b=0), height=650)
                # שולחן
                fig_d.add_shape(type="rect", x0=0, y0=0, x1=1300, y1=3050,
                    line=dict(color="Gray", width=2), fillcolor="rgba(128,128,128,0.1)")
                # פלטה (מנורמלת)
                off_x_disp = st.session_state.off_x
                off_y_disp = st.session_state.off_y
                if rotate:
                    fig_d.add_shape(type="rect",
                        x0=off_x_disp, y0=off_y_disp,
                        x1=dxf_wp_w+off_x_disp, y1=dxf_wp_l+off_y_disp,
                        line=dict(color="Sienna", width=3), fillcolor="rgba(139,69,19,0.4)")
                else:
                    fig_d.add_shape(type="rect",
                        x0=off_x_disp, y0=off_y_disp,
                        x1=dxf_wp_l+off_x_disp, y1=dxf_wp_w+off_y_disp,
                        line=dict(color="Sienna", width=3), fillcolor="rgba(139,69,19,0.4)")

                for b_id in dxf_order:
                    b_cfg = dxf_block_configs[b_id]; v_block = b_cfg['v_block']
                    order_idx = b_cfg['order_idx']
                    for it in v_block['paths']:
                        zv_calc = b_cfg['passes'][0] if b_cfg['passes'] else it['z']
                        ti_calc = round(dxf_thick - (zv_calc - it['z_off'] - st.session_state.gz), 3)
                        h_text = f"<b>[{order_idx}] {v_block['t_cnc']}</b>: {v_block['desc']}<br>קוטר: {it['diam']} מ-מ<br>TI: {ti_calc:.3f} מ-מ"
                        color = "red" if v_block['missing'] else ("green" if v_block['is_dr'] else ("red" if b_cfg['is_sep'] else "blue"))
                        if v_block['is_dr']:
                            r_c = it['diam'] / 2
                            theta = np.linspace(0, 2*np.pi, 32)
                            for pt in it['pts']:
                                cx_c = pt[0] + off_x_disp
                                cy_c = pt[1] + off_y_disp
                                fig_d.add_trace(go.Scatter(
                                    x=list(cx_c + r_c*np.cos(theta))+[None],
                                    y=list(cy_c + r_c*np.sin(theta))+[None],
                                    mode='lines', line=dict(color=color, width=1.5),
                                    fill='toself',
                                    fillcolor='rgba(0,180,0,0.3)' if color=='green' else 'rgba(255,0,0,0.3)',
                                    hoverinfo='text', text=h_text, showlegend=False))
                        else:
                            pts_list = it['pts']
                            ox = [p[0]+off_x_disp for p in pts_list]
                            oy = [p[1]+off_y_disp for p in pts_list]
                            _ow = v_block.get('orig_w', 0)
                            _oh = v_block.get('orig_h', 0)
                            _off = b_cfg.get('geo_off', 0.0)
                            _eb_off = -eb_thickness if (b_cfg['is_sep'] and eb_active and eb_thickness > 1e-9) else 0.0
                            if _ow > 0 or _oh > 0:
                                raw_w = round(_ow + 2*_off + 2*_eb_off, 1)
                                raw_h = round(_oh + 2*_off + 2*_eb_off, 1)
                                w_p = raw_h if rotate else raw_w
                                h_p = raw_w if rotate else raw_h
                            else:
                                w_p = round(max(p[0] for p in pts_list)-min(p[0] for p in pts_list),1)
                                h_p = round(max(p[1] for p in pts_list)-min(p[1] for p in pts_list),1)
                            h_text2 = h_text + f"<br>📐 {w_p} × {h_p} מ-מ"
                            fig_d.add_trace(go.Scatter(
                                x=ox+[ox[0]], y=oy+[oy[0]],
                                mode='lines', line=dict(color=color, width=2),
                                hoverinfo='text', text=h_text2,
                                hoveron='fills+points+points', showlegend=False))
                            eff_rk_d = b_cfg.get('rk_override', it['rk'])
                            s_p = calculate_path_v518(it['pts'], it['rad'], eff_rk_d, it['is_pocket'])
                            fig_d.add_trace(go.Scatter(
                                x=[p[0]+off_x_disp for p in s_p]+[None],
                                y=[p[1]+off_y_disp for p in s_p]+[None],
                                mode='lines+markers', marker=dict(size=3, opacity=0.5),
                                line=dict(color='yellow', dash='dash'),
                                hoverinfo='text', text=h_text2,
                                hoveron='fills+points', showlegend=False))

                st.plotly_chart(fig_d, use_container_width=True, config={'scrollZoom': True})
