from datetime import date, datetime, timedelta
import io
import os
import urllib.request
import pandas as pd
import requests
import streamlit as st

# ReportLab関連のインポート（フローブル構造・複数ページ対応）
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

# --------------------------------------------------
# 0. 3つのテーブル・アプリ別プリセット設定
# --------------------------------------------------
APP_PRESETS = {
    "1. 鋳物販売管理": {
        "app_id": 36,
        "f_customer": "field-3",
        "f_date": "field-17_12",      # 納品日
        "f_order_date": "field-2",    # 受注日
        "f_order_no": "field-9",      # 図面番号
        "f_drawing": "field-17_2",    # 部番（5桁ゼロ埋め対象）
        "f_item_name": "field-6",     # 品名
        "f_material": "field-7",      # 材質
        "f_qty": "field-17_11",       # 納品数量
        "f_order_qty": "field-17_8",  # 受注数量
        "f_price": "field-17_13",     # 販売単価
        "f_sub_table": "field-17",
        "f_supplier": "field-16",     # 仕入先名
        "f_cost_price": "field-17_14", # 仕入単価
        "secret_key_name": "app36_api_key",
    },
    "2. 物販管理": {
        "app_id": 34,
        "f_customer": "field-7",
        "f_date": "field-9_6",        # 納品日
        "f_order_date": "field-2",    # 受注日
        "f_order_no": "field-5",      # 注文番号
        "f_drawing": "",
        "f_item_name": "field-9_11",  # 品名
        "f_material": "",
        "f_qty": "field-9_2",         # 数量
        "f_order_qty": "",
        "f_price": "field-9_12",      # 販売単価
        "f_sub_table": "field-9",
        "f_supplier": "field-4",      # 仕入先名
        "f_cost_price": "field-9_13", # 仕入単価
        "secret_key_name": "app34_api_key",
    },
    "3. 鋳物管理ST-Ver": {
        "app_id": 31,
        "f_customer": "field-5",
        "f_date": "field-17",         # 納品日
        "f_order_date": "field-6",    # 受注日
        "f_order_no": "field-11",     # 注文番号
        "f_drawing": "field-9",       # 図番
        "f_item_name": "field-10",    # 品名
        "f_material": "field-12",     # 材質
        "f_qty": "field-13",          # 数量
        "f_order_qty": "",
        "f_price": "field-18",        # 販売単価
        "f_sub_table": "",            # サブテーブルなし
        "f_supplier": "field-3",      # 発注先名
        "f_cost_price": "field-19",   # 仕入単価
        "secret_key_name": "app31_api_key",
    },
}

# --------------------------------------------------
# 1. ページ初期設定
# --------------------------------------------------
st.set_page_config(page_title="期間請求書＆期間納品書＆仕入れ・未納管理", layout="wide")

st.title("🏢 期間請求書 ＆ 📋 期間納品書 ＆ 📦 仕入れ台帳 ＆ ⚠️ 未納管理システム")


# --------------------------------------------------
# 2. 日本語フォント登録処理（完全対応版）
# --------------------------------------------------
def setup_japanese_font():
    local_font_path = "NotoSansJP-Regular.ttf"
    if os.path.exists(local_font_path):
        try:
            pdfmetrics.registerFont(TTFont("JPFont", local_font_path))
            return "JPFont"
        except Exception:
            pass

    win_fonts = [
        os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Fonts", "msgothic.ttc"),
        os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Fonts", "meiryo.ttc"),
        os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Fonts", "YuGothM.ttc"),
    ]
    for font_path in win_fonts:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont("JPFont", font_path, subfontIndex=0))
                return "JPFont"
            except Exception:
                pass

    font_url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP-Regular.ttf"
    try:
        urllib.request.urlretrieve(font_url, local_font_path)
        if os.path.exists(local_font_path):
            pdfmetrics.registerFont(TTFont("JPFont", local_font_path))
            return "JPFont"
    except Exception:
        pass

    return "Helvetica"

FONT_NAME = setup_japanese_font()

# --------------------------------------------------
# 3. サイドバー設定（マルチAPIキー自動切り替え対応）
# --------------------------------------------------
st.sidebar.header("⚙️ システム・テーブル設定")

selected_preset_name = st.sidebar.selectbox(
    "📋 対象テーブル（アプリ）の選択", list(APP_PRESETS.keys())
)
current_preset = APP_PRESETS[selected_preset_name]

