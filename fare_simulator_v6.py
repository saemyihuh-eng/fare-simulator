import streamlit as st
import pandas as pd
import altair as alt
import gspread

from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Net Avg Fare Simulator", layout="wide")

st.markdown("""
<style>
.result-card {
    background: #f0f7ff; border-radius: 10px;
    padding: 14px 18px; border: 1px solid #c0d8f0; margin-bottom: 8px;
}
.metric-card {
    background: #f8f9fa; border-radius: 10px;
    padding: 14px 18px; border: 1px solid #e0e0e0; margin-bottom: 8px;
}
.result-header {
    background: #1a1a2e; color: white; padding: 12px 20px;
    border-radius: 8px; font-weight: 700; font-size: 18px; margin: 16px 0 12px;
}
.sub-step-header {
    background: #f5f5f5; color: #2d2d2d; padding: 9px 16px;
    border-radius: 8px; font-weight: 600; font-size: 14px;
    border: 1px solid #bbb; margin: 20px 0 12px;
}
.label { font-size: 12px; color: #666; margin-bottom: 4px; }
.value-main { font-size: 22px; font-weight: 600; color: #1a1a2e; }
.value-sub { font-size: 13px; color: #444; margin-top: 2px; }
.delta-pos { color: #1D9E75; font-weight: 600; font-size: 13px; }
.delta-neg { color: #E24B4A; font-weight: 600; font-size: 13px; }
.delta-neu { color: #888; font-size: 13px; }
</style>
""", unsafe_allow_html=True)

st.title("Net Avg Fare Simulator")
st.caption("Google Sheets-Linked | Major Metric Simulation for Glide & Fare Changes")

SPREADSHEET_ID = "1NuHYrIU0SPv9uxaLI-n3SvDD1KSvBT8qEcSGnbL5EUk"

@st.cache_data(ttl=300)
def load_all_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds  = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    gc     = gspread.authorize(creds)
    sh     = gc.open_by_key(SPREADSHEET_ID)

    raw_gsma = sh.worksheet("WBR_City Level").get_all_values()
    header_row = 6
    gsma_headers = raw_gsma[header_row]
    gsma_data    = raw_gsma[header_row+1:]
    last_city = ""
    filled = []
    for row in gsma_data:
        if len(row) < len(gsma_headers):
            row = row + [""] * (len(gsma_headers) - len(row))
        if row[0].strip():
            last_city = row[0].strip()
        else:
            row[0] = last_city
        filled.append(row)
    df_gsma = pd.DataFrame(filled, columns=gsma_headers)
    df_gsma.columns = [c.strip() for c in df_gsma.columns]
    df_gsma.rename(columns={df_gsma.columns[0]: "city_name",
                             df_gsma.columns[1]: "Category",
                             df_gsma.columns[2]: "Metrics"}, inplace=True)

    raw_sub = sh.worksheet("Subscription").get_all_values()
    df_sub  = pd.DataFrame(raw_sub[1:], columns=raw_sub[0])
    df_sub.columns = [c.strip() for c in df_sub.columns]

    raw_glide = sh.worksheet("Glide").get_all_values()
    df_glide  = pd.DataFrame(raw_glide[1:], columns=raw_glide[0])
    df_glide.columns = [c.strip() for c in df_glide.columns]

    raw_price = sh.worksheet("Price").get_all_values()
    df_price  = pd.DataFrame(raw_price[1:], columns=raw_price[0])
    df_price.columns = [c.strip() for c in df_price.columns]

    raw_glide_hour = sh.worksheet("Glide_hour").get_all_values()
    df_glide_hour  = pd.DataFrame(raw_glide_hour[1:], columns=raw_glide_hour[0])
    df_glide_hour  = df_glide_hour.iloc[:, :20]
    df_glide_hour.columns = [c.strip() for c in df_glide_hour.columns]

    raw_opz = sh.worksheet("opz_Max_glide_minutes_list").get_all_values()
    headers = [c.strip() for c in raw_opz[0]]
    rows    = raw_opz[1:]
    opz_records = []
    for row in rows:
        if len(row) < len(headers):
            row = row + [""] * (len(headers) - len(row))
        opz_records.append({
            "city_name":         str(row[headers.index("city_name")]).strip(),
            "subregion_name":    str(row[headers.index("subregion_name")]).strip(),
            "max_glide_minutes": row[headers.index("max_glide_minutes")].strip() if "max_glide_minutes" in headers else "",
        })
    df_opz_list = pd.DataFrame(opz_records)
    df_opz_list["max_glide_minutes"] = pd.to_numeric(df_opz_list["max_glide_minutes"], errors="coerce").fillna(10).astype(int)

    return df_gsma, df_sub, df_glide, df_price, df_glide_hour, df_opz_list

with st.spinner("Loading data from Google Sheets..."):
    try:
        df_gsma, df_sub, df_glide, df_price, df_glide_hour, df_opz_list = load_all_sheets()
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        st.stop()

st.markdown("---")
col_city, col_week = st.columns(2)

with col_city:
    all_cities = df_gsma["city_name"].dropna().unique().tolist()
    all_cities = [c for c in all_cities if c.strip() != ""]

    priority_order = ["Country", "Namyangju", "Songpa", "Hanam", "Wirye"]
    priority_cities = [c for c in priority_order if c in all_cities]
    rest_cities = sorted([c for c in all_cities if c not in priority_order])
    cities = priority_cities + rest_cities

    selected_city = st.selectbox("City", cities,
                                  index=cities.index("Namyangju") if "Namyangju" in cities else 0)

week_cols = [c for c in df_gsma.columns if c.strip().startswith("Week")]

with col_week:
    selected_week = st.selectbox("Week", ["L4W AVG"] + week_cols[::-1])
    
gsma_city = df_gsma[df_gsma["city_name"] == selected_city].reset_index(drop=True)

def get_metric(df_city, metric_name, week_col):
    try:
        row = df_city[df_city["Metrics"].str.strip() == metric_name]
        if row.empty:
            return None

        if week_col == "L4W AVG":
            last4 = week_cols[::-1][:4]
            vals = []
            for wc in last4:
                v = row.iloc[0][wc]
                if str(v).strip() in ["", "-", "N/A"]:
                    continue
                try:
                    vals.append(float(str(v).replace("$","").replace("%","").replace(",","").strip()))
                except:
                    continue
            return sum(vals)/len(vals) if vals else None
            
        val = row.iloc[0][week_col]
        if str(val).strip() in ["", "-", "N/A"]:
            return None
        val_str = str(val).replace("$","").replace("%","").replace(",","").strip()
        return float(val_str)
    except:
        return None

def get_country_metric(df_gsma, metric_name, week_col, week_cols, offset=2):
    try:
        row = df_gsma[
            (df_gsma["city_name"].str.strip() == "Country") &
            (df_gsma["Metrics"].str.strip() == metric_name)
        ]
        if row.empty:
            return None

        if week_col == "L4W AVG":
            last4 = week_cols[::-1][:4]
            vals = []
            for wc in last4:
                col_idx = df_gsma.columns.get_loc(wc)
                v = row.iloc[0, col_idx + offset]
                if str(v).strip() in ["", "-", "N/A"]:
                    continue
                try:
                    vals.append(float(str(v).replace("$","").replace("%","").replace(",","").strip()))
                except:
                    continue
            return sum(vals)/len(vals) if vals else None

        col_idx = df_gsma.columns.get_loc(week_col)
        val = row.iloc[0, col_idx + offset]
        if str(val).strip() in ["", "-", "N/A"]:
            return None
        val_str = str(val).replace("$","").replace("%","").replace(",","").strip()
        return float(val_str)
    except:
        return None

cur_dv        = get_metric(gsma_city, "DV",                    selected_week) or 0
cur_trips     = get_metric(gsma_city, "Trips",                 selected_week) or 0
cur_duration  = get_metric(gsma_city, "Avg Trip Length (min)", selected_week) or 5.3
cur_gross_rev = get_metric(gsma_city, "Gross Revenue",         selected_week) or 0
cur_net_rev   = get_metric(gsma_city, "Net Revenue",           selected_week) or 0
cur_l1_cost   = get_metric(gsma_city, "L1 Cost",               selected_week) or 0

cur_net_avg_fare   = cur_net_rev / cur_trips        if cur_trips > 0 else 0
cur_gross_avg_fare = cur_gross_rev / cur_trips      if cur_trips > 0 else 0
cur_tpvd           = (cur_trips / 7) / cur_dv      if cur_dv > 0    else 0
cur_nrpvd          = (cur_net_rev / 7) / cur_dv    if cur_dv > 0    else 0
cur_grpvd          = (cur_gross_rev / 7) / cur_dv  if cur_dv > 0    else 0
cur_l1_profit      = cur_net_rev - cur_l1_cost
cur_l1_pct         = cur_l1_profit / cur_net_rev * 100 if cur_net_rev > 0 else 0
cur_cpt            = cur_l1_cost / cur_trips        if cur_trips > 0 else 0
cur_vcd            = cur_l1_profit / cur_dv / 7    if cur_dv > 0    else 0

_offset = 0 if selected_city == "Country" else 2

cty_trips   = get_country_metric(df_gsma, "Trips",       selected_week, week_cols, offset=_offset) or 0
cty_net_rev = get_country_metric(df_gsma, "Net Revenue", selected_week, week_cols, offset=_offset) or 0
cty_l1_cost = get_country_metric(df_gsma, "L1 Cost",     selected_week, week_cols, offset=_offset) or 0
cty_dv      = get_country_metric(df_gsma, "DV",          selected_week, week_cols, offset=_offset) or 0

cty_net_avg_fare = cty_net_rev / cty_trips if cty_trips > 0 else 0
cty_l1_profit    = cty_net_rev - cty_l1_cost
cty_l1_pct       = cty_l1_profit / cty_net_rev * 100 if cty_net_rev > 0 else 0
cty_nrpvd        = (cty_net_rev / 7) / cty_dv if cty_dv > 0 else 0

cty_gross_rev = get_country_metric(df_gsma, "Gross Revenue", selected_week, week_cols, offset=_offset) or 0
cty_grpvd     = (cty_gross_rev / 7) / cty_dv if cty_dv > 0 else 0
cty_tpvd      = (cty_trips / 7) / cty_dv if cty_dv > 0 else 0
cty_cpt       = cty_l1_cost / cty_trips if cty_trips > 0 else 0
cty_vcd       = cty_l1_profit / cty_dv / 7 if cty_dv > 0 else 0

if selected_week == "L4W AVG":
    prev_week = None
else:
    prev_week_idx = week_cols[::-1].index(selected_week)
    prev_week = week_cols[::-1][prev_week_idx + 1] if prev_week_idx + 1 < len(week_cols) else None
    
def get_wow(metric_name):
    if prev_week is None:
        return None
    try:
        return get_metric(gsma_city, metric_name, prev_week)
    except:
        return None

prev_net_rev   = get_wow("Net Revenue")
prev_trips     = get_wow("Trips")
prev_gross_rev = get_wow("Gross Revenue")
prev_l1_cost   = get_wow("L1 Cost")

