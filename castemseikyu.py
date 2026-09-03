import datetime
import io
import os
import urllib.request
import pandas as pd
import requests
import streamlit as st

# ReportLab関連のインポート
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# --------------------------------------------------
# 0. 3つのテーブル・アプリ別プリセット設定
# --------------------------------------------------
APP_PRESETS = {
    "1. 鋳物販売管理": {
        "app_id": 36,
        "f_customer": "field-3",
        "f_date": "field-17_12",      # 納品日
        "f_order_date": "field-2",    # 受注日
        "f_order_no": "field-10",     # 注文番号
        "f_drawing": "field-17_2",    # 部番
        "f_item_name": "field-6",     # 品名
        "f_material": "",
        "f_qty": "field-17_11",       # 納品数量
        "f_order_qty": "field-17_8",  # 受注数量
        "f_price": "field-17_13",     # 販売単価
        "f_sub_table": "field-17",
        "f_supplier": "field-16",     # 仕入先名
        "f_cost_price": "field-17_14", # 仕入単価
        "secret_key_name": "app36_api_key", # 対応するシークレットキー名
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
st.set_page_config(page_title="期間請求書＆仕入れ・未納管理システム", layout="wide")

st.title("🏢 期間請求書 ＆ 📦 仕入れ台帳 ＆ ⚠️ 未納管理システム")


# --------------------------------------------------
# 2. 日本語フォント登録処理（エラー完全対策版）
# --------------------------------------------------
def setup_japanese_font():
    # 1. Windows標準フォントを優先探索
    win_fonts = [
        os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Fonts", "msgothic.ttc"),
        os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Fonts", "meiryo.ttc"),
        os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Fonts", "YuGothM.ttc"),
    ]
    for font_path in win_fonts:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont("JPFont", font_path))
                return "JPFont"
            except Exception:
                pass

    # 2. ローカルにあるフォントファイルの確認
    local_font_path = "NotoSansJP-Regular.ttf"
    if os.path.exists(local_font_path):
        try:
            pdfmetrics.registerFont(TTFont("JPFont", local_font_path))
            return "JPFont"
        except Exception:
            pass

    # 3. 安定したリポジトリからのフォントダウンロード試行（失敗しても絶対に止めない）
    font_url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP-Regular.ttf"
    try:
        urllib.request.urlretrieve(font_url, local_font_path)
        if os.path.exists(local_font_path):
            pdfmetrics.registerFont(TTFont("JPFont", local_font_path))
            return "JPFont"
    except Exception:
        pass

    # 4. すべてダメな場合は標準フォント（Helvetica）にフォールバックしてクラッシュを防ぐ
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

# 選択されたアプリに応じたAPIキーを自動取得（個別キーがなければ共通キーフォールバック）
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
    "株式会社CASTEM \n"
    "〒275-0016 千葉県 習志野市 津田沼 7-18-25\n"
    "TEL: 047-000-0000\n"
    "mail: info@castem.info"
)