key_name = current_preset["secret_key_name"]
default_api_key = st.secrets.get(key_name, st.secrets.get("pockets_api_key", ""))

api_key = st.sidebar.text_input(
    f"「{selected_preset_name}」用 APIキー", value=default_api_key, type="password"
)
app_id = st.sidebar.number_input(
    "アプリID", value=current_preset["app_id"], step=1
)

st.sidebar.markdown("---")
st.sidebar.header("🏢 発行元・振込先・備考設定")

DEFAULT_ISSUER_TEXT = (
    "株式会社 キャステム \n"
    "〒275-0016 千葉県 習志野市 津田沼 7-18-25\n"
    "TEL:047-452-9541 FAX:047-451-5843\n"
    "mail: info@castem.info"
)

DEFAULT_BANK_TEXT = (
    "京葉銀行 新習志野支店 （普）3565091\n" "みずほ銀行 津田沼支店 （普）2632369\n" "カ)キャステム"
)

DEFAULT_REMARKS_TEXT = "毎月末日までに翌月分をお振込みください。\n振込手数料はご負担ください。"

issuer_info = st.sidebar.text_area(
    "請求・発行元", value=DEFAULT_ISSUER_TEXT, height=120
)
bank_info = st.sidebar.text_area(
    "お振込先口座", value=DEFAULT_BANK_TEXT, height=100
)
default_remarks = st.sidebar.text_area(
    "標準の備考欄（UIから変更可能）", value=DEFAULT_REMARKS_TEXT, height=90
)


# --------------------------------------------------
# 4. APIデータ取得関数（Q絞り込み対応版）
# --------------------------------------------------
def fetch_pocket_records(api_key, app_id, start_date=None, end_date=None, preset=None, mode="invoice"):
    url = f"https://app060.at-pocket.com/seihon03_bb/api/apps/{app_id}/records"
    headers = {"X-At-Pocket-API-Key": api_key, "Accept": "application/json"}
    
    params = {}
    if start_date and end_date and preset:
        f_target = preset["f_order_date"] if mode == "alert" else preset["f_date"]
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        params["query"] = f'{f_target} >= "{start_str}" and {f_target} <= "{end_str}"'

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        if response.status_code != 200 and "query" in params:
            response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"APIエラーが発生しました（ステータスコード: {response.status_code}）")
            return None
    except Exception as e:
        st.error(f"通信エラーが発生しました: {e}")
        return None


# --------------------------------------------------
# 汎用フィールド値抽出ヘルパー ＆ 5桁ゼロ埋めフォーマッター
# --------------------------------------------------
def extract_val(raw_val):
    if raw_val is None:
        return ""
    if isinstance(raw_val, dict):
        return str(raw_val.get("value", raw_val.get("name", ""))).strip()
    elif isinstance(raw_val, list) and len(raw_val) > 0:
        extracted = []
        for item in raw_val:
            if isinstance(item, dict):
                extracted.append(str(item.get("value", item.get("name", ""))))
            else:
                extracted.append(str(item))
        return " ".join([e for e in extracted if e and e.lower() != "none"])
    else:
        val_str = str(raw_val).strip()
        if val_str.lower() == "none":
            return ""
        return val_str

def format_drawing_no(val):
    """部番を5桁のゼロ埋め表記（例: 00123）にする"""
    s = extract_val(val)
    if not s:
        return ""
    cleaned = "".join([c for c in s if c.isdigit()])
    if cleaned and len(cleaned) <= 5:
        return cleaned.zfill(5)
    return s