prev_net_avg_fare = (prev_net_rev / prev_trips) if prev_net_rev and prev_trips else None
prev_tpvd         = ((prev_trips / 7) / cur_dv) if prev_trips and cur_dv > 0 else None
prev_nrpvd        = ((prev_net_rev / 7) / cur_dv) if prev_net_rev and cur_dv > 0 else None
prev_grpvd        = ((prev_gross_rev / 7) / cur_dv) if prev_gross_rev and cur_dv > 0 else None
prev_l1_profit    = (prev_net_rev - prev_l1_cost) if prev_net_rev and prev_l1_cost else None
prev_l1_pct       = (prev_l1_profit / prev_net_rev * 100) if prev_l1_profit and prev_net_rev else None
prev_cpt          = (prev_l1_cost / prev_trips) if prev_l1_cost and prev_trips else None
prev_vcd          = (prev_l1_profit / cur_dv / 7) if prev_l1_profit and cur_dv > 0 else None

def wow_badge(cur, prev):
    if prev is None or prev == 0:
        return ""
    pct = (cur - prev) / abs(prev) * 100
    sign = "▲" if pct > 0 else "▼"
    color = "#1D9E75" if pct > 0 else "#E24B4A"
    return f'<span style="font-size:11px;font-weight:600;color:{color};margin-left:6px;">{sign} {abs(pct):.1f}% WoW</span>'

if selected_week == "L4W AVG":
    week_num = []
    for wc in week_cols[::-1][:4]:
        try:
            week_num.append(int("".join(filter(str.isdigit, wc))))
        except:
            continue
else:
    try:
        week_num = int("".join(filter(str.isdigit, selected_week)))
    except:
        week_num = 18

def get_sub_metrics(df_sub, city, week_num):
    try:
        week_list = week_num if isinstance(week_num, list) else [week_num]
        df_f = df_sub[
            (df_sub["city_name"].str.strip() == city) &
            (df_sub["week_num"].astype(str).str.strip().isin([str(w) for w in week_list]))
        ].copy()
        df_f["trips_total"] = pd.to_numeric(df_f["trips_total"], errors="coerce").fillna(0)
        total = df_f["trips_total"].sum()
        if total == 0:
            return None, None, None, None
        day_trips   = df_f[df_f["timeofday"].str.strip() == "DAY"]["trips_total"].sum()
        night_trips = df_f[df_f["timeofday"].str.strip() == "NIGHT"]["trips_total"].sum()
        day_pct   = round(day_trips / total * 100, 2)
        night_pct = round(night_trips / total * 100, 2)
        day_fu    = df_f[(df_f["timeofday"]=="DAY")   & (df_f["pass_type"].str.strip()=="Free Unlock Pass")]["trips_total"].sum()
        night_fu  = df_f[(df_f["timeofday"]=="NIGHT") & (df_f["pass_type"].str.strip()=="Free Unlock Pass")]["trips_total"].sum()
        subs_day_pct   = round(day_fu / day_trips * 100, 2)     if day_trips > 0   else 0
        subs_night_pct = round(night_fu / night_trips * 100, 2) if night_trips > 0 else 0
        return day_pct, night_pct, subs_day_pct, subs_night_pct
    except:
        return None, None, None, None

day_pct, night_pct, subs_day, subs_night = get_sub_metrics(df_sub, selected_city, week_num)
day_pct_calc   = day_pct   if day_pct   is not None else 0
night_pct_calc = night_pct if night_pct is not None else 0
subs_day   = subs_day   if subs_day   is not None else 0
subs_night = subs_night if subs_night is not None else 0

def get_glide_by_opz(df_glide, city, week_num):
    try:
        week_list = week_num if isinstance(week_num, list) else [week_num]
        df_f = df_glide[
            (df_glide["city"].str.strip() == city) &
            (df_glide["weeknum"].astype(str).str.strip().isin([str(w) for w in week_list]))
        ].copy()
        df_f["region_name"] = df_f["region_name"].astype(str).str.strip()
        for col in ["glidesum", "noglide", "total_trips"]:
            df_f[col] = pd.to_numeric(df_f[col], errors="coerce").fillna(0)
        result = df_f.groupby(["region_name", "timeofday"]).agg(
            glidesum=("glidesum", "sum"),
            total_trips=("total_trips", "sum")
        ).reset_index()
        result["glide_pct"] = result.apply(
            lambda r: round(r["glidesum"]/r["total_trips"]*100, 2) if r["total_trips"] > 0 else 0, axis=1
        )
        return result
    except:
        return pd.DataFrame()

df_glide_opz = get_glide_by_opz(df_glide, selected_city, week_num)

def get_city_glide_pct(df_glide_opz, timeofday):
    try:
        df_tod = df_glide_opz[df_glide_opz["timeofday"].str.strip() == timeofday]
        if df_tod.empty:
            return 0
        total_trips = df_tod["total_trips"].sum()
        if total_trips == 0:
            return 0
        return round(df_tod["glidesum"].sum() / total_trips * 100, 2)
    except:
        return 0

# ══════════════════════════════════════════════════════
# [수정] get_price → OPZ 단위 dict + 도시 단위(opz 빈 행) 별도 반환
# ══════════════════════════════════════════════════════
def get_price_by_opz(df_price, city):
    """
    return:
      opz_dict  : { opz: {ppu_day, ppm_day, ppu_night, ppm_night, inflows_4w} }  (opz 비어있지 않은 행만)
      city_row  : {ppu_day, ppm_day, ppu_night, ppm_night, inflows_4w} 또는 None (opz가 빈 행, 도시 단위 가격)
    """
    try:
        df_f = df_price[df_price["city_name"].str.strip() == city].copy()
        if df_f.empty:
            return {}, None
        for col in ["ppu_day","ppm_day","ppu_night","ppm_night"]:
            df_f[col] = pd.to_numeric(df_f[col], errors="coerce").fillna(0)
        opz_dict = {}
        city_row = None
        for _, row in df_f.iterrows():
            opz = str(row["opz"]).strip()
            try:
                inflows_4w = float(str(row["inflows_4w_avg"]).replace("%","").strip()) / 100
            except:
                inflows_4w = 0
            entry = {
                "ppu_day": row["ppu_day"], "ppm_day": row["ppm_day"],
                "ppu_night": row["ppu_night"], "ppm_night": row["ppm_night"],
                "inflows_4w": inflows_4w,
            }
            if opz == "" or opz.lower() == "nan":
                city_row = entry  # opz 빈 행 = 도시 단위 가격
            else:
                opz_dict[opz] = entry
        return opz_dict, city_row
    except:
        return {}, None

price_by_opz, city_price_row = get_price_by_opz(df_price, selected_city)
price_opz_list = sorted(price_by_opz.keys())

def get_opz_trip_weight(df_glide_opz, opz, timeofday):
    """해당 OPZ의 DAY/NIGHT trip이 도시 전체 DAY/NIGHT trip에서 차지하는 비중(%)"""
    try:
        df_tod = df_glide_opz[df_glide_opz["timeofday"].str.strip() == timeofday]
        city_total = df_tod["total_trips"].sum()
        if city_total == 0:
            return 0
        opz_total = df_tod[df_tod["region_name"] == opz]["total_trips"].sum()
        return round(opz_total / city_total * 100, 2)
    except:
        return 0

# ══════════════════════════════════════════════════════
# ── 변경: get_glide_hour_pct 전면 수정 ──
# 인자: max_minutes (분 단위 정수)
# ── 컬럼 구조 ──
#   10분 단위: glide_0_10_min ~ glide_50_60_min  (0~60분)
#   시간 단위: glide_1_2_hours ~ glide_over_10_hours (1h~)
# ══════════════════════════════════════════════════════
def get_glide_hour_pct(df_glide_hour, city, opz, max_minutes):
    try:
        df_f = df_glide_hour[
            (df_glide_hour["City"].str.strip() == city) &
            (df_glide_hour["region_name"].str.strip() == opz)
        ].copy()
        if df_f.empty:
            return None

        min_cols = [
            "glide_0_10_min", "glide_10_20_min", "glide_20_30_min",
            "glide_30_40_min", "glide_40_50_min", "glide_50_60_min",
        ]
        hour_cols = [
            "glide_1_2_hours", "glide_2_4_hours", "glide_4_6_hours",
            "glide_6_8_hours", "glide_8_10_hours", "glide_over_10_hours",
        ]
        all_cols = min_cols + hour_cols

        for c in all_cols:
            df_f[c] = pd.to_numeric(df_f[c], errors="coerce").fillna(0)

        total = df_f[all_cols].sum().sum()
        if total == 0:
            return None

        min_col_map = {
            10:  min_cols[:1],
            20:  min_cols[:2],
            30:  min_cols[:3],
            40:  min_cols[:4],
            50:  min_cols[:5],
            60:  min_cols[:6],
        }
        hour_col_map = {
            120: min_cols + hour_cols[:1],
            240: min_cols + hour_cols[:2],
            360: min_cols + hour_cols[:3],
            480: min_cols + hour_cols[:4],
            600: min_cols + hour_cols[:5],
            720: min_cols + hour_cols[:6],
        }

        if max_minutes in min_col_map:
            within_cols = min_col_map[max_minutes]
        elif max_minutes in hour_col_map:
            within_cols = hour_col_map[max_minutes]
        else:
            within_cols = all_cols  # No Change (전체)

        within = df_f[within_cols].sum().sum()
        return round(within / total * 100, 1)
    except:
        return None

def get_opz_max_glide(df_opz_list, city, opz):
    row = df_opz_list[
        (df_opz_list["city_name"] == city) &
        (df_opz_list["subregion_name"] == opz)
    ]
    if row.empty:
        return 10
    return int(row["max_glide_minutes"].values[0])

def build_opz_box(total_cur, total_glide, total_all, day_pct, night_pct,
                  day_glide, day_total, night_glide, night_total,
                  delta, delta_color, prop_pct, info, info_color):
    if delta != 0:
        sign = "+" if delta > 0 else ""
        delta_part = (
            "<div style='font-size:11px;color:#1a1a2e;'>&rarr;</div>"
            "<div style='font-size:18px;font-weight:700;color:" + delta_color + ";'>" + str(round(prop_pct, 1)) + "%</div>"
            "<div style='font-size:11px;font-weight:600;color:" + delta_color + ";'>(" + sign + str(round(delta, 1)) + "%p)</div>"
        )
    else:
        delta_part = ""

    hour_div = "<div style='margin-top:8px;font-size:12px;font-weight:600;color:" + info_color + ";'>" + info + "</div>" if info else ""

    html  = "<div style='background:#f8f9fa;border:1px solid #e0e0e0;border-radius:10px;padding:14px 16px;margin-bottom:24px;text-align:center;'>"
    html += "<div style='font-size:11px;color:#999;margin-bottom:4px;'>Total</div>"
    html += "<div style='display:flex;align-items:center;justify-content:center;gap:8px;margin-bottom:4px;'>"
    html += "<div style='font-size:18px;font-weight:700;color:#1a1a2e;'>" + str(round(total_cur, 1)) + "%</div>"
    html += delta_part
    html += "</div>"
    html += "<div style='font-size:11px;color:#555;margin-bottom:10px;'>" + f"{int(total_glide):,}" + " / " + f"{int(total_all):,}" + "</div>"
    html += "<div style='display:flex;gap:16px;justify-content:center;'>"
    html += "<div><div style='font-size:11px;color:#999;margin-bottom:2px;'>DAY</div>"
    html += "<div style='font-size:16px;font-weight:700;color:#1D9E75;'>" + str(round(day_pct, 1)) + "%</div>"
    html += "<div style='font-size:11px;color:#555;'>" + f"{int(day_glide):,}" + " / " + f"{int(day_total):,}" + "</div></div>"
    html += "<div style='width:1px;background:#ddd;'></div>"
    html += "<div><div style='font-size:11px;color:#999;margin-bottom:2px;'>NIGHT</div>"
    html += "<div style='font-size:16px;font-weight:700;color:#7F77DD;'>" + str(round(night_pct, 1)) + "%</div>"
    html += "<div style='font-size:11px;color:#555;'>" + f"{int(night_glide):,}" + " / " + f"{int(night_total):,}" + "</div></div>"
    html += "</div>"
    html += hour_div
    html += "</div>"
    return html

