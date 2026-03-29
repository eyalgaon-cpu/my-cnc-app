import streamlit as st
import re, os, zipfile

# הגדרות הכלים הסופיות של אבי השכן
AVI_LOGIC = {
    "142": {"name": "כרסום 6 מילימטר", "cnc": "T2"},
    "158": {"name": "כרסום 8 מילימטר", "cnc": "T3"},
    "128": {"name": "כרסום 12 מילימטר", "cnc": "T4"},
    "140": {"name": "כרסום 3 מילימטר", "cnc": "T11"},
    "130": {"name": "כרסום 45 מעלות", "cnc": "T13"},
    "121": {"name": "מקדח 5 מילימטר", "cnc": "T44"},
    "149": {"name": "מקדח 15 מילימטר", "cnc": "T49"}
}

def convert_logic(mpr_text, tool_mapping, num_passes):
    t_match = re.search(r't="([\d.]+)"', mpr_text)
    thickness = float(t_match.group(1)) if t_match else 16.5
    geometries = {}
    blocks = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(blocks), 2):
        block_id, pts = blocks[i], []
        for line in blocks[i+1].split('\n'):
            x_m, y_m = re.search(r'X=([\d.-]+)', line), re.search(r'Y=([\d.-]+)', line)
            if x_m and y_m: pts.append((float(x_m.group(1)), float(y_m.group(1))))
        geometries[block_id] = pts

    nc_out, l_num, last_tool = [], 10, ""
    drills = re.findall(r'<102.*?XA="([\d.]+)".*?YA="([\d.]+)".*?TI="([\d.]+)".*?(?:TNO="(\d+)")?.*?', mpr_text, re.DOTALL)
    for x, y, depth, tno in drills:
        tno = tno if tno else "121"
        cnc_tool = tool_mapping.get(tno, {"cnc": "T44"})["cnc"]
        if cnc_tool != last_tool:
            nc_out.extend([f"N{l_num} {cnc_tool} M06", f"N{l_num+10} G43 H{cnc_tool[1:]} S4000 M03"])
            l_num, last_tool = l_num + 20, cnc_tool
        z_target = round(thickness - float(depth), 3)
        nc_out.extend([f"N{l_num} G00 X{float(x):.3f} Y{float(y):.3f}", f"N{l_num+10} G01 Z{z_target:.3f} F2000.0", f"N{l_num+20} G00 Z{thickness + 10:.3f}"])
        l_num += 30

    millings = re.findall(r'<105.*?EA="(\d+):.*?ZA="([\d.-]+)".*?TNO="(\d+)".*?', mpr_text, re.DOTALL)
    for geo_id, za, tno in millings:
        cnc_tool = tool_mapping.get(tno, {"cnc": "T2"})["cnc"]
        if cnc_tool != last_tool:
            nc_out.extend([f"N{l_num} {cnc_tool} M06", f"N{l_num+10} G43 H{cnc_tool[1:]} S17000 M03"])
            l_num, last_tool = l_num + 20, cnc_tool
        pts = geometries.get(geo_id)
        if pts:
            z_levels = [float(za)] if num_passes != 2 else [2.0, -0.2]
            for z_val in z_levels:
                nc_out.append(f"N{l_num} G00 X{pts[0][0]:.3f} Y{pts[0][1]:.3f}")
                l_num += 10
                nc_out.append(f"N{l_num} G01 Z{z_val:.3f} F3000.0")
                l_num += 10
                for px, py in pts[1:]:
                    nc_out.append(f"N{l_num} G01 X{px:.3f} Y{py:.3f}")
                    l_num += 10
                nc_out.append(f"N{l_num} G00 Z{thickness + 10:.3f}")
                l_num += 10
    nc_out.append(f"N{l_num} M30")
    return "\n".join(nc_out)

st.set_page_config(page_title="Darwish CNC Pro", page_icon="🪚")
st.title("🪚 המרת MPR ל-NC - גרסת אבי השכן")

st.sidebar.header("הגדרות כלים")
for tno, d in AVI_LOGIC.items():
    st.sidebar.text(f"• {d['name']} ({tno}) -> {d['cnc']}")

mode = st.radio("בחר שיטת עבודה:", ('לפי MPR', '2 פסיעות (2.0 ומינוס 0.2)'))
pass_val = 2 if '2 פסיעות' in mode else 0

uploaded = st.file_uploader("העלה קבצי MPR (אפשר כמה יחד)", accept_multiple_files=True)

if uploaded:
    if st.button("בצע המרה וארוז ל-ZIP", type="primary"):
        zip_path = 'CNC_KITCHEN_FILES.zip'
        with zipfile.ZipFile(zip_path, 'w') as zip_f:
            for file in uploaded:
                content = file.read().decode('utf-8', errors='ignore')
                res = convert_logic(content, AVI_LOGIC, pass_val)
                nc_name = file.name.replace(".mpr", ".nc")
                zip_f.writestr(nc_name, res)
        
        with open(zip_path, "rb") as f:
            st.download_button("📂 לחץ כאן להורדת ה-ZIP", f, zip_path)