# --------------------------------------------------
# 5. 集計関数（請求・納品用共通）
# --------------------------------------------------
def filter_and_group_by_customer_pocket(records, start_date, end_date, preset):
    parsed_list = []

    f_cust = preset["f_customer"]
    f_dt = preset["f_date"]
    f_ord = preset["f_order_no"]
    f_drawing = preset["f_drawing"]
    f_item_name = preset["f_item_name"]
    f_material = preset["f_material"]
    f_q = preset["f_qty"]
    f_p = preset["f_price"]
    f_sub = preset.get("f_sub_table", "")

    for r in records:
        inner = r.get("record", r)

        customer = extract_val(inner.get(f_cust, ""))
        if not customer:
            continue

        parent_order_no = extract_val(inner.get(f_ord, "")) if f_ord else ""
        parent_drawing = format_drawing_no(inner.get(f_drawing, "")) if f_drawing else ""
        parent_material = extract_val(inner.get(f_material, "")) if f_material else ""
        parent_item_name = extract_val(inner.get(f_item_name, "")) if f_item_name else ""

        sub_list = inner.get(f_sub, "") if f_sub else ""
        if f_sub and isinstance(sub_list, list):
            row_count = len(sub_list)
            for i in range(row_count):
                try:
                    sub_item = sub_list[i]
                    sub_rec = sub_item.get("record", sub_item) if isinstance(sub_item, dict) else {}

                    def get_sub_val(field_key):
                        if not field_key:
                            return ""
                        val = sub_rec.get(field_key)
                        if val is not None and val != "":
                            return extract_val(val)

                        val_container = inner.get(field_key)
                        if isinstance(val_container, list) and len(val_container) > i:
                            return extract_val(val_container[i])
                        return ""

                    date_str = get_sub_val(f_dt)
                    if not date_str:
                        continue

                    delivery_date = pd.to_datetime(date_str)
                    if not (pd.to_datetime(start_date) <= delivery_date <= pd.to_datetime(end_date)):
                        continue

                    def safe_float(val):
                        try:
                            return float(str(val).replace(",", ""))
                        except (ValueError, TypeError):
                            return 0.0

                    qty = safe_float(get_sub_val(f_q))
                    price = safe_float(get_sub_val(f_p))
                    amount = qty * price

                    ord_no = get_sub_val(f_ord) if f_ord and get_sub_val(f_ord) else parent_order_no
                    
                    raw_dwg = get_sub_val(f_drawing) if f_drawing and get_sub_val(f_drawing) else parent_drawing
                    drawing_val = format_drawing_no(raw_dwg) if preset.get("app_id") == 36 else extract_val(raw_dwg)

                    mat_val = get_sub_val(f_material) if f_material and get_sub_val(f_material) else parent_material
                    item_val = get_sub_val(f_item_name) if f_item_name and get_sub_val(f_item_name) else parent_item_name

                    parsed_list.append({
                        "顧客名": customer,
                        "納品日": delivery_date.strftime("%Y/%m/%d"),
                        "__sort_date": delivery_date,
                        "部番": drawing_val,
                        "品名": item_val,
                        "材質": mat_val,
                        "図面番号": ord_no,
                        "数量": qty,
                        "単価": price,
                        "金額": amount,
                    })
                except Exception:
                    continue
        else:
            raw_date_val = inner.get(f_dt)
            date_str = extract_val(raw_date_val)
            if not date_str:
                continue

            try:
                delivery_date = pd.to_datetime(date_str)
            except Exception:
                continue

            if pd.to_datetime(start_date) <= delivery_date <= pd.to_datetime(end_date):
                def safe_float(val):
                    try:
                        return float(str(val).replace(",", ""))
                    except (ValueError, TypeError):
                        return 0.0

                qty = safe_float(inner.get(f_q, 0))
                price = safe_float(inner.get(f_p, 0))
                amount = qty * price

                raw_dwg_parent = inner.get(f_drawing, "")
                drawing_val = format_drawing_no(raw_dwg_parent) if preset.get("app_id") == 36 else extract_val(raw_dwg_parent)

                parsed_list.append({
                    "顧客名": customer,
                    "納品日": delivery_date.strftime("%Y/%m/%d"),
                    "__sort_date": delivery_date,
                    "部番": drawing_val,
                    "品名": parent_item_name,
                    "材質": parent_material,
                    "図面番号": parent_order_no,
                    "数量": qty,
                    "単価": price,
                    "金額": amount,
                })

    if not parsed_list:
        return {}

    df = pd.DataFrame(parsed_list)

    customer_invoices = {}
    for customer, group in df.groupby("顧客名"):
        group_sorted = group.sort_values(by="__sort_date", ascending=True)
        items = group_sorted.drop(columns=["__sort_date"]).to_dict(orient="records")
        
        subtotal_ex_tax = sum(item["金額"] for item in items)
        tax_amount = subtotal_ex_tax * 0.10
        total_inc_tax = subtotal_ex_tax + tax_amount

        customer_invoices[customer] = {
            "明細": items,
            "税別小計": int(subtotal_ex_tax),
            "消費税": int(tax_amount),
            "税込合計": int(total_inc_tax),
            "件数": len(items),
        }

    return customer_invoices