# ══════════════════════════════════════════════════════
# Week's Metrics
# ══════════════════════════════════════════════════════
st.markdown("---")
st.markdown("### Week's Metrics")

def wow_badge_reverse(cur, prev):
    if prev is None or prev == 0:
        return ""
    pct = (cur - prev) / abs(prev) * 100
    sign = "▲" if pct > 0 else "▼"
    color = "#E24B4A" if pct > 0 else "#1D9E75"
    return f'<span style="font-size:11px;font-weight:600;color:{color};margin-left:6px;">{sign} {abs(pct):.1f}% WoW</span>'

def compare_badge(cur, nation, fmt="num", reverse=False):
    if not nation or selected_city == "Country":
        return ""
    diff = cur - nation
    pct = diff / abs(nation) * 100 if nation != 0 else 0
    sign = "+" if diff >= 0 else ""
    is_good = (diff <= 0) if reverse else (diff >= 0)
    color = "#1D9E75" if is_good else "#E24B4A"

    if fmt == "money":
        nation_str = f"${nation:.2f}"
    elif fmt == "pct":
        nation_str = f"{nation:.1f}%"
    else:
        nation_str = f"{nation:.2f}"

    return (
        f'<span style="font-size:11px;font-weight:600;color:#333;">'
        f'vs KR avg <span style="color:{color};">{nation_str} ({sign}{pct:.1f}%)</span>'
        f'</span>'
    )
    
def mcard(col, label, val, sub="", color=None, wow="", compare=""):
    color_style = f"color:{color};" if color else ""
    compare_box = (
        f'<div style="background:#f0f2f5;border-radius:6px;padding:4px 10px;margin-left:8px;white-space:nowrap;">{compare}</div>'
        if compare else ""
    )
    html = (
        '<div class="metric-card">'
        f'<div class="label">{label}</div>'
        '<div style="display:flex;align-items:flex-start;justify-content:space-between;">'
        '<div>'
        f'<div class="value-main" style="{color_style}">{val}{wow}</div>'
        f'<div class="value-sub">{sub}</div>'
        '</div>'
        f'{compare_box}'
        '</div>'
        '</div>'
    )
    col.markdown(html, unsafe_allow_html=True)

r1c1, r1c2, r1c3, r1c4 = st.columns(4)
mcard(r1c1, "Net Avg Fare", f"${cur_net_avg_fare:.2f}", f"Gross Avg Fare: ${cur_gross_avg_fare:.2f}", color="#1D9E75", wow=wow_badge(cur_net_avg_fare, prev_net_avg_fare), compare=compare_badge(cur_net_avg_fare, cty_net_avg_fare, "money"))
mcard(r1c2, "NRPVD",        f"${cur_nrpvd:.2f}",        f"Net Revenue: ${cur_net_rev:,.0f}",          wow=wow_badge(cur_nrpvd, prev_nrpvd), compare=compare_badge(cur_nrpvd, cty_nrpvd, "money"))
mcard(r1c3, "GRPVD",        f"${cur_grpvd:.2f}",        f"Gross Revenue: ${cur_gross_rev:,.0f}",      wow=wow_badge(cur_grpvd, prev_grpvd), compare=compare_badge(cur_grpvd, cty_grpvd, "money"))
mcard(r1c4, "TPVD",         f"{cur_tpvd:.2f}",          f"Trips: {cur_trips:,.0f}",                   wow=wow_badge(cur_tpvd, prev_tpvd), compare=compare_badge(cur_tpvd, cty_tpvd, "num"))

r2c1, r2c2, r2c3, _ = st.columns(4)
mcard(r2c1, "VCD", f"${cur_vcd:.2f}", f"DV: {cur_dv:,.0f}", wow=wow_badge(cur_vcd, prev_vcd), compare=compare_badge(cur_vcd, cty_vcd, "money"))
mcard(r2c2, "CPT", f"${cur_cpt:.2f}", f"L1 Cost: ${cur_l1_cost:,.0f}", wow=wow_badge_reverse(cur_cpt, prev_cpt), compare=compare_badge(cur_cpt, cty_cpt, "money", reverse=True))
mcard(r2c3, "L1 %", f"{cur_l1_pct:.1f}%", f"L1 Profit: ${cur_l1_profit:,.0f}", wow=wow_badge(cur_l1_pct, prev_l1_pct), compare=compare_badge(cur_l1_pct, cty_l1_pct, "pct"))

if selected_week == "L4W AVG":
    st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:16px;font-weight:600;color:#1a1a2e;margin-bottom:8px;'>4-Week Trend</div>", unsafe_allow_html=True)
    trend_weeks = week_cols[::-1][:4][::-1]
    
    trend_fare, trend_l1pct, trend_tpvd, trend_nrpvd = [], [], [], []
    trend_kr_fare, trend_kr_l1pct, trend_kr_tpvd, trend_kr_nrpvd = [], [], [], []
    for wc in trend_weeks:
        t_trips   = get_metric(gsma_city, "Trips", wc) or 0
        t_net_rev = get_metric(gsma_city, "Net Revenue", wc) or 0
        t_l1_cost = get_metric(gsma_city, "L1 Cost", wc) or 0
        t_dv      = get_metric(gsma_city, "DV", wc) or 0

        t_fare      = t_net_rev / t_trips if t_trips > 0 else 0
        t_l1_profit = t_net_rev - t_l1_cost
        t_l1_pct    = t_l1_profit / t_net_rev * 100 if t_net_rev > 0 else 0
        t_tpvd      = (t_trips / 7) / t_dv if t_dv > 0 else 0
        t_nrpvd     = (t_net_rev / 7) / t_dv if t_dv > 0 else 0

        trend_fare.append(round(t_fare, 2))
        trend_l1pct.append(round(t_l1_pct, 1))
        trend_tpvd.append(round(t_tpvd, 2))
        trend_nrpvd.append(round(t_nrpvd, 2))

        k_trips   = get_country_metric(df_gsma, "Trips",       wc, week_cols, offset=2) or 0
        k_net_rev = get_country_metric(df_gsma, "Net Revenue", wc, week_cols, offset=2) or 0
        k_l1_cost = get_country_metric(df_gsma, "L1 Cost",     wc, week_cols, offset=2) or 0
        k_dv      = get_country_metric(df_gsma, "DV",          wc, week_cols, offset=2) or 0

        k_fare      = k_net_rev / k_trips if k_trips > 0 else 0
        k_l1_profit = k_net_rev - k_l1_cost
        k_l1_pct    = k_l1_profit / k_net_rev * 100 if k_net_rev > 0 else 0
        k_tpvd      = (k_trips / 7) / k_dv if k_dv > 0 else 0
        k_nrpvd     = (k_net_rev / 7) / k_dv if k_dv > 0 else 0

        trend_kr_fare.append(round(k_fare, 2))
        trend_kr_l1pct.append(round(k_l1_pct, 1))
        trend_kr_tpvd.append(round(k_tpvd, 2))
        trend_kr_nrpvd.append(round(k_nrpvd, 2))

    def render_trend(weeks, values, label, kr_avgs=None, fmt="num"):
        df = pd.DataFrame({"Week": weeks, label: values})

        wow_list = [None]
        for i in range(1, len(values)):
            prev = values[i-1]
            wow_list.append(round((values[i]-prev)/abs(prev)*100, 1) if prev else None)
        df["WoW"] = [f"{'+' if w and w>0 else ''}{w}%" if w is not None else "-" for w in wow_list]

        if kr_avgs is not None:
            diff_list = []
            for v, k in zip(values, kr_avgs):
                d = v - k
                p = (d / abs(k) * 100) if k else 0
                sign = "+" if d >= 0 else ""
                if fmt == "pct":
                    diff_list.append(f"{sign}{d:.1f}%p ({sign}{p:.1f}%)")
                else:
                    diff_list.append(f"{sign}{d:.2f} ({sign}{p:.1f}%)")
            df["vs KR"] = diff_list

            if fmt == "money":
                df["KR avg"] = [f"${k:.2f}" for k in kr_avgs]
            elif fmt == "pct":
                df["KR avg"] = [f"{k:.1f}%" for k in kr_avgs]
            else:
                df["KR avg"] = [f"{k:.2f}" for k in kr_avgs]
            tooltip_fields = [
                alt.Tooltip("Week:N", title="Week"),
                alt.Tooltip(f"{label}:Q", title=label, format=".2f"),
                alt.Tooltip("WoW:N", title="WoW"),
                alt.Tooltip("KR avg:N", title="KR avg"),
                alt.Tooltip("vs KR:N", title="vs KR avg"),
            ]
        else:
            tooltip_fields = [
                alt.Tooltip("Week:N", title="Week"),
                alt.Tooltip(f"{label}:Q", title=label, format=".2f"),
                alt.Tooltip("WoW:N", title="WoW"),
            ]

        main_line = alt.Chart(df).mark_line(point=True, color="#1F3864").encode(
            x=alt.X("Week:N", sort=None, axis=alt.Axis(labelAngle=0), title=None),
            y=alt.Y(f"{label}:Q", scale=alt.Scale(zero=False, padding=10), title=None),
            tooltip=tooltip_fields
        )

        if kr_avgs is not None:
            df_kr = pd.DataFrame({"Week": weeks, "KR_line": kr_avgs})
            kr_line = alt.Chart(df_kr).mark_line(
                color="#bbbbbb", strokeDash=[4, 3], strokeWidth=2
            ).encode(
                x=alt.X("Week:N", sort=None),
                y=alt.Y("KR_line:Q"),
                tooltip=[alt.Tooltip("KR_line:Q", title="KR avg", format=".2f")]
            )
            chart = (kr_line + main_line).properties(height=180)
        else:
            chart = main_line.properties(height=180)

        with st.container(border=True):
            st.markdown(f'<div style="font-size:13px;font-weight:700;color:#1a1a2e;margin-bottom:4px;">{label}</div>', unsafe_allow_html=True)
            st.altair_chart(chart, use_container_width=True)
            
    _is_country = (selected_city == "Country")

    tcol1, tcol2, tcol3, tcol4 = st.columns(4)
    with tcol1: render_trend(trend_weeks, trend_fare, "Net Avg Fare", kr_avgs=None if _is_country else trend_kr_fare, fmt="money")
    with tcol2: render_trend(trend_weeks, trend_tpvd, "TPVD", kr_avgs=None if _is_country else trend_kr_tpvd, fmt="num")
    with tcol3: render_trend(trend_weeks, trend_nrpvd, "NRPVD", kr_avgs=None if _is_country else trend_kr_nrpvd, fmt="money")
    with tcol4: render_trend(trend_weeks, trend_l1pct, "L1 %", kr_avgs=None if _is_country else trend_kr_l1pct, fmt="pct")
    