DEFAULT_BANK_TEXT = (
    "*****銀行（000）\n" "***支店 普通 *******\n" "カ)キャステム"
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
# 5. 集計関数（請求用）
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

        raw_cust = inner.get(f_cust, "")
        if isinstance(raw_cust, dict):
            customer = str(raw_cust.get("value", raw_cust.get("name", ""))).strip()
        elif isinstance(raw_cust, list) and len(raw_cust) > 0:
            customer = str(raw_cust[0]).strip()
        else:
            customer = str(raw_cust).strip()

        if not customer or customer.lower() == "none":
            continue

        parent_order_no = str(inner.get(f_ord, "")) if f_ord else ""

        sub_list = inner.get(f_sub, "") if f_sub else ""
        if f_sub and isinstance(sub_list, list):
            row_count = len(sub_list)
            for i in range(row_count):
                try:
                    sub_item = sub_list[i]
                    if isinstance(sub_item, dict):
                        sub_rec = sub_item.get("record", sub_item)
                    else:
                        sub_rec = {}

                    def get_sub_val(field_key):
                        if not field_key:
                            return ""
                        val = sub_rec.get(field_key)
                        if val is not None and val != "":
                            return str(val)

                        val_container = inner.get(field_key)
                        if isinstance(val_container, list) and len(val_container) > i:
                            item = val_container[i]
                            if isinstance(item, dict):
                                return str(item.get("value", item.get("record", {}).get(field_key, "")))
                            return str(item)
                        return ""

                    date_str = get_sub_val(f_dt)
                    if not date_str or date_str.lower() == "none":
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

                    ord_no = get_sub_val(f_ord) if f_ord else parent_order_no

                    parsed_list.append({
                        "顧客名": customer,
                        "納品日": delivery_date.strftime("%Y/%m/%d"),
                        "図番": get_sub_val(f_drawing) if f_drawing else "",
                        "品名": get_sub_val(f_item_name),
                        "材質": get_sub_val(f_material) if f_material else "",
                        "注文番号": ord_no,
                        "数量": qty,
                        "単価": price,
                        "金額": amount,
                    })
                except Exception:
                    continue
        else:
            raw_date_val = inner.get(f_dt)
            date_str = str(raw_date_val or "")
            if not date_str or date_str.lower() == "none":
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

                parsed_list.append({
                    "顧客名": customer,
                    "納品日": delivery_date.strftime("%Y/%m/%d"),
                    "図番": str(inner.get(f_drawing, "")) if f_drawing else "",
                    "品名": str(inner.get(f_item_name, "")),
                    "材質": str(inner.get(f_material, "")) if f_material else "",
                    "注文番号": str(inner.get(f_ord, "")) if f_ord else "",
                    "数量": qty,
                    "単価": price,
                    "金額": amount,
                })

    if not parsed_list:
        return {}

    df = pd.DataFrame(parsed_list)

    customer_invoices = {}
    for customer, group in df.groupby("顧客名"):
        items = group.to_dict(orient="records")
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

        raw_supp = inner.get(f_supp, "")
        if isinstance(raw_supp, dict):
            supplier = str(raw_supp.get("value", raw_supp.get("name", ""))).strip()
        elif isinstance(raw_supp, list) and len(raw_supp) > 0:
            supplier = str(raw_supp[0]).strip()
        else:
            supplier = str(raw_supp).strip()

        if not supplier or supplier.lower() == "none":
            continue

        parent_order_no = str(inner.get(f_ord, "")) if f_ord else ""

        sub_list = inner.get(f_sub, "") if f_sub else ""
        if f_sub and isinstance(sub_list, list):
            row_count = len(sub_list)
            for i in range(row_count):
                try:
                    sub_item = sub_list[i]
                    if isinstance(sub_item, dict):
                        sub_rec = sub_item.get("record", sub_item)
                    else:
                        sub_rec = {}

                    def get_sub_val(field_key):
                        if not field_key:
                            return ""
                        val = sub_rec.get(field_key)
                        if val is not None and val != "":
                            return str(val)

                        val_container = inner.get(field_key)
                        if isinstance(val_container, list) and len(val_container) > i:
                            item = val_container[i]
                            if isinstance(item, dict):
                                return str(item.get("value", item.get("record", {}).get(field_key, "")))
                            return str(item)
                        return ""

                    date_str = get_sub_val(f_dt)
                    if not date_str or date_str.lower() == "none":
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

                    ord_no = get_sub_val(f_ord) if f_ord else parent_order_no

                    parsed_list.append({
                        "仕入れ先": supplier,
                        "納品日": delivery_date.strftime("%Y/%m/%d"),
                        "注文番号": ord_no,
                        "図番": get_sub_val(f_drawing) if f_drawing else "",
                        "品名": get_sub_val(f_item_name),
                        "材質": get_sub_val(f_material) if f_material else "",
                        "数量": qty,
                        "仕入単価": cost_price,
                        "仕入金額": cost_amount,
                    })
                except Exception:
                    continue
        else:
            raw_date_val = inner.get(f_dt)
            date_str = str(raw_date_val or "")
            if not date_str or date_str.lower() == "none":
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

                parsed_list.append({
                    "仕入れ先": supplier,
                    "納品日": delivery_date.strftime("%Y/%m/%d"),
                    "注文番号": str(inner.get(f_ord, "")) if f_ord else "",
                    "図番": str(inner.get(f_drawing, "")) if f_drawing else "",
                    "品名": str(inner.get(f_item_name, "")) if f_item_name else "",
                    "材質": str(inner.get(f_material, "")) if f_material else "",
                    "数量": qty,
                    "仕入単価": cost_price,
                    "仕入金額": cost_amount,
                })

    if not parsed_list:
        return {}

    df = pd.DataFrame(parsed_list)

    supplier_ledgers = {}
    for supplier, group in df.groupby("仕入れ先"):
        items = group.to_dict(orient="records")
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
        order_date_str = str(raw_order_date or "").strip()
        if not order_date_str or order_date_str.lower() == "none":
            continue

        try:
            order_date = pd.to_datetime(order_date_str)
        except Exception:
            continue

        if not (pd.to_datetime(start_date) <= order_date <= pd.to_datetime(end_date)):
            continue

        raw_supp = inner.get(f_supp, "")
        if isinstance(raw_supp, dict):
            supplier = str(raw_supp.get("value", raw_supp.get("name", ""))).strip()
        elif isinstance(raw_supp, list) and len(raw_supp) > 0:
            supplier = str(raw_supp[0]).strip()
        else:
            supplier = str(raw_supp).strip()
        
        if not supplier or supplier.lower() == "none":
            supplier = "（仕入れ先未設定）"

        parent_order_no = str(inner.get(f_ord, "")) if f_ord else ""

        sub_list = inner.get(f_sub, "") if f_sub else ""
        if f_sub and isinstance(sub_list, list):
            row_count = len(sub_list)
            for i in range(row_count):
                try:
                    sub_item = sub_list[i]
                    if isinstance(sub_item, dict):
                        sub_rec = sub_item.get("record", sub_item)
                    else:
                        sub_rec = {}

                    def get_sub_val(field_key):
                        if not field_key:
                            return ""
                        val = sub_rec.get(field_key)
                        if val is not None and val != "":
                            return str(val)

                        val_container = inner.get(field_key)
                        if isinstance(val_container, list) and len(val_container) > i:
                            item = val_container[i]
                            if isinstance(item, dict):
                                return str(item.get("value", item.get("record", {}).get(field_key, "")))
                            return str(item)
                        return ""

                    ord_qty_val = 0.0
                    if f_order_qty:
                        ord_qty_val = safe_float(get_sub_val(f_order_qty))
                        if ord_qty_val == 0.0:
                            continue

                    delivery_str = get_sub_val(f_dt)
                    if delivery_str and delivery_str.lower() != "none" and delivery_str.strip() != "":
                        continue

                    qty = safe_float(get_sub_val(f_q))
                    ord_no = get_sub_val(f_ord) if f_ord else parent_order_no

                    parsed_list.append({
                        "仕入れ先": supplier,
                        "受注日": order_date.strftime("%Y/%m/%d"),
                        "注文番号": ord_no,
                        "図番": get_sub_val(f_drawing) if f_drawing else "",
                        "品名": get_sub_val(f_item_name),
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

            delivery_str = str(inner.get(f_dt, "") or "").strip()
            if delivery_str and delivery_str.lower() != "none" and delivery_str != "":
                continue

            qty = safe_float(inner.get(f_q, 0))

            parsed_list.append({
                "仕入れ先": supplier,
                "受注日": order_date.strftime("%Y/%m/%d"),
                "注文番号": str(inner.get(f_ord, "")) if f_ord else "",
                "図番": str(inner.get(f_drawing, "")) if f_drawing else "",
                "品名": str(inner.get(f_item_name, "")) if f_item_name else "",
                "受注数量": ord_qty_val,
                "数量": qty,
                "状態": "未納（納品日未入力）",
            })

    if not parsed_list:
        return {}

    df = pd.DataFrame(parsed_list)

    unfulfilled_dict = {}
    for supplier, group in df.groupby("仕入れ先"):
        items = group.to_dict(orient="records")
        unfulfilled_dict[supplier] = {
            "明細": items,
            "件数": len(items),
        }

    return unfulfilled_dict


# --------------------------------------------------
# 6. ブルー基調・A4縦型請求書 PDF生成関数
# --------------------------------------------------
def generate_period_invoice_pdf(
    customer_name, inv_data, target_month, issuer_info, bank_info, remarks_text
):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    PRIMARY_COLOR = colors.HexColor("#1E3A8A")
    SECONDARY_COLOR = colors.HexColor("#3B82F6")
    BG_LIGHT = colors.HexColor("#F8FAFC")
    TEXT_DARK = colors.HexColor("#1E293B")
    BORDER_COLOR = colors.HexColor("#CBD5E1")

    today_str = datetime.date.today().strftime("%Y年%m月%d日")

    p.setFillColor(PRIMARY_COLOR)
    p.setFont(FONT_NAME, 22)
    p.drawString(40, height - 45, "御 請 求 書")

    p.setFont(FONT_NAME, 10)
    p.setFillColor(SECONDARY_COLOR)
    p.drawRightString(width - 40, height - 43, f"対象期間: {target_month}")

    p.setStrokeColor(PRIMARY_COLOR)
    p.setLineWidth(2)
    p.line(40, height - 53, width - 40, height - 53)

    p.setFillColor(TEXT_DARK)
    p.setFont(FONT_NAME, 13)
    p.drawString(40, height - 80, f"{customer_name}  御中")

    p.setFont(FONT_NAME, 9)
    p.drawRightString(width - 40, height - 70, f"発行日: {today_str}")

    y_issuer = height - 85
    p.setFillColor(PRIMARY_COLOR)
    p.setFont(FONT_NAME, 10)
    p.drawString(width - 240, y_issuer, "[ 発行元 ]")
    p.setFillColor(TEXT_DARK)
    p.setFont(FONT_NAME, 9.5)
    for line in issuer_info.split("\n"):
        y_issuer -= 14
        p.drawString(width - 240, y_issuer, line)

    p.setFont(FONT_NAME, 10)
    p.drawString(40, height - 128, "下記の通りご請求申し上げます。")

    box_y = height - 195
    box_h = 55
    p.setFillColor(BG_LIGHT)
    p.setStrokeColor(PRIMARY_COLOR)
    p.setLineWidth(1)
    p.rect(40, box_y, width - 80, box_h, fill=1, stroke=1)

    p.setFillColor(TEXT_DARK)
    p.setFont(FONT_NAME, 9)
    p.drawString(55, box_y + 35, "ご請求金額合計（税込）")

    total_inc_str = f"￥{inv_data['税込合計']:,}-"
    p.setFillColor(PRIMARY_COLOR)
    p.setFont(FONT_NAME, 21)
    p.drawString(55, box_y + 8, total_inc_str)

    p.setFont(FONT_NAME, 9)
    p.setFillColor(TEXT_DARK)
    p.drawRightString(
        width - 55, box_y + 35, f"（税別金額: ￥{inv_data['税別小計']:,}-）"
    )
    p.drawRightString(
        width - 55, box_y + 20, f"（消費税10%: ￥{inv_data['消費税']:,}-）"
    )

    table_y = box_y - 25
    p.setFillColor(PRIMARY_COLOR)
    p.rect(40, table_y - 20, width - 80, 20, fill=1, stroke=0)

    p.setFillColor(colors.white)
    p.setFont(FONT_NAME, 9)
    p.drawString(45, table_y - 14, "納品日")
    p.drawString(100, table_y - 14, "注文番号 / 図番")
    p.drawString(210, table_y - 14, "品名 / 材質")
    p.drawString(380, table_y - 14, "数量")
    p.drawString(430, table_y - 14, "単価")
    p.drawRightString(width - 45, table_y - 14, "金額（税別）")

    current_y = table_y - 35
    p.setFillColor(TEXT_DARK)
    p.setFont(FONT_NAME, 8.5)

    for item in inv_data["明細"]:
        if current_y < 150:
            break
        p.drawString(45, current_y, item["納品日"])

        ord_draw = []
        if item["注文番号"]:
            ord_draw.append(item["注文番号"])
        if item["図番"]:
            ord_draw.append(f"({item['図番']})")
        p.drawString(100, current_y, " ".join(ord_draw))

        name_mat = item["品名"]
        if item["材質"]:
            name_mat += f" [{item['材質']}]"
        p.drawString(210, current_y, name_mat)

        p.drawString(380, current_y, f"{item['数量']:,}")
        p.drawString(430, current_y, f"￥{item['単価']:,}")
        p.drawRightString(width - 45, current_y, f"￥{item['金額']:,}")

        p.setStrokeColor(BORDER_COLOR)
        p.setLineWidth(0.5)
        p.line(40, current_y - 4, width - 40, current_y - 4)
        current_y -= 22

    footer_y = 65

    p.setFillColor(PRIMARY_COLOR)
    p.setFont(FONT_NAME, 9)
    p.drawString(40, footer_y + 45, "【お振込先口座】")

    p.setFillColor(TEXT_DARK)
    p.setFont(FONT_NAME, 8.5)
    y_b = footer_y + 32
    for line in bank_info.split("\n"):
        p.drawString(50, y_b, line)
        y_b -= 11

    p.setFillColor(PRIMARY_COLOR)
    p.setFont(FONT_NAME, 9)
    p.drawString(width / 2 + 10, footer_y + 45, "【備考】")

    p.setStrokeColor(BORDER_COLOR)
    p.setFillColor(BG_LIGHT)
    p.rect(
        width / 2 + 10, footer_y - 10, width / 2 - 50, 52, fill=1, stroke=1
    )

    p.setFillColor(TEXT_DARK)
    p.setFont(FONT_NAME, 8.5)
    y_rem = footer_y + 30
    for line in remarks_text.split("\n"):
        p.drawString(width / 2 + 18, y_rem, line)
        y_rem -= 11

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer


# --------------------------------------------------
# 7. メインUI画面（3タブ切り替え対応）
# --------------------------------------------------
col1, col2, col3 = st.columns(3)

with col1:
    start_date = st.date_input(
        "対象期間の開始日", datetime.date(2017, 6, 1)
    )
with col2:
    end_date = st.date_input("対象期間の終了日", datetime.date(2017, 6, 30))
with col3:
    target_month_str = st.text_input("請求書表記 / 対象月", "2017年6月分")

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["📄 期間請求書発行", "📦 仕入れ台帳管理", "⚠️ 未納・未完了アラート"])

# ==========================================
# タブ 1: 期間請求書発行
# ==========================================
with tab1:
    ui_remarks = st.text_area(
        "📝 請求書に記載する備考欄",
        value=default_remarks,
        height=80,
        key="invoice_remarks",
    )

    if st.button(
        f"「{selected_preset_name}」から請求データを取得・作成する",
        type="primary",
        key="btn_invoice",
    ):
        if not api_key:
            st.error("👈 左側のサイドバーにAPIキーを設定してください。")
        else:
            with st.spinner(f"「{selected_preset_name}」のデータを取得中..."):
                res_data = fetch_pocket_records(
                    api_key, app_id=current_preset["app_id"],
                    start_date=start_date, end_date=end_date, preset=current_preset, mode="invoice"
                )

                if res_data:
                    records = res_data.get("records", res_data.get("data", []))
                    customer_invoices = filter_and_group_by_customer_pocket(
                        records, start_date, end_date, current_preset
                    )

                    if customer_invoices:
                        st.session_state["customer_invoices"] = customer_invoices
                        st.session_state["target_month_str"] = target_month_str
                        st.session_state["ui_remarks"] = ui_remarks
                        st.success(
                            f"集計完了！ {len(customer_invoices)} 社分の請求データを作成しました。"
                        )
                    else:
                        st.session_state["customer_invoices"] = None
                        st.warning("指定期間に該当する請求データが見つかりませんでした。")

    if "customer_invoices" in st.session_state and st.session_state["customer_invoices"]:
        invs = st.session_state["customer_invoices"]
        t_month = st.session_state.get("target_month_str", "2017年6月分")
        current_remarks = st.session_state.get("ui_remarks", default_remarks)

        st.markdown("---")
        st.markdown("### 📊 全会社 集計レポート")

        total_companies = len(invs)
        total_items_count = sum(data["件数"] for data in invs.values())
        grand_subtotal = sum(data["税別小計"] for data in invs.values())
        grand_tax = sum(data["消費税"] for data in invs.values())
        grand_total = sum(data["税込合計"] for data in invs.values())

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("請求先企業数", f"{total_companies} 社")
        m2.metric("総明細行数", f"{total_items_count} 件")
        m3.metric("合計金額（税別）", f"￥{grand_subtotal:,}")
        m4.metric("合計金額（税込）", f"￥{grand_total:,}")

        summary_list = [
            {
                "顧客名": cust_name,
                "明細件数": d["件数"],
                "税別小計": f"￥{d['税別小計']:,}",
                "消費税(10%)": f"￥{d['消費税']:,}",
                "税込合計": f"￥{d['税込合計']:,}",
            }
            for cust_name, d in invs.items()
        ]
        st.dataframe(pd.DataFrame(summary_list), use_container_width=True)

        st.markdown("---")
        st.markdown("### 📄 顧客別 期間請求書 PDFダウンロード")

        cols = st.columns(2)
        for idx, (customer_name, inv_data) in enumerate(invs.items()):
            sub_ex = inv_data["税別小計"]
            total_inc = inv_data["税込合計"]
            count = inv_data["件数"]

            pdf_buffer = generate_period_invoice_pdf(
                customer_name,
                inv_data,
                t_month,
                issuer_info,
                bank_info,
                current_remarks,
            )

            with cols[idx % 2]:
                with st.expander(
                    f"🏢 {customer_name} （請求額: ￥{total_inc:,} / 明細: {count}件）",
                    expanded=True,
                ):
                    st.write(f"**税別小計:** ￥{sub_ex:,} ｜ **税込合計:** ￥{total_inc:,}")
                    st.dataframe(pd.DataFrame(inv_data["明細"]), use_container_width=True)

                    st.download_button(
                        label=f"⬇️ {customer_name} の請求書PDFをダウンロード",
                        data=pdf_buffer,
                        file_name=f"請求書_{customer_name}_{t_month}.pdf",
                        mime="application/pdf",
                        key=f"dl_pdf_{customer_name}_{idx}",
                    )


# ==========================================
# タブ 2: 仕入れ台帳管理
# ==========================================
with tab2:
    st.markdown("### 📦 仕入れ台帳・CSV出力")
    st.write("指定された期間のデータを取得し、仕入先ごとに「数量 × 仕入れ単価」で計算した仕入れ台帳を表示・CSV出力します。")

    if st.button(
        f"「{selected_preset_name}」から仕入れデータを取得・集計する",
        type="primary",
        key="btn_supplier",
    ):
        if not api_key:
            st.error("👈 左側のサイドバーにAPIキーを設定してください。")
        else:
            with st.spinner(f"「{selected_preset_name}」のデータを取得中..."):
                res_data = fetch_pocket_records(
                    api_key, app_id=current_preset["app_id"],
                    start_date=start_date, end_date=end_date, preset=current_preset, mode="invoice"
                )

                if res_data:
                    records = res_data.get("records", res_data.get("data", []))
                    supplier_ledgers = filter_and_group_by_supplier_pocket(
                        records, start_date, end_date, current_preset
                    )

                    if supplier_ledgers:
                        st.session_state["supplier_ledgers"] = supplier_ledgers
                        st.success(
                            f"集計完了！ {len(supplier_ledgers)} 社分の仕入れ先データを集計しました。"
                        )
                    else:
                        st.session_state["supplier_ledgers"] = None
                        st.warning("指定期間に該当する仕入れデータが見つかりませんでした。")

    if "supplier_ledgers" in st.session_state and st.session_state["supplier_ledgers"]:
        ledgers = st.session_state["supplier_ledgers"]

        st.markdown("---")
        st.markdown("### 📊 仕入れ先別 サマリー")

        total_suppliers = len(ledgers)
        total_cost_sum = sum(data["仕入合計"] for data in ledgers.values())

        c1, c2 = st.columns(2)
        c1.metric("仕入先企業数", f"{total_suppliers} 社")
        c2.metric("総仕入れ金額", f"￥{total_cost_sum:,}")

        supp_summary_list = [
            {
                "仕入れ先": supp_name,
                "明細件数": d["件数"],
                "仕入金額合計": f"￥{d['仕入合計']:,}",
            }
            for supp_name, d in ledgers.items()
        ]
        st.dataframe(pd.DataFrame(supp_summary_list), use_container_width=True)

        st.markdown("---")
        st.markdown("### 📥 仕入れ先別 CSVダウンロード")

        for supp_name, supp_data in ledgers.items():
            df_supp = pd.DataFrame(supp_data["明細"])
            csv_data = df_supp.to_csv(index=False).encode("utf-8-sig")

            with st.expander(f"📦 {supp_name} （仕入合計: ￥{supp_data['仕入合計']:,} / 件数: {supp_data['件数']}件）"):
                st.dataframe(df_supp, use_container_width=True)
                st.download_button(
                    label=f"⬇️ {supp_name} の仕入れ台帳CSVをダウンロード",
                    data=csv_data,
                    file_name=f"仕入れ台帳_{supp_name}_{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    key=f"dl_csv_{supp_name}",
                )


# ==========================================
# タブ 3: 未納・未完了アラート管理
# ==========================================
with tab3:
    st.markdown("### ⚠️ 未納・未完了アラート（受注日ベース）")
    st.write("指定された期間内に**受注**されたものの、**納品日がまだ入力されていない（未納）**案件を仕入れ先ごとに抽出し、リスト化します。")

    if st.button(
        f"「{selected_preset_name}」から未納データをチェックする",
        type="primary",
        key="btn_alert",
    ):
        if not api_key:
            st.error("👈 左側のサイドバーにAPIキーを設定してください。")
        else:
            with st.spinner(f"「{selected_preset_name}」のデータを取得中..."):
                res_data = fetch_pocket_records(
                    api_key, app_id=current_preset["app_id"],
                    start_date=start_date, end_date=end_date, preset=current_preset, mode="alert"
                )

                if res_data:
                    records = res_data.get("records", res_data.get("data", []))
                    unfulfilled_dict = filter_unfulfilled_orders(
                        records, start_date, end_date, current_preset
                    )

                    if unfulfilled_dict:
                        st.session_state["unfulfilled_dict"] = unfulfilled_dict
                        st.success(
                            f"チェック完了！ {len(unfulfilled_dict)} 社の仕入れ先に未納・未完了の案件があります。"
                        )
                    else:
                        st.session_state["unfulfilled_dict"] = None
                        st.success("素晴らしい！指定期間内の受注で未納（納品日未入力）の案件はありませんでした。")

    if "unfulfilled_dict" in st.session_state and st.session_state["unfulfilled_dict"]:
        unful_data = st.session_state["unfulfilled_dict"]

        st.markdown("---")
        st.markdown("### 🚨 未納・未完了 件数サマリー")

        total_unful_suppliers = len(unful_data)
        total_unful_items = sum(d["件数"] for d in unful_data.values())

        u1, u2 = st.columns(2)
        u1.metric("未納がある仕入先数", f"{total_unful_suppliers} 社")
        u2.metric("未納の総件数", f"{total_unful_items} 件")

        unful_summary_list = [
            {
                "仕入れ先": supp_name,
                "未納件数": d["件数"],
            }
            for supp_name, d in unful_data.items()
        ]
        st.dataframe(pd.DataFrame(unful_summary_list), use_container_width=True)

        st.markdown("---")
        st.markdown("### 📥 仕入れ先別 未納リスト（送付用）CSVダウンロード")
        st.write("各仕入れ先ごとに、未納となっている案件のリストをCSVでダウンロードできます。そのままメール添付等によるリスト送付にご活用いただけます。")

        for supp_name, supp_info in unful_data.items():
            df_unful = pd.DataFrame(supp_info["明細"])
            csv_unful_data = df_unful.to_csv(index=False).encode("utf-8-sig")

            with st.expander(f"⚠️ {supp_name} （未納件数: {supp_info['件数']}件）", expanded=True):
                st.dataframe(df_unful, use_container_width=True)
                st.download_button(
                    label=f"⬇️ {supp_name} の未納リストCSVをダウンロード",
                    data=csv_unful_data,
                    file_name=f"未納リスト_{supp_name}_{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    key=f"dl_csv_unful_{supp_name}",
                )