# --------------------------------------------------
# 5.2 集計関数（仕入れ台帳用）
# --------------------------------------------------
def filter_and_group_by_supplier_pocket(records, start_date, end_date, preset):
    parsed_list = []

    f_supp = preset.get("f_supplier", "")
    f_dt = preset["f_date"]
    f_ord = preset["f_order_no"]
    f_drawing = preset["f_drawing"]
    f_item_name = preset["f_item_name"]
    f_material = preset["f_material"]
    f_q = preset["f_qty"]
    f_cost = preset.get("f_cost_price", "")
    f_sub = preset.get("f_sub_table", "")

    for r in records:
        inner = r.get("record", r)

        supplier = extract_val(inner.get(f_supp, ""))
        if not supplier:
            continue

        parent_order_no = extract_val(inner.get(f_ord, "")) if f_ord else ""
        parent_drawing = format_drawing_no(inner.get(f_drawing, "")) if f_drawing else ""
        parent_material = extract_val(inner.get(f_material, "")) if f_material else ""
        parent_item_name = extract_val(inner.get(f_item_name, "")) if f_item_name else ""

        sub_list = inner.get(f_sub, "") if f_sub else ""
        if f_sub and isinstance(sub_list, list):
            row_count = len(sub_list)
            for i in range(row_count):
                try:
                    sub_item = sub_list[i]
                    sub_rec = sub_item.get("record", sub_item) if isinstance(sub_item, dict) else {}

                    def get_sub_val(field_key):
                        if not field_key:
                            return ""
                        val = sub_rec.get(field_key)
                        if val is not None and val != "":
                            return extract_val(val)

                        val_container = inner.get(field_key)
                        if isinstance(val_container, list) and len(val_container) > i:
                            return extract_val(val_container[i])
                        return ""

                    date_str = get_sub_val(f_dt)
                    if not date_str:
                        continue

                    delivery_date = pd.to_datetime(date_str)
                    if not (pd.to_datetime(start_date) <= delivery_date <= pd.to_datetime(end_date)):
                        continue

                    def safe_float(val):
                        try:
                            return float(str(val).replace(",", ""))
                        except (ValueError, TypeError):
                            return 0.0

                    qty = safe_float(get_sub_val(f_q))
                    cost_price = safe_float(get_sub_val(f_cost))
                    cost_amount = qty * cost_price

                    ord_no = get_sub_val(f_ord) if f_ord and get_sub_val(f_ord) else parent_order_no
                    
                    raw_dwg = get_sub_val(f_drawing) if f_drawing and get_sub_val(f_drawing) else parent_drawing
                    drawing_val = format_drawing_no(raw_dwg) if preset.get("app_id") == 36 else extract_val(raw_dwg)

                    mat_val = get_sub_val(f_material) if f_material and get_sub_val(f_material) else parent_material
                    item_val = get_sub_val(f_item_name) if f_item_name and get_sub_val(f_item_name) else parent_item_name

                    parsed_list.append({
                        "仕入れ先": supplier,
                        "納品日": delivery_date.strftime("%Y/%m/%d"),
                        "__sort_date": delivery_date,
                        "部番": drawing_val,
                        "品名": item_val,
                        "材質": mat_val,
                        "図面番号": ord_no,
                        "数量": qty,
                        "仕入単価": cost_price,
                        "仕入金額": cost_amount,
                    })
                except Exception:
                    continue
        else:
            raw_date_val = inner.get(f_dt)
            date_str = extract_val(raw_date_val)
            if not date_str:
                continue

            try:
                delivery_date = pd.to_datetime(date_str)
            except Exception:
                continue

            if pd.to_datetime(start_date) <= delivery_date <= pd.to_datetime(end_date):
                def safe_float(val):
                    try:
                        return float(str(val).replace(",", ""))
                    except (ValueError, TypeError):
                        return 0.0

                qty = safe_float(inner.get(f_q, 0))
                cost_price = safe_float(inner.get(f_cost, 0))
                cost_amount = qty * cost_price

                raw_dwg_parent = inner.get(f_drawing, "")
                drawing_val = format_drawing_no(raw_dwg_parent) if preset.get("app_id") == 36 else extract_val(raw_dwg_parent)

                parsed_list.append({
                    "仕入れ先": supplier,
                    "納品日": delivery_date.strftime("%Y/%m/%d"),
                    "__sort_date": delivery_date,
                    "部番": drawing_val,
                    "品名": parent_item_name,
                    "材質": parent_material,
                    "図面番号": parent_order_no,
                    "数量": qty,
                    "仕入単価": cost_price,
                    "仕入金額": cost_amount,
                })

    if not parsed_list:
        return {}

    df = pd.DataFrame(parsed_list)

    supplier_ledgers = {}
    for supplier, group in df.groupby("仕入れ先"):
        group_sorted = group.sort_values(by="__sort_date", ascending=True)
        items = group_sorted.drop(columns=["__sort_date"]).to_dict(orient="records")
        
        total_cost = sum(item["仕入金額"] for item in items)

        supplier_ledgers[supplier] = {
            "明細": items,
            "仕入合計": int(total_cost),
            "件数": len(items),
        }

    return supplier_ledgers