# ══════════════════════════════════════════════════════
# STEP 1. GLIDE
# ══════════════════════════════════════════════════════
st.markdown("---")
st.markdown('<div style="background:#1B2A3B;color:white;padding:10px 18px;border-radius:8px;font-weight:600;margin:60px 0 16px;">STEP 1. Glide Settings</div>', unsafe_allow_html=True)

opz_list = sorted(df_glide_opz["region_name"].unique().tolist()) if not df_glide_opz.empty else []

if opz_list:
    cur_glide_day   = get_city_glide_pct(df_glide_opz, "DAY")
    cur_glide_night = get_city_glide_pct(df_glide_opz, "NIGHT")

    df_day_all   = df_glide_opz[df_glide_opz["timeofday"]=="DAY"]
    df_night_all = df_glide_opz[df_glide_opz["timeofday"]=="NIGHT"]
    city_day_total   = int(df_day_all["total_trips"].sum())
    city_night_total = int(df_night_all["total_trips"].sum())
    city_day_glide   = int(df_day_all["glidesum"].sum())
    city_night_glide = int(df_night_all["glidesum"].sum())
    city_total_glide = city_day_glide + city_night_glide
    city_total_all   = city_day_total + city_night_total
    city_total_pct   = round(city_total_glide / city_total_all * 100, 1) if city_total_all > 0 else 0

    summary_placeholder = st.container()

    st.markdown("<div style='margin-top:20px;margin-bottom:16px;font-size:17px;font-weight:600;border-left:4px solid #1F3864;padding-left:12px;'>⏱ OPZ Glide Time Limit Settings</div>", unsafe_allow_html=True)

    opz_hour_limits = {}
    num_cols = min(len(opz_list), 3)
    opz_col_list = st.columns(num_cols)

    for i, opz in enumerate(opz_list):
        col = opz_col_list[i % num_cols]
        day_row   = df_glide_opz[(df_glide_opz["region_name"]==opz) & (df_glide_opz["timeofday"]=="DAY")]
        night_row = df_glide_opz[(df_glide_opz["region_name"]==opz) & (df_glide_opz["timeofday"]=="NIGHT")]

        day_glide   = int(day_row["glidesum"].sum())
        day_total   = int(day_row["total_trips"].sum())
        night_glide = int(night_row["glidesum"].sum())
        night_total = int(night_row["total_trips"].sum())
        total_glide = day_glide + night_glide
        total_all   = day_total + night_total
        day_g_pct   = day_glide / day_total * 100     if day_total > 0   else 0
        night_g_pct = night_glide / night_total * 100 if night_total > 0 else 0
        total_cur_pct = round(total_glide / total_all * 100, 1) if total_all > 0 else 0

        max_glide_min = get_opz_max_glide(df_opz_list, selected_city, opz)

        if max_glide_min <= 10:
            col.markdown(
                "<div style='background:#f8f9fa;border:1px solid #e0e0e0;border-radius:8px;"
                "padding:6px 12px;margin-bottom:-50px;display:inline-block;font-weight:600;font-size:16px;'>"
                + opz + "<span style='font-size:11px;color:#888;font-weight:400;'> / Current: " + str(max_glide_min) + "min</span></div>",
                unsafe_allow_html=True
            )
            minute_options = [0, 10]
            minute_limit = col.select_slider(
                "",
                options=minute_options,
                value=10,
                key=f"opz_min_{i}",
                format_func=lambda x: "OFF" if x == 0 else "No Change"
            )

        elif max_glide_min <= 60:
            col.markdown(
                "<div style='background:#f8f9fa;border:1px solid #e0e0e0;border-radius:8px;"
                "padding:6px 12px;margin-bottom:-50px;display:inline-block;font-weight:600;font-size:16px;'>"
                + opz + "<span style='font-size:11px;color:#888;font-weight:400;margin-left:8px;'>/ Current: " + str(max_glide_min) + "min</span></div>", unsafe_allow_html=True
            )
            minute_options = [0, 10, 20, 30, 40, 50, 60]
            minute_limit = col.select_slider(
                "",
                options=minute_options,
                value=max_glide_min,
                key=f"opz_min_{i}",
                format_func=lambda x: "OFF" if x == 0 else (f"{x}min" if x < max_glide_min else "No Change")
            )
        else:
            col.markdown(
                "<div style='background:#f8f9fa;border:1px solid #e0e0e0;border-radius:8px;"
                "padding:6px 12px;margin-bottom:-50px;display:inline-block;font-weight:600;font-size:16px;'>"
                + opz + "<span style='font-size:11px;color:#888;font-weight:400;margin-left:8px;'>/ Current: " + str(max_glide_min) + "min</span></div>", unsafe_allow_html=True
            )
            minute_options = [0, 10, 20, 30, 40, 50, 60, 120, 240, 360, 480, 600, 720]
            minute_limit = col.select_slider(
                "",
                options=minute_options,
                value=720,
                key=f"opz_min_{i}",
                format_func=lambda x: (
                    "OFF" if x == 0 else
                    f"{x}min" if x <= 60 else
                    f"{x//60}h" if x < 720 else
                    "No Change"
                )
            )

        opz_hour_limits[opz] = minute_limit

        if minute_limit == 0:
            hour_info      = "OFF"
            info_color     = "#E24B4A"
            prop_total_pct = 0.0
        elif minute_limit == max_glide_min or minute_limit == 720:
            hour_info      = ""
            info_color     = "#888"
            prop_total_pct = total_cur_pct
        else:
            within_pct     = get_glide_hour_pct(df_glide_hour, selected_city, opz, minute_limit)
            hour_info      = ("→ " + str(int(round(within_pct, 0))) + "% retained") if within_pct is not None else ""
            info_color     = "#E07B00"
            ratio          = (within_pct / 100) if within_pct is not None else 1.0
            prop_total_pct = round(total_cur_pct * ratio, 1)

        total_delta       = prop_total_pct - total_cur_pct
        total_delta_color = "#E24B4A" if total_delta < 0 else "#1D9E75"

        box_html = build_opz_box(
            total_cur_pct, total_glide, total_all,
            day_g_pct, night_g_pct,
            day_glide, day_total, night_glide, night_total,
            total_delta, total_delta_color, prop_total_pct,
            hour_info, info_color
        )
        col.markdown(box_html, unsafe_allow_html=True)

    def get_proposed_glide_pct(df_glide_opz, df_glide_hour, timeofday, opz_hour_limits, city, df_opz_list):
        try:
            df_tod = df_glide_opz[df_glide_opz["timeofday"].str.strip() == timeofday]
            total_trips = df_tod["total_trips"].sum()
            if total_trips == 0:
                return 0
            glide_trips = 0
            for opz, minute_limit in opz_hour_limits.items():
                opz_row = df_tod[df_tod["region_name"] == opz]
                if opz_row.empty:
                    continue
                opz_glide = opz_row["glidesum"].sum()
                max_glide_min = get_opz_max_glide(df_opz_list, city, opz)
                if minute_limit == 0:
                    opz_glide = 0
                elif minute_limit == max_glide_min or minute_limit == 720:
                    pass
                else:
                    within_pct = get_glide_hour_pct(df_glide_hour, city, opz, minute_limit)
                    if within_pct is not None:
                        opz_glide = opz_glide * (within_pct / 100)
                glide_trips += opz_glide
            return round(glide_trips / total_trips * 100, 2)
        except:
            return 0

    prop_glide_day   = get_proposed_glide_pct(df_glide_opz, df_glide_hour, "DAY",   opz_hour_limits, selected_city, df_opz_list)
    prop_glide_night = get_proposed_glide_pct(df_glide_opz, df_glide_hour, "NIGHT", opz_hour_limits, selected_city, df_opz_list)

    day_delta_val    = prop_glide_day - cur_glide_day
    day_delta_color  = "#E24B4A" if day_delta_val < 0 else "#1D9E75"
    day_delta_bg     = "#ffebee" if day_delta_val < 0 else "#e8f5e9"
    day_delta_border = "#e57373" if day_delta_val < 0 else "#81c784"
    day_prop_color   = "#1D9E75" if day_delta_val != 0 else "#1a1a2e"

    night_delta_val    = prop_glide_night - cur_glide_night
    night_delta_color  = "#E24B4A" if night_delta_val < 0 else "#1D9E75"
    night_delta_bg     = "#ffebee" if night_delta_val < 0 else "#e8f5e9"
    night_delta_border = "#e57373" if night_delta_val < 0 else "#81c784"
    night_prop_color   = "#7F77DD" if night_delta_val != 0 else "#1a1a2e"

    prop_total_glide_pct   = round((prop_glide_day * city_day_total + prop_glide_night * city_night_total) / city_total_all, 1) if city_total_all > 0 else 0
    prop_total_delta       = prop_total_glide_pct - city_total_pct
    prop_total_delta_color = "#E24B4A" if prop_total_delta < 0 else "#1D9E75"
    prop_total_sign        = "+" if prop_total_delta > 0 else ""

    with summary_placeholder.container():
        col_cur, col_prop = st.columns(2)
        col_cur.markdown(f"""<div style="background:#f8f9fa;border:1px solid #e0e0e0;border-radius:10px;padding:12px 16px;text-align:center;">
    <div style="margin-bottom:12px;">
        <div style="font-size:14px;font-weight:600;color:#1a1a2e;margin-bottom:4px;">Current</div>
        <div style="font-size:32px;font-weight:700;color:#1a1a2e;">{city_total_pct:.1f}%</div>
        <div style="font-size:13px;color:#555;margin-top:2px;">{city_total_glide:,} / {city_total_all:,}</div>
    </div>
    <div style="width:100%;height:1px;background:#ddd;margin-bottom:12px;"></div>
    <div style="display:flex;gap:48px;justify-content:center;">
        <div>
            <div style="font-size:14px;font-weight:600;color:#1D9E75;margin-bottom:4px;">DAY</div>
            <div style="font-size:26px;font-weight:700;color:#1D9E75;">{cur_glide_day:.1f}%</div>
            <div style="font-size:13px;color:#555;margin-top:2px;">{city_day_glide:,} / {city_day_total:,}</div>
        </div>
        <div style="width:1px;background:#ddd;"></div>
        <div>
            <div style="font-size:14px;font-weight:600;color:#7F77DD;margin-bottom:4px;">NIGHT</div>
            <div style="font-size:26px;font-weight:700;color:#7F77DD;">{cur_glide_night:.1f}%</div>
            <div style="font-size:13px;color:#555;margin-top:2px;">{city_night_glide:,} / {city_night_total:,}</div>
        </div>
    </div>
</div>""", unsafe_allow_html=True)

        col_prop.markdown("<div style='background:#f0f7ff;border:1px solid #c0d8f0;border-radius:10px;padding:12px 16px;text-align:center;'>"
            "<div style='margin-bottom:12px;'>"
            "<div style='font-size:14px;font-weight:600;color:#1a1a2e;margin-bottom:4px;'>Proposed</div>"
            "<div style='font-size:32px;font-weight:700;color:#1a1a2e;'>" + str(round(prop_total_glide_pct, 1)) + "%</div>"
            "<div style='font-size:13px;font-weight:600;color:" + prop_total_delta_color + ";margin-top:2px;'>" + prop_total_sign + str(round(prop_total_delta, 1)) + "%p</div>"
            "</div>"
            "<div style='width:100%;height:1px;background:#ddd;margin-bottom:12px;'></div>"
            "<div style='display:flex;gap:48px;justify-content:center;'>"
            "<div>"
            "<div style='font-size:14px;font-weight:600;color:#1D9E75;margin-bottom:4px;'>DAY</div>"
            "<div style='font-size:26px;font-weight:700;color:" + day_prop_color + ";'>" + str(round(prop_glide_day, 1)) + "%</div>"
            "<div style='display:inline-block;background:" + day_delta_bg + ";border:1px solid " + day_delta_border + ";border-radius:6px;padding:2px 8px;font-size:12px;font-weight:600;color:" + day_delta_color + ";margin-top:4px;'>" + ("+" if day_delta_val > 0 else "") + str(round(day_delta_val, 1)) + "%p</div>"
            "</div>"
            "<div style='width:1px;background:#ddd;'></div>"
            "<div>"
            "<div style='font-size:14px;font-weight:600;color:#7F77DD;margin-bottom:4px;'>NIGHT</div>"
            "<div style='font-size:26px;font-weight:700;color:" + night_prop_color + ";'>" + str(round(prop_glide_night, 1)) + "%</div>"
            "<div style='display:inline-block;background:" + night_delta_bg + ";border:1px solid " + night_delta_border + ";border-radius:6px;padding:2px 8px;font-size:12px;font-weight:600;color:" + night_delta_color + ";margin-top:4px;'>" + ("+" if night_delta_val > 0 else "") + str(round(night_delta_val, 1)) + "%p</div>"
            "</div>"
            "</div>"
            "</div>", unsafe_allow_html=True)

else:
    st.info(f"{selected_city} | {selected_week} Glide 데이터가 없습니다.")
    cur_glide_day = cur_glide_night = prop_glide_day = prop_glide_night = 0
    opz_hour_limits = {}

# ══════════════════════════════════════════════════════
# STEP 2. 가격 변경 (OPZ별 분리)  [전면 수정]
# ══════════════════════════════════════════════════════
st.markdown('<div style="background:#1B2A3B;color:white;padding:10px 18px;border-radius:8px;font-weight:600;margin:60px 0 16px;">STEP 2. Pricing Settings</div>', unsafe_allow_html=True)

prop_price_by_opz = {}  # { opz: {ppu_day, ppm_day, ppu_night, ppm_night} }

# ── 도시 단위 박스 (Price 시트 opz 빈 행 기준, 예전 단순 로직) ──
st.markdown("<div style='margin-bottom:10px;font-size:19px;font-weight:700;'>City-wide</div>", unsafe_allow_html=True)

if city_price_row is not None:
    with st.expander(f"📍 **{selected_city}**", expanded=False):
        pc1, pc2 = st.columns(2)
        with pc1:
            st.markdown('<div style="background:#e8f5e9;border-left:4px solid #1D9E75;padding:8px 14px;border-radius:6px;font-weight:600;color:#1a1a2e;margin-bottom:12px;">☀️ DAY (06:00~23:59)</div>', unsafe_allow_html=True)
            c1, c2 = st.columns(2)
        with c1:
            st.caption("Current")
            st.text_input("PPU", value=f"{city_price_row['ppu_day']:.0f}", disabled=True, key=f"ppu_d_c_{selected_city}_city")
            st.text_input("PPM", value=f"{city_price_row['ppm_day']:.0f}", disabled=True, key=f"ppm_d_c_{selected_city}_city")
            st.text_input("Subs Free Unlock %", value=f"{subs_day:.1f}%" if subs_day is not None else "-", disabled=True, key=f"sub_d_c_{selected_city}_city")
            st.text_input("DAY Trip %", value=f"{day_pct:.1f}%" if day_pct is not None else "-", disabled=True, key=f"day_pct_c_{selected_city}_city")
        with c2:
            st.caption("Proposed")
            city_prop_ppu_day = st.number_input("PPU", value=int(city_price_row['ppu_day']), step=10, key=f"ppu_d_p_{selected_city}_city")
            city_prop_ppm_day = st.number_input("PPM", value=int(city_price_row['ppm_day']), step=10, key=f"ppm_d_p_{selected_city}_city")

        with pc2:
            st.markdown('<div style="background:#ede7f6;border-left:4px solid #7F77DD;padding:8px 14px;border-radius:6px;font-weight:600;color:#1a1a2e;margin-bottom:12px;">🌙 NIGHT (00:00~05:59)</div>', unsafe_allow_html=True)
            c1, c2 = st.columns(2)
        with c1:
            st.caption("Current")
            st.text_input("PPU", value=f"{city_price_row['ppu_night']:.0f}", disabled=True, key=f"ppu_n_c_{selected_city}_city")
            st.text_input("PPM", value=f"{city_price_row['ppm_night']:.0f}", disabled=True, key=f"ppm_n_c_{selected_city}_city")
            st.text_input("Subs Free Unlock %", value=f"{subs_night:.1f}%" if subs_night is not None else "-", disabled=True, key=f"sub_n_c_{selected_city}_city")
            st.text_input("NIGHT Trip %", value=f"{night_pct:.1f}%" if night_pct is not None else "-", disabled=True, key=f"ngt_pct_c_{selected_city}_city")
        with c2:
            st.caption("Proposed")
            city_prop_ppu_night = st.number_input("PPU", value=int(city_price_row['ppu_night']), step=10, key=f"ppu_n_p_{selected_city}_city")
            city_prop_ppm_night = st.number_input("PPM", value=int(city_price_row['ppm_night']), step=10, key=f"ppm_n_p_{selected_city}_city")
else:
    st.info("No city-level pricing data (OPZ blank row)")
    city_prop_ppu_day = city_prop_ppm_day = city_prop_ppu_night = city_prop_ppm_night = 0

st.markdown("<div style='margin:18px 0 10px;font-size:19px;font-weight:700;'>By OPZ</div>", unsafe_allow_html=True)

if price_opz_list:
    for opz in price_opz_list:
        cur_p = price_by_opz[opz]
        opz_day_weight   = get_opz_trip_weight(df_glide_opz, opz, "DAY")
        opz_night_weight = get_opz_trip_weight(df_glide_opz, opz, "NIGHT")

         # 이 OPZ 내부에서 DAY/NIGHT가 차지하는 비율 (도시 전체값 아님)
        opz_day_total_trips   = df_glide_opz[(df_glide_opz["region_name"]==opz) & (df_glide_opz["timeofday"]=="DAY")]["total_trips"].sum()
        opz_night_total_trips = df_glide_opz[(df_glide_opz["region_name"]==opz) & (df_glide_opz["timeofday"]=="NIGHT")]["total_trips"].sum()
        opz_total_trips = opz_day_total_trips + opz_night_total_trips
        opz_internal_day_pct   = round(opz_day_total_trips / opz_total_trips * 100, 1)   if opz_total_trips > 0 else 0
        opz_internal_night_pct = round(opz_night_total_trips / opz_total_trips * 100, 1) if opz_total_trips > 0 else 0
        city_total_all_trips = df_glide_opz["total_trips"].sum()
        opz_total_weight = round(opz_total_trips / city_total_all_trips * 100, 1) if         city_total_all_trips > 0 else 0

        with st.expander(f"📍 **{opz}**  ·  Total {opz_total_weight:.1f}% (DAY {opz_day_weight:.1f}% | NIGHT {opz_night_weight:.1f}%)", expanded=False):
            pc1, pc2 = st.columns(2)
            with pc1:
                st.markdown('<div style="background:#e8f5e9;border-left:4px solid #1D9E75;padding:8px 14px;border-radius:6px;font-weight:600;color:#1a1a2e;margin-bottom:12px;">☀️ DAY (06:00~23:59)</div>', unsafe_allow_html=True)
                c1, c2 = st.columns(2)
            with c1:
                st.caption("Current")
                st.text_input("PPU", value=f"{cur_p['ppu_day']:.0f}", disabled=True, key=f"ppu_d_c_{selected_city}_{opz}")
                st.text_input("PPM", value=f"{cur_p['ppm_day']:.0f}", disabled=True, key=f"ppm_d_c_{selected_city}_{opz}")
                st.text_input("DAY Trip % (OPZ 내)", value=f"{opz_internal_day_pct:.1f}%", disabled=True, key=f"day_pct_c_{selected_city}_{opz}")
            with c2:
                st.caption("Proposed")
                p_ppu_day = st.number_input("PPU", value=int(cur_p['ppu_day']), step=10, key=f"ppu_d_p_{selected_city}_{opz}")
                p_ppm_day = st.number_input("PPM", value=int(cur_p['ppm_day']), step=10, key=f"ppm_d_p_{selected_city}_{opz}")

            with pc2:
                st.markdown('<div style="background:#ede7f6;border-left:4px solid #7F77DD;padding:8px 14px;border-radius:6px;font-weight:600;color:#1a1a2e;margin-bottom:12px;">🌙 NIGHT (00:00~05:59)</div>', unsafe_allow_html=True)
                c1, c2 = st.columns(2)
            with c1:
                st.caption("Current")
                st.text_input("PPU", value=f"{cur_p['ppu_night']:.0f}", disabled=True, key=f"ppu_n_c_{selected_city}_{opz}")
                st.text_input("PPM", value=f"{cur_p['ppm_night']:.0f}", disabled=True, key=f"ppm_n_c_{selected_city}_{opz}")
                st.text_input("NIGHT Trip % (OPZ 내)", value=f"{opz_internal_night_pct:.1f}%", disabled=True, key=f"ngt_pct_c_{selected_city}_{opz}")
            with c2:
                st.caption("Proposed")
                p_ppu_night = st.number_input("PPU", value=int(cur_p['ppu_night']), step=10, key=f"ppu_n_p_{selected_city}_{opz}")
                p_ppm_night = st.number_input("PPM", value=int(cur_p['ppm_night']), step=10, key=f"ppm_n_p_{selected_city}_{opz}")

        prop_price_by_opz[opz] = {
            "ppu_day": p_ppu_day, "ppm_day": p_ppm_day,
            "ppu_night": p_ppu_night, "ppm_night": p_ppm_night,
        }