# --------------------------------------------------
# 5.3 集計関数（未納アラート用）
# --------------------------------------------------
def filter_unfulfilled_orders(records, start_date, end_date, preset):
    parsed_list = []

    f_supp = preset.get("f_supplier", "")
    f_ord_date = preset["f_order_date"]
    f_dt = preset["f_date"]
    f_ord = preset["f_order_no"]
    f_drawing = preset["f_drawing"]
    f_item_name = preset["f_item_name"]
    f_material = preset["f_material"]
    f_q = preset["f_qty"]
    f_order_qty = preset.get("f_order_qty", "")
    f_sub = preset.get("f_sub_table", "")

    def safe_float(val):
        try:
            return float(str(val).replace(",", ""))
        except (ValueError, TypeError):
            return 0.0

    for r in records:
        inner = r.get("record", r)

        raw_order_date = inner.get(f_ord_date, "")
        order_date_str = extract_val(raw_order_date)
        if not order_date_str:
            continue

        try:
            order_date = pd.to_datetime(order_date_str)
        except Exception:
            continue

        if not (pd.to_datetime(start_date) <= order_date <= pd.to_datetime(end_date)):
            continue

        supplier = extract_val(inner.get(f_supp, ""))
        if not supplier:
            supplier = "（仕入れ先未設定）"

        parent_order_no = extract_val(inner.get(f_ord, "")) if f_ord else ""
        parent_drawing = format_drawing_no(inner.get(f_drawing, "")) if f_drawing else ""
        parent_material = extract_val(inner.get(f_material, "")) if f_material else ""
        parent_item_name = extract_val(inner.get(f_item_name, "")) if f_item_name else ""

        sub_list = inner.get(f_sub, "") if f_sub else ""
        if f_sub and isinstance(sub_list, list):
            row_count = len(sub_list)
            for i in range(row_count):
                try:
                    sub_item = sub_list[i]
                    sub_rec = sub_item.get("record", sub_item) if isinstance(sub_item, dict) else {}

                    def get_sub_val(field_key):
                        if not field_key:
                            return ""
                        val = sub_rec.get(field_key)
                        if val is not None and val != "":
                            return extract_val(val)

                        val_container = inner.get(field_key)
                        if isinstance(val_container, list) and len(val_container) > i:
                            return extract_val(val_container[i])
                        return ""

                    ord_qty_val = 0.0
                    if f_order_qty:
                        ord_qty_val = safe_float(get_sub_val(f_order_qty))
                        if ord_qty_val == 0.0:
                            continue

                    delivery_str = get_sub_val(f_dt)
                    if delivery_str:
                        continue

                    qty = safe_float(get_sub_val(f_q))
                    ord_no = get_sub_val(f_ord) if f_ord and get_sub_val(f_ord) else parent_order_no
                    
                    raw_dwg = get_sub_val(f_drawing) if f_drawing and get_sub_val(f_drawing) else parent_drawing
                    drawing_val = format_drawing_no(raw_dwg) if preset.get("app_id") == 36 else extract_val(raw_dwg)

                    mat_val = get_sub_val(f_material) if f_material and get_sub_val(f_material) else parent_material
                    item_val = get_sub_val(f_item_name) if f_item_name and get_sub_val(f_item_name) else parent_item_name

                    parsed_list.append({
                        "仕入れ先": supplier,
                        "受注日": order_date.strftime("%Y/%m/%d"),
                        "__sort_date": order_date,
                        "部番": drawing_val,
                        "品名": item_val,
                        "材質": mat_val,
                        "図面番号": ord_no,
                        "受注数量": ord_qty_val,
                        "数量": qty,
                        "状態": "未納（納品日未入力）",
                    })
                except Exception:
                    continue
        else:
            ord_qty_val = 0.0
            if f_order_qty:
                ord_qty_val = safe_float(inner.get(f_order_qty, 0))
                if ord_qty_val == 0.0:
                    continue

            delivery_str = extract_val(inner.get(f_dt, ""))
            if delivery_str:
                continue

            qty = safe_float(inner.get(f_q, 0))

            parsed_list.append({
                "仕入れ先": supplier,
                "受注日": order_date.strftime("%Y/%m/%d"),
                "__sort_date": order_date,
                "部番": parent_drawing,
                "品名": parent_item_name,
                "材質": parent_material,
                "図面番号": parent_order_no,
                "受注数量": ord_qty_val,
                "数量": qty,
                "状態": "未納（納品日未入力）",
            })

    if not parsed_list:
        return {}

    df = pd.DataFrame(parsed_list)

    unfulfilled_dict = {}
    for supplier, group in df.groupby("仕入れ先"):
        group_sorted = group.sort_values(by="__sort_date", ascending=True)
        items = group_sorted.drop(columns=["__sort_date"]).to_dict(orient="records")
        
        unfulfilled_dict[supplier] = {
            "明細": items,
            "件数": len(items),
        }

    return unfulfilled_dict