else:
    st.info(f"No pricing data for {selected_city}")

# ══════════════════════════════════════════════════════
# CALCULATION
#  - City-wide 계산: 예전 단순 로직 (단일 PPU/PPM)
#  - OPZ별 계산: OPZ별 blended (Subs%는 도시 전체 공통값)
#  - 우선순위: OPZ가 하나라도 바뀌면 OPZ 계산이 최종값으로 사용됨.
#              City-wide도 같이 바뀌었으면 OPZ가 우선하고 City-wide 변경은 무시.
# ══════════════════════════════════════════════════════
def gross_fare_krw(ppu, ppm, dur, glide_pct, subs_pct):
    return ppu * (1 - glide_pct/100 - subs_pct/100) + ppm * dur

glide_changed = (prop_glide_day != cur_glide_day) or (prop_glide_night != cur_glide_night)

# ── City-wide 계산 (예전 로직) ──
city_changed = False
city_pricing_change_rate = 0
if city_price_row is not None:
    city_changed = (
        city_prop_ppu_day   != city_price_row['ppu_day']   or
        city_prop_ppm_day   != city_price_row['ppm_day']   or
        city_prop_ppu_night != city_price_row['ppu_night'] or
        city_prop_ppm_night != city_price_row['ppm_night']
    )

    _city_day_total   = city_day_total if opz_list else 0
    _city_night_total = city_night_total if opz_list else 0
    _city_total_trips = _city_day_total + _city_night_total
    _city_day_w   = _city_day_total / _city_total_trips if _city_total_trips > 0 else (day_pct_calc/100)
    _city_night_w = _city_night_total / _city_total_trips if _city_total_trips > 0 else (night_pct_calc/100)

    city_cur_fare_krw = (
        gross_fare_krw(city_price_row['ppu_day'],   city_price_row['ppm_day'],   cur_duration, cur_glide_day,   subs_day)   * _city_day_w +
        gross_fare_krw(city_price_row['ppu_night'], city_price_row['ppm_night'], cur_duration, cur_glide_night, subs_night) * _city_night_w
    )
    city_prop_fare_krw = (
        gross_fare_krw(city_prop_ppu_day,   city_prop_ppm_day,   cur_duration, prop_glide_day,   subs_day)   * _city_day_w +
        gross_fare_krw(city_prop_ppu_night, city_prop_ppm_night, cur_duration, prop_glide_night, subs_night) * _city_night_w
    )
    
    city_pricing_change_rate = (city_prop_fare_krw - city_cur_fare_krw) / city_cur_fare_krw if city_cur_fare_krw > 0 else 0



# ── OPZ별 계산 ──
opz_cur_fare_krw  = 0
opz_prop_fare_krw = 0
opz_change_detail = {}  # { opz: {ppu_day_chg, ppm_day_chg, ppu_night_chg, ppm_night_chg, day_weight, night_weight, ppu_changed, ppm_changed} }

for opz in price_opz_list:
    cur_p  = price_by_opz[opz]
    prop_p = prop_price_by_opz[opz]

    opz_day_glide   = df_glide_opz[(df_glide_opz["region_name"]==opz) & (df_glide_opz["timeofday"]=="DAY")]
    opz_night_glide = df_glide_opz[(df_glide_opz["region_name"]==opz) & (df_glide_opz["timeofday"]=="NIGHT")]
    opz_day_total   = opz_day_glide["total_trips"].sum()
    opz_night_total = opz_night_glide["total_trips"].sum()
    opz_day_glidesum   = opz_day_glide["glidesum"].sum()
    opz_night_glidesum = opz_night_glide["glidesum"].sum()
    opz_cur_glide_day   = round(opz_day_glidesum / opz_day_total * 100, 2)   if opz_day_total > 0   else 0
    opz_cur_glide_night = round(opz_night_glidesum / opz_night_total * 100, 2) if opz_night_total > 0 else 0

    minute_limit  = opz_hour_limits.get(opz, 720)
    max_glide_min = get_opz_max_glide(df_opz_list, selected_city, opz)
    if minute_limit == 0:
        opz_prop_glide_day = 0
        opz_prop_glide_night = 0
    elif minute_limit == max_glide_min or minute_limit == 720:
        opz_prop_glide_day = opz_cur_glide_day
        opz_prop_glide_night = opz_cur_glide_night
    else:
        within_pct = get_glide_hour_pct(df_glide_hour, selected_city, opz, minute_limit)
        ratio = (within_pct / 100) if within_pct is not None else 1.0
        opz_prop_glide_day = round(opz_cur_glide_day * ratio, 2)
        opz_prop_glide_night = round(opz_cur_glide_night * ratio, 2)

    city_grand_total_trips = df_glide_opz["total_trips"].sum()
    day_weight   = opz_day_total / city_grand_total_trips   if city_grand_total_trips > 0 else 0
    night_weight = opz_night_total / city_grand_total_trips if city_grand_total_trips > 0 else 0
    
    opz_cur_fare_krw += (
        gross_fare_krw(cur_p['ppu_day'],   cur_p['ppm_day'],   cur_duration, opz_cur_glide_day,   subs_day)   * day_weight +
        gross_fare_krw(cur_p['ppu_night'], cur_p['ppm_night'], cur_duration, opz_cur_glide_night, subs_night) * night_weight
    )
    opz_prop_fare_krw += (
        gross_fare_krw(prop_p['ppu_day'],   prop_p['ppm_day'],   cur_duration, opz_prop_glide_day,   subs_day)   * day_weight +
        gross_fare_krw(prop_p['ppu_night'], prop_p['ppm_night'], cur_duration, opz_prop_glide_night, subs_night) * night_weight
    )

    opz_change_detail[opz] = {
        "ppu_day_chg":   (prop_p['ppu_day']   - cur_p['ppu_day'])   / cur_p['ppu_day']   * 100 if cur_p['ppu_day']   > 0 else 0,
        "ppm_day_chg":   (prop_p['ppm_day']   - cur_p['ppm_day'])   / cur_p['ppm_day']   * 100 if cur_p['ppm_day']   > 0 else 0,
        "ppu_night_chg": (prop_p['ppu_night'] - cur_p['ppu_night']) / cur_p['ppu_night'] * 100 if cur_p['ppu_night'] > 0 else 0,
        "ppm_night_chg": (prop_p['ppm_night'] - cur_p['ppm_night']) / cur_p['ppm_night'] * 100 if cur_p['ppm_night'] > 0 else 0,
        "day_weight":    day_weight,
        "night_weight":  night_weight,
        "ppu_changed":   (prop_p['ppu_day'] != cur_p['ppu_day']) or (prop_p['ppu_night'] != cur_p['ppu_night']),
        "ppm_changed":   (prop_p['ppm_day'] != cur_p['ppm_day']) or (prop_p['ppm_night'] != cur_p['ppm_night']),
    }

opz_any_changed = any(v["ppu_changed"] or v["ppm_changed"] for v in opz_change_detail.values()) if opz_change_detail else False
opz_pricing_change_rate = (opz_prop_fare_krw - opz_cur_fare_krw) / opz_cur_fare_krw if opz_cur_fare_krw > 0 else 0

# ── 우선순위: OPZ가 바뀌었으면 OPZ 계산 사용, 아니면 City-wide 계산 사용 ──
if opz_any_changed:
    pricing_change_rate = opz_pricing_change_rate
    price_source = "opz"
elif city_changed:
    pricing_change_rate = city_pricing_change_rate
    price_source = "city"
elif glide_changed:
    pricing_change_rate = opz_pricing_change_rate if opz_change_detail else city_pricing_change_rate
    price_source = "opz" if opz_change_detail else "city"
else:
    pricing_change_rate = 0
    price_source = "none"
    
prop_net_avg_fare = cur_net_avg_fare * (1 + pricing_change_rate)

if opz_any_changed and city_changed:
    st.markdown(
        "<div style='background:#fff3e0;border:1px solid #ffb74d;border-radius:6px;"
        "padding:8px 14px;margin:8px 0;font-size:13px;color:#e65100;'>"
        "⚠️ City-wide와 OPZ 가격이 동시에 변경되었습니다. <b>OPZ별 변경값이 우선 적용</b>되며 City-wide 변경분은 무시됩니다."
        "</div>",
        unsafe_allow_html=True
    )

# ══════════════════════════════════════════════════════
# SIMULATION RESULT
# ══════════════════════════════════════════════════════
st.markdown("---")
st.markdown('<div class="result-header">📊 Simulation Result</div>', unsafe_allow_html=True)
  
glide_changed = (prop_glide_day != cur_glide_day) or (prop_glide_night != cur_glide_night)
price_changed = opz_any_changed or city_changed
ppu_changed   = (any(v["ppu_changed"] for v in opz_change_detail.values()) if opz_change_detail else False) or \
                (city_changed and city_price_row is not None and (city_prop_ppu_day != city_price_row['ppu_day'] or city_prop_ppu_night != city_price_row['ppu_night']))
ppm_changed   = (any(v["ppm_changed"] for v in opz_change_detail.values()) if opz_change_detail else False) or \
                (city_changed and city_price_row is not None and (city_prop_ppm_day != city_price_row['ppm_day'] or city_prop_ppm_night != city_price_row['ppm_night']))

if glide_changed and price_changed:
    effect_title = "Glide & Pricing Impact"
elif glide_changed:
    effect_title = "Glide Impact"
elif price_changed:
    effect_title = "Pricing Impact"
else:
    effect_title = "Baseline"

st.markdown(f'<div class="sub-step-header">STEP 1 · {effect_title}</div>', unsafe_allow_html=True)

d_fare    = prop_net_avg_fare - cur_net_avg_fare
pct_fare  = d_fare / cur_net_avg_fare * 100 if cur_net_avg_fare != 0 else 0
sign_fare = "+" if d_fare >= 0 else ""
cls_fare  = "delta-pos" if d_fare > 0 else ("delta-neg" if d_fare < 0 else "delta-neu")

st.markdown(f"""<div class="result-card" style="padding:20px 24px;max-width:500px;">
    <div class="label">Net Avg Fare (USD)</div>
    <div style="display:flex;align-items:flex-end;gap:20px;margin-top:6px;flex-wrap:wrap;">
        <div>
            <div style="font-size:11px;color:#999;margin-bottom:2px;">Current</div>
            <div style="font-size:22px;font-weight:600;color:#888;">${cur_net_avg_fare:.2f}</div>
        </div>
        <div style="font-size:22px;color:#ccc;padding-bottom:4px;">→</div>
        <div>
            <div style="font-size:11px;color:#999;margin-bottom:2px;">Proposed</div>
            <div style="font-size:28px;font-weight:700;color:#1a1a2e;">${prop_net_avg_fare:.2f}</div>
        </div>
        <div style="padding-bottom:6px;">
            <span class="{cls_fare}" style="font-size:18px;">{sign_fare}{pct_fare:.1f}%</span>
        </div>
    </div>
</div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════
# STEP 2 · Trip Decline Scenario
# ══════════════════════════════════════════════════════
st.markdown('<div class="sub-step-header">STEP 2 · Trip Decline Scenario</div>', unsafe_allow_html=True)

if price_changed:
    st.markdown("**📊 Price Sensitivity Settings**",
        help="Estimated trip change rate per 1% fare increase (e.g., -0.5 = fare +1% → approx. trips -0.5%)")

    sensitivity_options = {
        "🟢 Low (-0.3)": (-0.5, -0.1),
        "🟡 Medium (-0.5)": (-0.8, -0.3),
        "🔴 High (-0.7)": (-1.2, -0.5),
    }
    selected_sensitivity = st.radio(
        "Quick Select",
        options=list(sensitivity_options.keys()),
        captions=[
            "Commute-Focused · Fixed destinations, limited alternatives",
            "Mixed-Use · Blend of commuting and daily trips",
            "Leisure-Focused · More alternatives, highly price-sensitive",
        ],
        index=1,
        horizontal=True,
    )
    default_ppu_e, default_ppm_e = sensitivity_options[selected_sensitivity]

    col_e1, col_e2 = st.columns(2)
    with col_e1:
        ppu_elasticity = st.number_input(
            "PPU Elasticity",
            value=float(default_ppu_e),
            min_value=-3.0,
            max_value=0.0,
            step=0.1,
            format="%.1f",
            key=f"ppu_e_{selected_sensitivity}",
        )
    with col_e2:
        ppm_elasticity = st.number_input(
            "PPM Elasticity",
            value=float(default_ppm_e),
            min_value=-3.0,
            max_value=0.0,
            step=0.1,
            format="%.1f",
            key=f"ppm_e_{selected_sensitivity}",
        )
else:
    ppu_elasticity = -0.8
    ppm_elasticity = -0.3
    selected_sensitivity = "🟡 Medium (-0.5)"

# ══════════════════════════════════════════════════════
# PPU/PPM 변화율 가중평균 (elasticity 계산용)
#  - price_source == "opz"  → OPZ별 trip 비중 가중평균
#  - price_source == "city" → City-wide 단일 변화율 그대로 사용
# ══════════════════════════════════════════════════════
ppu_avg_change = 0
ppm_avg_change = 0
cur_ppu_avg = 0
cur_ppm_avg = 0

if price_source == "opz":
    total_weight = sum(v["day_weight"] + v["night_weight"] for v in opz_change_detail.values()) if opz_change_detail else 0
    if total_weight > 0:
        for opz, v in opz_change_detail.items():
            ppu_avg_change += (v["ppu_day_chg"] * v["day_weight"] + v["ppu_night_chg"] * v["night_weight"])
            ppm_avg_change += (v["ppm_day_chg"] * v["day_weight"] + v["ppm_night_chg"] * v["night_weight"])
        ppu_avg_change /= total_weight
        ppm_avg_change /= total_weight
        cur_ppu_avg = sum(price_by_opz[opz]['ppu_day'] * v['day_weight'] + price_by_opz[opz]['ppu_night'] * v['night_weight']
                           for opz, v in opz_change_detail.items()) / total_weight
        cur_ppm_avg = sum(price_by_opz[opz]['ppm_day'] * v['day_weight'] + price_by_opz[opz]['ppm_night'] * v['night_weight']
                           for opz, v in opz_change_detail.items()) / total_weight
elif price_source == "city" and city_price_row is not None:
    ppu_day_chg_c   = (city_prop_ppu_day   - city_price_row['ppu_day'])   / city_price_row['ppu_day']   * 100 if city_price_row['ppu_day']   > 0 else 0
    ppm_day_chg_c   = (city_prop_ppm_day   - city_price_row['ppm_day'])   / city_price_row['ppm_day']   * 100 if city_price_row['ppm_day']   > 0 else 0
    ppu_night_chg_c = (city_prop_ppu_night - city_price_row['ppu_night']) / city_price_row['ppu_night'] * 100 if city_price_row['ppu_night'] > 0 else 0
    ppm_night_chg_c = (city_prop_ppm_night - city_price_row['ppm_night']) / city_price_row['ppm_night'] * 100 if city_price_row['ppm_night'] > 0 else 0
    ppu_avg_change = ppu_day_chg_c * (day_pct_calc/100) + ppu_night_chg_c * (night_pct_calc/100)
    ppm_avg_change = ppm_day_chg_c * (day_pct_calc/100) + ppm_night_chg_c * (night_pct_calc/100)
    cur_ppu_avg = city_price_row['ppu_day'] * (day_pct_calc/100) + city_price_row['ppu_night'] * (night_pct_calc/100)
    cur_ppm_avg = city_price_row['ppm_day'] * (day_pct_calc/100) + city_price_row['ppm_night'] * (night_pct_calc/100)

cur_fare_base = cur_ppu_avg + cur_ppm_avg * cur_duration
ppu_weight = cur_ppu_avg / cur_fare_base if cur_fare_base > 0 else 0.4
ppm_weight = (cur_ppm_avg * cur_duration) / cur_fare_base if cur_fare_base > 0 else 0.6
weighted_elasticity = (ppu_weight * ppu_elasticity) + (ppm_weight * ppm_elasticity)

total_fare_change = (ppu_weight * ppu_avg_change) + (ppm_weight * ppm_avg_change)
price_decline = round(total_fare_change * weighted_elasticity, 1) if price_changed else 0.0
ppu_decline   = round(ppu_avg_change * ppu_elasticity * ppu_weight, 1) if price_changed else 0.0
ppm_decline   = round(ppm_avg_change * ppm_elasticity * ppm_weight, 1) if price_changed else 0.0

def calc_expected_trip_decline(df_glide_opz, df_glide_hour, opz_hour_limits, city, cur_trips, df_opz_list):
    try:
        total_excess_trips = 0
        for opz, minute_limit in opz_hour_limits.items():
            max_glide_min = get_opz_max_glide(df_opz_list, city, opz)
            if minute_limit == max_glide_min or minute_limit == 720:
                continue
            day_row   = df_glide_opz[(df_glide_opz["region_name"]==opz) & (df_glide_opz["timeofday"]=="DAY")]
            night_row = df_glide_opz[(df_glide_opz["region_name"]==opz) & (df_glide_opz["timeofday"]=="NIGHT")]
            opz_glide = day_row["glidesum"].sum() + night_row["glidesum"].sum()
            if minute_limit == 0:
                total_excess_trips += opz_glide
            else:
                within_pct = get_glide_hour_pct(df_glide_hour, city, opz, minute_limit)
                if within_pct is not None:
                    total_excess_trips += opz_glide * (1 - within_pct / 100)
        if cur_trips == 0:
            return None
        return round(total_excess_trips / cur_trips * 100, 1)
    except:
        return None

expected_decline_glide = calc_expected_trip_decline(
    df_glide_opz, df_glide_hour, opz_hour_limits, selected_city, cur_trips, df_opz_list
) if opz_list else None

total_expected_decline = round((expected_decline_glide or 0) + abs(price_decline), 1)

if total_expected_decline > 0:
    parts_list = []
    if (expected_decline_glide or 0) > 0:
        parts_list.append(f"Glide limit -{expected_decline_glide}%")
    if price_decline != 0:
        parts_list.append(f"PPU -{abs(ppu_decline)}% / PPM -{abs(ppm_decline)}%")
    parts = " + ".join(parts_list)
    detail = f" ({parts})" if parts else ""
    st.markdown(
        "<div style='background:#fff8e1;border:1px solid #ffe082;border-radius:8px;"
        "padding:10px 16px;margin-bottom:12px;font-size:13px;'>"
        "⚠️ <b>Estimated Trip Decline: ~" + str(total_expected_decline) + "%</b>"
        "<span style='color:#888;font-size:11px;margin-left:8px;'>" + detail + " based estimate</span>"
        "</div>",
        unsafe_allow_html=True
    )

default_a = -int(round(total_expected_decline)) if total_expected_decline > 0 else -5

if prop_net_avg_fare > 0 and cur_trips > 0:
    breakeven_drop = (cur_net_rev / (prop_net_avg_fare * cur_trips) - 1) * 100
    default_b = max(-15, min(0, int(breakeven_drop) + 1))
else:
    default_b = -3

sc1, sc2, sc3 = st.columns(3)
with sc1:
    trip_drop_a = st.slider("Scenario A (%)", -15, 15, max(-15, min(15, default_a)))
with sc2:
    trip_drop_b = st.slider("Scenario B (%)", -15, 15, default_b)
with sc3:
    trip_drop_c = st.slider("Scenario C (%)", -15, 15, max(-15, min(15, default_b + 5)))

def calc_scenario(drop_pct):
    trips     = cur_trips * (1 + drop_pct/100)
    net_rev   = prop_net_avg_fare * trips
    l1_profit = net_rev - cur_l1_cost
    l1_pct    = l1_profit / net_rev * 100 if net_rev > 0 else 0
    cpt       = cur_l1_cost / trips        if trips > 0  else 0
    tpvd      = (trips / 7) / cur_dv      if cur_dv > 0 else 0
    nrpvd     = (net_rev / 7) / cur_dv    if cur_dv > 0 else 0
    vcd       = l1_profit / cur_dv / 7    if cur_dv > 0 else 0
    return dict(trips=trips, net_rev=net_rev, cpt=cpt,
                tpvd=tpvd, nrpvd=nrpvd, vcd=vcd,
                l1_profit=l1_profit, l1_pct=l1_pct)

s_cur = dict(trips=cur_trips, net_rev=cur_net_rev, cpt=cur_cpt,
             tpvd=cur_tpvd, nrpvd=cur_nrpvd, vcd=cur_vcd,
             l1_profit=cur_l1_profit, l1_pct=cur_l1_pct)
s_a = calc_scenario(trip_drop_a)
s_b = calc_scenario(trip_drop_b)
s_c = calc_scenario(trip_drop_c)

# ══════════════════════════════════════════════════════
# STEP 3 · Result Summary
# ══════════════════════════════════════════════════════
st.markdown('<div class="sub-step-header">STEP 3 · Result Summary</div>', unsafe_allow_html=True)

bullets = []

if glide_changed and price_changed:
    bullets.append(f"Combined Glide restriction and pricing changes increased Net Avg Fare by +{pct_fare:.1f}%")
    if (expected_decline_glide or 0) > 0 and abs(price_decline) > 0:
        bullets.append(f"Glide-driven decline: ~{expected_decline_glide}% / Pricing-driven decline: ~{abs(price_decline):.1f}%<br><span style='font-size:11px;color:#888;'>({selected_sensitivity} · Weighted elasticity: {round(weighted_elasticity, 2)}, trip duration mix applied)</span>")
    bullets.append(f"Total modeled trip decline: ~{total_expected_decline}% (Glide + Pricing combined estimate)")
elif glide_changed:
    bullets.append(f"Glide restriction increased Net Avg Fare by +{pct_fare:.1f}%")
    bullets.append(f"Total modeled trip decline: ~{total_expected_decline}% (Glide-based estimate)")
elif price_changed:
    if ppu_changed and ppm_changed:
        bullets.append(f"Pricing changes increased Net Avg Fare by +{pct_fare:.1f}%")
    elif ppu_changed:
        bullets.append(f"PPU change increased Net Avg Fare by +{pct_fare:.1f}%")
    else:
        bullets.append(f"PPM change increased Net Avg Fare by +{pct_fare:.1f}%")
    bullets.append(
        f"Total modeled trip decline: ~{total_expected_decline}% (Pricing-based estimate)"
        f"<br><span style='font-size:11px;color:#888;'>({selected_sensitivity} · Weighted elasticity: {round(weighted_elasticity, 2)} based on trip duration mix)</span>"
    )
else:
    bullets.append("No changes applied — baseline metrics displayed")

if (glide_changed or price_changed) and prop_net_avg_fare > 0 and cur_trips > 0:
    bk = (cur_net_rev / (prop_net_avg_fare * cur_trips) - 1) * 100
    bk_abs = abs(bk)
    if total_expected_decline > bk_abs:
        bullets.append(f"⚠️ Estimated decline exceeds modeled trip decline threshold (~{bk_abs:.1f}%)")
    else:
        bullets.append(f"Current setup is within modeled trip decline threshold (~{bk_abs:.1f}%)")

bullet_html = "".join([
    f"<div style='display:flex;gap:8px;margin-bottom:6px;'>"
    f"<span style='color:#1F3864;font-weight:700;'>•</span>"
    f"<span style='font-size:13px;color:#1a1a2e;'>{b}</span>"
    f"</div>"
    for b in bullets
])

st.markdown(f"""
<div style="background:#f8f9fa;border:1px solid #e0e0e0;border-radius:10px;padding:16px 20px;margin-bottom:8px;">
    <div style="font-size:13px;font-weight:700;color:#1F3864;margin-bottom:10px;">📌 Result Summary</div>
    {bullet_html}
</div>""", unsafe_allow_html=True)

st.markdown('<div class="sub-step-header">STEP 4 · Scenario Outcomes</div>', unsafe_allow_html=True)

def fmt_scenario_label(val):
    if val == 0:
        return "0%"
    sign = "+" if val > 0 else ""
    return f"{sign}{val}%"

scenario_list = [
    (f"{selected_week} (기준)",                                s_cur),
    (f"Scenario A ({fmt_scenario_label(trip_drop_a)})",        s_a),
    (f"Scenario B ({fmt_scenario_label(trip_drop_b)})",        s_b),
    (f"Scenario C ({fmt_scenario_label(trip_drop_c)})",        s_c),
]

def delta_str(val, fmt="num", is_cur=False):
    if is_cur:
        return ""
    color = "#1a1a2e" if val == 0 else ("#E24B4A" if val < 0 else "#1D9E75")
    sign  = "+" if val > 0 else ""
    if fmt == "money":
        txt = ("+$" if val >= 0 else "-$") + f"{abs(val):,.0f}"
    elif fmt == "pct":
        txt = sign + f"{val:.1f}" + "%p"
    else:
        txt = sign + f"{val:.2f}"
    return '<span style="font-size:11px;color:' + color + ';"> (' + txt + ')</span>'

def delta_str_reverse(val, fmt="num", is_cur=False):
    if is_cur:
        return ""
    color = "#1a1a2e" if val == 0 else ("#1D9E75" if val < 0 else "#E24B4A")
    sign  = "+" if val > 0 else ""
    if fmt == "money":
        txt = ("+$" if val >= 0 else "-$") + f"{abs(val):,.0f}"
    elif fmt == "pct":
        txt = sign + f"{val:.1f}" + "%p"
    else:
        txt = sign + f"{val:.2f}"
    return '<span style="font-size:11px;color:' + color + ';"> (' + txt + ')</span>'

cols = st.columns(4)
for i, (col, (lbl, s)) in enumerate(zip(cols, scenario_list)):
    is_cur = (i == 0)

    trips_up  = s['trips']     > s_cur['trips']
    tpvd_up   = s['tpvd']      > s_cur['tpvd']
    netrev_up = s['net_rev']   > s_cur['net_rev']
    nrpvd_up  = s['nrpvd']     > s_cur['nrpvd']
    cpt_up    = s['cpt']       < s_cur['cpt']
    vcd_up    = s['vcd']       > s_cur['vcd']
    l1p_up    = s['l1_profit'] > s_cur['l1_profit']
    l1pct_up  = s['l1_pct']    > s_cur['l1_pct']

    improved_count = sum([trips_up, tpvd_up, netrev_up, nrpvd_up, cpt_up, vcd_up, l1p_up, l1pct_up]) if not is_cur else 0

    if is_cur:
        bg, border = "#f5f5f5", "#ccc"
    elif improved_count >= 4:
        bg, border = "#e8f5e9", "#81c784"
    else:
        bg, border = "#ffebee", "#e57373"

    def metric_bg(is_good, val_diff):
        if is_cur:
            return "white"
        if val_diff == 0:
            return "#f5f5f5"
        return "#c8e6c9" if is_good else "#ffcdd2"

    d_trips  = delta_str(s['trips']     - s_cur['trips'],     'num',   is_cur)
    d_tpvd   = delta_str(s['tpvd']      - s_cur['tpvd'],      'num',   is_cur)
    d_netrev = delta_str(s['net_rev']   - s_cur['net_rev'],   'money', is_cur)
    d_nrpvd  = delta_str(s['nrpvd']     - s_cur['nrpvd'],     'num',   is_cur)
    d_cpt    = delta_str_reverse(s['cpt'] - s_cur['cpt'],     'num',   is_cur)
    d_vcd    = delta_str(s['vcd']       - s_cur['vcd'],       'num',   is_cur)
    d_l1p    = delta_str(s['l1_profit'] - s_cur['l1_profit'], 'money', is_cur)
    d_l1pct  = delta_str(s['l1_pct']   - s_cur['l1_pct'],    'pct',   is_cur)

    html  = "<div style='background:" + bg + ";border:1px solid " + border + ";border-radius:10px;padding:14px 16px;'>"
    html += "<div style='font-size:13px;font-weight:600;color:#333;margin-bottom:12px;'>" + lbl + "</div>"
    html += "<div style='display:flex;gap:8px;margin-bottom:6px;'>"
    html += "<div style='background:" + metric_bg(trips_up,  s['trips']     - s_cur['trips'])     + ";border-radius:8px;padding:8px 10px;flex:1;text-align:center;'><div style='font-size:10px;color:#1a1a2e;font-weight:500;margin-bottom:2px;'>Trips" + d_trips + "</div><div style='font-size:14px;font-weight:600;'>" + f"{s['trips']:,.0f}" + "</div></div>"
    html += "<div style='background:" + metric_bg(tpvd_up,   s['tpvd']      - s_cur['tpvd'])      + ";border-radius:8px;padding:8px 10px;flex:1;text-align:center;'><div style='font-size:10px;color:#1a1a2e;font-weight:500;margin-bottom:2px;'>TPVD" + d_tpvd + "</div><div style='font-size:14px;font-weight:600;'>" + f"{s['tpvd']:.2f}" + "</div></div>"
    html += "</div><div style='display:flex;gap:8px;margin-bottom:6px;'>"
    html += "<div style='background:" + metric_bg(netrev_up, s['net_rev']   - s_cur['net_rev'])   + ";border-radius:8px;padding:8px 10px;flex:1;text-align:center;'><div style='font-size:10px;color:#1a1a2e;font-weight:500;margin-bottom:2px;'>Net Revenue" + d_netrev + "</div><div style='font-size:14px;font-weight:600;'>$" + f"{s['net_rev']:,.0f}" + "</div></div>"
    html += "<div style='background:" + metric_bg(nrpvd_up,  s['nrpvd']     - s_cur['nrpvd'])     + ";border-radius:8px;padding:8px 10px;flex:1;text-align:center;'><div style='font-size:10px;color:#1a1a2e;font-weight:500;margin-bottom:2px;'>NRPVD" + d_nrpvd + "</div><div style='font-size:14px;font-weight:600;'>$" + f"{s['nrpvd']:.2f}" + "</div></div>"
    html += "</div><div style='display:flex;gap:8px;margin-bottom:6px;'>"
    html += "<div style='background:" + metric_bg(cpt_up,    s['cpt']       - s_cur['cpt'])       + ";border-radius:8px;padding:8px 10px;flex:1;text-align:center;'><div style='font-size:10px;color:#1a1a2e;font-weight:500;margin-bottom:2px;'>CPT" + d_cpt + "</div><div style='font-size:14px;font-weight:600;'>$" + f"{s['cpt']:.2f}" + "</div></div>"
    html += "<div style='background:" + metric_bg(vcd_up,    s['vcd']       - s_cur['vcd'])       + ";border-radius:8px;padding:8px 10px;flex:1;text-align:center;'><div style='font-size:10px;color:#1a1a2e;font-weight:500;margin-bottom:2px;'>VCD" + d_vcd + "</div><div style='font-size:14px;font-weight:600;'>$" + f"{s['vcd']:.2f}" + "</div></div>"
    html += "</div><div style='display:flex;gap:8px;'>"
    html += "<div style='background:" + metric_bg(l1p_up,    s['l1_profit'] - s_cur['l1_profit']) + ";border-radius:8px;padding:8px 10px;flex:1;text-align:center;'><div style='font-size:10px;color:#1a1a2e;font-weight:500;margin-bottom:2px;'>L1 Profit" + d_l1p + "</div><div style='font-size:14px;font-weight:600;'>$" + f"{s['l1_profit']:,.0f}" + "</div></div>"
    html += "<div style='background:" + metric_bg(l1pct_up,  s['l1_pct']    - s_cur['l1_pct'])    + ";border-radius:8px;padding:8px 10px;flex:1;text-align:center;'><div style='font-size:10px;color:#1a1a2e;font-weight:500;margin-bottom:2px;'>L1 %" + d_l1pct + "</div><div style='font-size:14px;font-weight:600;'>" + f"{s['l1_pct']:.1f}%" + "</div></div>"
    html += "</div></div>"
    col.markdown(html, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════
# Assumptions & Limitations
# ══════════════════════════════════════════════════════
st.markdown("---")
st.markdown("""
<div style="margin-top:13px;">
    <div style="font-size:14px; font-weight:700; color:#212529; margin-bottom:12px;">
        ⚠️ Assumptions & Limitations
    </div>
    <ul style="font-size:13px; color:#495057; margin:0; padding-left:18px; line-height:1.8;">
        <li>Users exceeding the Glide time limit are assumed to fully churn (actual churn rate may be lower).</li>
        <li>PPU/PPM elasticity values are user-defined estimates rather than empirically observed metrics.</li>
        <li>Glide-driven and price-driven trip declines are calculated independently, and potential overlap is not accounted for.</li>
        <li>Subs Free Unlock % uses the city-wide average across all OPZs (no OPZ-level breakdown available)</li>
    </ul>
    <div style="font-size:13px; font-weight:500; color:#212529; margin-top:14px;">
        ※ Results are based on a simplified model and should be used as reference values for scenario comparison, not absolute predictions.
    </div>
</div>
""", unsafe_allow_html=True)