# --------------------------------------------------
# 6. 総ページ数自動挿入用カスタムCanvas
# --------------------------------------------------
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont(FONT_NAME, 8.5)
        self.setFillColor(colors.HexColor("#1E293B"))
        page_text = f"{self._pageNumber} / {page_count}"
        self.drawCentredString(595.27 / 2.0, 20, page_text)
        self.restoreState()


# --------------------------------------------------
# 7. PDF生成関数（請求書用 ＆ 納品書用）
# --------------------------------------------------
def generate_period_invoice_pdf(
    customer_name, inv_data, target_month, issuer_info, bank_info, remarks_text
):
    buffer = io.BytesIO()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle("Title", fontName=FONT_NAME, fontSize=20, leading=24, textColor=colors.HexColor("#1E3A8A"))
    sub_style = ParagraphStyle("Sub", fontName=FONT_NAME, fontSize=9, leading=12, textColor=colors.HexColor("#3B82F6"), alignment=2)
    meta_style = ParagraphStyle("Meta", fontName=FONT_NAME, fontSize=9, leading=13, textColor=colors.HexColor("#1E293B"))
    issuer_style = ParagraphStyle("Issuer", fontName=FONT_NAME, fontSize=9, leading=13, textColor=colors.HexColor("#1E293B"))
    
    th_style = ParagraphStyle("TH", fontName=FONT_NAME, fontSize=8, leading=10, textColor=colors.white, alignment=1)
    td_date = ParagraphStyle("TDDate", fontName=FONT_NAME, fontSize=8, leading=11, textColor=colors.HexColor("#1E293B"))
    td_text = ParagraphStyle("TDText", fontName=FONT_NAME, fontSize=8, leading=11, textColor=colors.HexColor("#1E293B"))
    td_right = ParagraphStyle("TDRight", fontName=FONT_NAME, fontSize=8, leading=11, textColor=colors.HexColor("#1E293B"), alignment=2)

    today_str = date.today().strftime("%Y年%m月%d日")
    elements = []

    elements.append(Paragraph("<b>御 請 求 書</b>", title_style))
    elements.append(Paragraph(f"対象期間: {target_month}", sub_style))
    elements.append(Spacer(1, 4))
    
    cust_para = Paragraph(f"<b>{customer_name} 御中</b>", ParagraphStyle("Cust", fontName=FONT_NAME, fontSize=12, leading=16, textColor=colors.HexColor("#1E293B")))
    issuer_lines = f"<b>発行日: {today_str}</b><br/><br/><b>[ 発行元 ]</b><br/>" + issuer_info.replace("\n", "<br/>")
    issuer_para = Paragraph(issuer_lines, issuer_style)

    top_info_table = Table([[cust_para, issuer_para]], colWidths=[260, 255])
    top_info_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    elements.append(top_info_table)
    elements.append(Spacer(1, 10))

    elements.append(Paragraph("下記の通りご請求申し上げます。", meta_style))
    elements.append(Spacer(1, 6))

    total_inc_yen = f"￥{inv_data['税込合計']:,}-"
    tax_ex_yen = f"￥{inv_data['税別小計']:,}-"
    tax_yen = f"￥{inv_data['消費税']:,}-"

    box_data = [
        [Paragraph("<b>ご請求金額合計（税込）</b>", ParagraphStyle("BT1", fontName=FONT_NAME, fontSize=9, leading=12, textColor=colors.HexColor("#1E293B"))),
         Paragraph(f"（税別金額: {tax_ex_yen}）", ParagraphStyle("BT2", fontName=FONT_NAME, fontSize=8.5, leading=11, textColor=colors.HexColor("#1E293B"), alignment=2))],
        [Paragraph(f"<b><font size=18 color='#1E3A8A'>{total_inc_yen}</font></b>", ParagraphStyle("BT3", fontName=FONT_NAME, fontSize=18, leading=22)),
         Paragraph(f"（消費税10%: {tax_yen}）", ParagraphStyle("BT4", fontName=FONT_NAME, fontSize=8.5, leading=11, textColor=colors.HexColor("#1E293B"), alignment=2))]
    ]
    box_table = Table(box_data, colWidths=[280, 235])
    box_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#1E3A8A")),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(box_table)
    elements.append(Spacer(1, 15))

    table_data = [[
        Paragraph("納品日", th_style),
        Paragraph("部番 / 図面番号", th_style),
        Paragraph("品名 / 材質", th_style),
        Paragraph("数量", th_style),
        Paragraph("単価", th_style),
        Paragraph("金額（税別）", th_style),
    ]]

    for item in inv_data["明細"]:
        dwg_ord = []
        if item["部番"]:
            dwg_ord.append(item["部番"])
        if item["図面番号"]:
            dwg_ord.append(f"({item['図面番号']})")
        
        name_mat = item["品名"]
        if item["材質"]:
            name_mat += f" [{item['材質']}]"

        table_data.append([
            Paragraph(str(item["納品日"]), td_date),
            Paragraph(" ".join(dwg_ord), td_text),
            Paragraph(name_mat, td_text),
            Paragraph(f"{item['数量']:,}", td_right),
            Paragraph(f"￥{item['単価']:,}", td_right),
            Paragraph(f"￥{item['金額']:,}", td_right),
        ])

    col_widths = [65, 110, 160, 45, 60, 75]
    
    details_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    details_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
    ]))
    elements.append(details_table)
    elements.append(Spacer(1, 20))

    bank_html = "<b>【お振込先口座】</b><br/>" + bank_info.replace("\n", "<br/>")
    remarks_html = "<b>【備考】</b><br/>" + remarks_text.replace("\n", "<br/>")

    bank_para = Paragraph(bank_html, ParagraphStyle("Bank", fontName=FONT_NAME, fontSize=8, leading=11, textColor=colors.HexColor("#1E293B")))
    remarks_para = Paragraph(remarks_html, ParagraphStyle("Rem", fontName=FONT_NAME, fontSize=8, leading=11, textColor=colors.HexColor("#1E293B")))

    footer_table = Table([[bank_para, remarks_para]], colWidths=[250, 265])
    footer_table.setStyle(TableStyle([
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor("#F8FAFC")),
        ('BOX', (1, 0), (1, 0), 0.5, colors.HexColor("#CBD5E1")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(footer_table)

    doc.build(elements, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer


def generate_period_delivery_pdf(
    customer_name, inv_data, target_month, issuer_info, remarks_text
):
    """期間納品書PDF生成関数（請求書をベースにタイトル・文言を納品書用に変更）"""
    buffer = io.BytesIO()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    title_style = ParagraphStyle("Title", fontName=FONT_NAME, fontSize=20, leading=24, textColor=colors.HexColor("#1E3A8A"))
    sub_style = ParagraphStyle("Sub", fontName=FONT_NAME, fontSize=9, leading=12, textColor=colors.HexColor("#3B82F6"), alignment=2)
    meta_style = ParagraphStyle("Meta", fontName=FONT_NAME, fontSize=9, leading=13, textColor=colors.HexColor("#1E293B"))
    issuer_style = ParagraphStyle("Issuer", fontName=FONT_NAME, fontSize=9, leading=13, textColor=colors.HexColor("#1E293B"))
    
    th_style = ParagraphStyle("TH", fontName=FONT_NAME, fontSize=8, leading=10, textColor=colors.white, alignment=1)
    td_date = ParagraphStyle("TDDate", fontName=FONT_NAME, fontSize=8, leading=11, textColor=colors.HexColor("#1E293B"))
    td_text = ParagraphStyle("TDText", fontName=FONT_NAME, fontSize=8, leading=11, textColor=colors.HexColor("#1E293B"))
    td_right = ParagraphStyle("TDRight", fontName=FONT_NAME, fontSize=8, leading=11, textColor=colors.HexColor("#1E293B"), alignment=2)

    today_str = date.today().strftime("%Y年%m月%d日")
    elements = []

    # ★ タイトルを納品書に変更
    elements.append(Paragraph("<b>御 納 品 書</b>", title_style))
    elements.append(Paragraph(f"対象期間: {target_month}", sub_style))
    elements.append(Spacer(1, 4))
    
    cust_para = Paragraph(f"<b>{customer_name} 御中</b>", ParagraphStyle("Cust", fontName=FONT_NAME, fontSize=12, leading=16, textColor=colors.HexColor("#1E293B")))
    issuer_lines = f"<b>発行日: {today_str}</b><br/><br/><b>[ 発行元 ]</b><br/>" + issuer_info.replace("\n", "<br/>")
    issuer_para = Paragraph(issuer_lines, issuer_style)

    top_info_table = Table([[cust_para, issuer_para]], colWidths=[260, 255])
    top_info_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    elements.append(top_info_table)
    elements.append(Spacer(1, 10))

    # ★ 文言を納品申し上げますに変更
    elements.append(Paragraph("下記の通り納品申し上げます。", meta_style))
    elements.append(Spacer(1, 6))

    total_inc_yen = f"￥{inv_data['税込合計']:,}-"
    tax_ex_yen = f"￥{inv_data['税別小計']:,}-"
    tax_yen = f"￥{inv_data['消費税']:,}-"

    box_data = [
        [Paragraph("<b>納品金額合計（税込）</b>", ParagraphStyle("BT1", fontName=FONT_NAME, fontSize=9, leading=12, textColor=colors.HexColor("#1E293B"))),
         Paragraph(f"（税別金額: {tax_ex_yen}）", ParagraphStyle("BT2", fontName=FONT_NAME, fontSize=8.5, leading=11, textColor=colors.HexColor("#1E293B"), alignment=2))],
        [Paragraph(f"<b><font size=18 color='#1E3A8A'>{total_inc_yen}</font></b>", ParagraphStyle("BT3", fontName=FONT_NAME, fontSize=18, leading=22)),
         Paragraph(f"（消費税10%: {tax_yen}）", ParagraphStyle("BT4", fontName=FONT_NAME, fontSize=8.5, leading=11, textColor=colors.HexColor("#1E293B"), alignment=2))]
    ]
    box_table = Table(box_data, colWidths=[280, 235])
    box_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#1E3A8A")),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(box_table)
    elements.append(Spacer(1, 15))

    table_data = [[
        Paragraph("納品日", th_style),
        Paragraph("部番 / 図面番号", th_style),
        Paragraph("品名 / 材質", th_style),
        Paragraph("数量", th_style),
        Paragraph("単価", th_style),
        Paragraph("金額（税別）", th_style),
    ]]

    for item in inv_data["明細"]:
        dwg_ord = []
        if item["部番"]:
            dwg_ord.append(item["部番"])
        if item["図面番号"]:
            dwg_ord.append(f"({item['図面番号']})")
        
        name_mat = item["品名"]
        if item["材質"]:
            name_mat += f" [{item['材質']}]"

        table_data.append([
            Paragraph(str(item["納品日"]), td_date),
            Paragraph(" ".join(dwg_ord), td_text),
            Paragraph(name_mat, td_text),
            Paragraph(f"{item['数量']:,}", td_right),
            Paragraph(f"￥{item['単価']:,}", td_right),
            Paragraph(f"￥{item['金額']:,}", td_right),
        ])

    col_widths = [65, 110, 160, 45, 60, 75]
    
    details_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    details_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
    ]))