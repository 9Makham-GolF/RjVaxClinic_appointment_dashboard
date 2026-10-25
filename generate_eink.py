#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ระบบสร้างภาพใบนัดประจำวันสำหรับจอ E-Ink 4.2 นิ้ว (400x300 px) คลินิกวัคซีนผู้ใหญ่ครบวงจร รพ.ราชวิถี
- รองรับการอ่านสถานะล่าสุดจาก clinic_state.json (วันเปิดทำการเฉพาะกิจ, วันหยุดที่เพิ่ม/แก้ไข/ลบ, โหมดเกลี่ยวันนัด)
- ใช้ฟอนต์ Google Sarabun คมชัดสูง (Crisp E-Ink Rendering)
- ส่งออกไฟล์ today.bmp (24-bit BMP สำหรับจอ 3 สี ดำ/ขาว/แดง), today_bw.bmp (1-bit BMP ขาวดำ) และ today.png
"""

import os
import sys
import json
import argparse
import datetime
import calendar
from PIL import Image, ImageDraw, ImageFont

FIXED_SOLAR_HOLIDAYS = [
    (1, 1, 'วันขึ้นปีใหม่'),
    (4, 6, 'วันจักรี'),
    (4, 13, 'วันสงกรานต์'),
    (4, 14, 'วันสงกรานต์'),
    (4, 15, 'วันสงกรานต์'),
    (5, 1, 'วันแรงงานแห่งชาติ'),
    (5, 4, 'วันฉัตรมงคล'),
    (6, 3, 'วันเฉลิมพระชนมพรรษาสมเด็จพระนางเจ้าฯ พระบรมราชินี'),
    (7, 28, 'วันเฉลิมพระชนมพรรษาพระบาทสมเด็จพระเจ้าอยู่หัว'),
    (8, 12, 'วันแม่แห่งชาติ / วันเฉลิมพระชนมพรรษาสมเด็จพระพันปีหลวง'),
    (10, 13, 'วันนวมินทรมหาราช'),
    (10, 23, 'วันปิยมหาราช'),
    (12, 5, 'วันพ่อแห่งชาติ / วันคล้ายวันพระบรมราชสมภพ ร.9'),
    (12, 10, 'วันรัฐธรรมนูญ'),
    (12, 31, 'วันสิ้นปี'),
]

KNOWN_MOVABLE_HOLIDAYS = {
    2025: [
        ('2025-02-12', 'วันมาฆบูชา'),
        ('2025-05-09', 'วันพืชมงคล'),
        ('2025-05-11', 'วันวิสาขบูชา'),
        ('2025-07-10', 'วันอาสาฬหบูชา'),
        ('2025-07-11', 'วันเข้าพรรษา'),
    ],
    2026: [
        ('2026-01-02', 'วันหยุดพิเศษเทศกาลปีใหม่ (มติ ครม.)'),
        ('2026-03-03', 'วันมาฆบูชา'),
        ('2026-05-13', 'วันพืชมงคลจรดพระนังคัลแรกนาขวัญ'),
        ('2026-05-31', 'วันวิสาขบูชา'),
        ('2026-07-29', 'วันอาสาฬหบูชา'),
        ('2026-07-30', 'วันเข้าพรรษา'),
    ],
    2027: [
        ('2027-02-21', 'วันมาฆบูชา'),
        ('2027-05-10', 'วันพืชมงคล'),
        ('2027-05-20', 'วันวิสาขบูชา'),
        ('2027-07-18', 'วันอาสาฬหบูชา'),
        ('2027-07-19', 'วันเข้าพรรษา'),
    ],
    2028: [
        ('2028-02-10', 'วันมาฆบูชา'),
        ('2028-05-08', 'วันวิสาขบูชา'),
        ('2028-05-12', 'วันพืชมงคล'),
        ('2028-07-06', 'วันอาสาฬหบูชา'),
        ('2028-07-07', 'วันเข้าพรรษา'),
    ],
    2029: [
        ('2029-02-28', 'วันมาฆบูชา'),
        ('2029-05-11', 'วันพืชมงคล'),
        ('2029-05-27', 'วันวิสาขบูชา'),
        ('2029-07-26', 'วันอาสาฬหบูชา'),
        ('2029-07-27', 'วันเข้าพรรษา'),
    ],
    2030: [
        ('2030-02-17', 'วันมาฆบูชา'),
        ('2030-05-10', 'วันพืชมงคล'),
        ('2030-05-16', 'วันวิสาขบูชา'),
        ('2030-07-15', 'วันอาสาฬหบูชา'),
        ('2030-07-16', 'วันเข้าพรรษา'),
    ]
}

THAI_MONTHS_SHORT = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']
THAI_DAYS_INITIAL = ['จ.', 'อ.', 'พ.', 'พฤ.', 'ศ.', 'ส.', 'อา.']
THAI_DAYS_FULL = ['จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์']

def load_clinic_state(state_path='clinic_state.json'):
    if os.path.exists(state_path):
        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: could not parse {state_path}: {e}")
    return {}

def build_holidays_db(clinic_state=None, start_year=2025, end_year=2031):
    hols = {}
    for y in range(start_year, end_year + 1):
        for m, d, name in FIXED_SOLAR_HOLIDAYS:
            dt = datetime.date(y, m, d)
            hols[dt] = name
            if dt.weekday() == 5:
                hols[dt + datetime.timedelta(days=2)] = f'วันหยุดชดเชย{name}'
            elif dt.weekday() == 6:
                hols[dt + datetime.timedelta(days=1)] = f'วันหยุดชดเชย{name}'
        if y in KNOWN_MOVABLE_HOLIDAYS:
            for s, name in KNOWN_MOVABLE_HOLIDAYS[y]:
                dt = datetime.date.fromisoformat(s)
                hols[dt] = name
                if dt.weekday() == 5:
                    hols[dt + datetime.timedelta(days=2)] = f'วันหยุดชดเชย{name}'
                elif dt.weekday() == 6:
                    hols[dt + datetime.timedelta(days=1)] = f'วันหยุดชดเชย{name}'

    if clinic_state:
        # Remove deleted holidays
        for item in clinic_state.get('deletedHolidays', []):
            d_str = item.get('date') if isinstance(item, dict) else str(item)
            try:
                dt = datetime.date.fromisoformat(d_str)
                hols.pop(dt, None)
            except Exception:
                pass
        # Apply modified holidays
        for item in clinic_state.get('modifiedHolidays', []):
            if isinstance(item, dict) and item.get('date') and item.get('name'):
                try:
                    dt = datetime.date.fromisoformat(item['date'])
                    hols[dt] = item['name']
                except Exception:
                    pass
        # Apply custom added holidays
        for item in clinic_state.get('customAddedHolidays', []):
            if isinstance(item, dict) and item.get('date') and item.get('name'):
                try:
                    dt = datetime.date.fromisoformat(item['date'])
                    hols[dt] = item['name']
                except Exception:
                    pass
    return hols

def add_months_clamped(d, months):
    year = d.year + (d.month + months - 1) // 12
    month = (d.month + months - 1) % 12 + 1
    max_day = calendar.monthrange(year, month)[1]
    return datetime.date(year, month, min(d.day, max_day))

def format_thai_short(d):
    if not d:
        return '-'
    be_short = str(d.year + 543)[-2:]
    return f"{d.day} {THAI_MONTHS_SHORT[d.month - 1]} {be_short}"

def get_monday_of_week(d):
    return d - datetime.timedelta(days=d.weekday())

def calculate_balanced_appointments_for_date(target_date, holidays_db, adhoc_open_set, balance_mode='max_2'):
    mon = get_monday_of_week(target_date)
    week_dates = [mon + datetime.timedelta(days=i) for i in range(5)]
    if target_date not in week_dates:
        week_dates.append(target_date)
        week_dates.sort()

    max_allowed = 2 if balance_mode == 'max_2' else (1 if balance_mode == 'max_1' else 999)

    intervals_long = [
        ('1d', '1 เดือน (1 ด.)', 1, 'month'),
        ('2d', '2 เดือน (2 ด.)', 2, 'month'),
        ('3d', '3 เดือน (3 ด.)', 3, 'month'),
        ('6d', '6 เดือน (6 ด.)', 6, 'month'),
        ('1y', '1 ปี (1 ปี)',    12, 'month'),
    ]
    fu_intervals = [
        ('fu1', 'ครั้งที่ 1 (3-5 วัน)', 3, 'day'),
        ('fu2', 'ครั้งที่ 2 (10-14 วัน)', 10, 'day'),
    ]

    def is_non_working(d):
        if d.weekday() in (5, 6):
            return True, 'วันเสาร์-อาทิตย์'
        if d in holidays_db:
            return True, holidays_db[d]
        return False, None

    def is_base_closed(d):
        iso = d.isoformat()
        is_wknd = d.weekday() in (5, 6)
        is_hol = d in holidays_db
        if (is_wknd or is_hol) and (iso not in adhoc_open_set):
            reason = holidays_db.get(d) or ('วันเสาร์' if d.weekday() == 5 else 'วันอาทิตย์')
            return True, reason
        return False, None

    closed_target, closed_reason = is_base_closed(target_date)
    if closed_target:
        return {
            'is_holiday': True,
            'holiday_name': closed_reason,
            'is_adhoc_open': False
        }

    is_adhoc_target = (target_date.weekday() in (5, 6) or target_date in holidays_db) and (target_date.isoformat() in adhoc_open_set)

    long_results = []
    for key, lbl, val, itype in intervals_long:
        usage_count = {}
        target_res = None
        for b_date in week_dates:
            closed, _ = is_base_closed(b_date)
            if closed:
                continue
            unadj = add_months_clamped(b_date, val)
            cur = unadj
            if cur.day < b_date.day:
                max_d = calendar.monthrange(cur.year, cur.month)[1]
                cur = datetime.date(cur.year, cur.month, min(b_date.day, max_d))
            shifted = False
            balanced = False
            while True:
                nw, _ = is_non_working(cur)
                if nw:
                    shifted = True
                    cur += datetime.timedelta(days=1)
                    continue
                if balance_mode != 'none' and usage_count.get(cur, 0) >= max_allowed:
                    shifted = True
                    balanced = True
                    cur += datetime.timedelta(days=1)
                    continue
                break
            usage_count[cur] = usage_count.get(cur, 0) + 1
            if b_date == target_date:
                day_thai = THAI_DAYS_FULL[cur.weekday()]
                suffix = " (เกลี่ย)" if balanced else (" (เลื่อน)" if shifted else "")
                target_res = {
                    'label': lbl,
                    'date': cur,
                    'date_str': format_thai_short(cur),
                    'day_str': f"{day_thai}{suffix}",
                    'shifted': shifted,
                    'balanced': balanced
                }
        if target_res:
            long_results.append(target_res)

    fu_results = []
    for key, lbl, days, itype in fu_intervals:
        usage_count = {}
        target_res = None
        for b_date in week_dates:
            closed, _ = is_base_closed(b_date)
            if closed:
                continue
            cur = b_date + datetime.timedelta(days=days)
            shifted = False
            while True:
                nw, _ = is_non_working(cur)
                if nw or (balance_mode != 'none' and usage_count.get(cur, 0) >= max_allowed):
                    shifted = True
                    cur += datetime.timedelta(days=1)
                    continue
                break
            usage_count[cur] = usage_count.get(cur, 0) + 1
            if b_date == target_date:
                target_res = {
                    'label': lbl,
                    'date': cur,
                    'date_str': format_thai_short(cur),
                    'shifted': shifted
                }
        if target_res:
            fu_results.append(target_res)

    return {
        'is_holiday': False,
        'is_adhoc_open': is_adhoc_target,
        'long_terms': long_results,
        'follow_ups': fu_results
    }

def render_eink_image(base_date, data, font_dir='fonts'):
    W, H = 400, 300
    img = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    font_bold_path = os.path.join(font_dir, 'Sarabun-Bold.ttf')
    font_reg_path = os.path.join(font_dir, 'Sarabun-Regular.ttf')
    if not os.path.exists(font_bold_path):
        font_bold_path = '/usr/share/fonts/truetype/noto/NotoSansThai-Bold.ttf'
        font_reg_path = '/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf'

    font_hdr = ImageFont.truetype(font_bold_path, 20)
    font_hdr_sub = ImageFont.truetype(font_bold_path, 12)
    font_label = ImageFont.truetype(font_bold_path, 18)
    font_date = ImageFont.truetype(font_bold_path, 23)
    font_day = ImageFont.truetype(font_reg_path, 13)
    font_fu_title = ImageFont.truetype(font_bold_path, 12)
    font_fu_lbl = ImageFont.truetype(font_reg_path, 12)
    font_fu_val = ImageFont.truetype(font_bold_path, 15)

    RED = (220, 20, 20)
    BLACK = (0, 0, 0)
    WHITE = (255, 255, 255)
    GRAY = (90, 90, 90)
    LIGHT_BG = (248, 250, 252)

    day_initial = THAI_DAYS_INITIAL[base_date.weekday()]
    day_name = THAI_DAYS_FULL[base_date.weekday()]
    be_year = base_date.year + 543
    header_str = f"({day_initial}) {base_date.day} {THAI_MONTHS_SHORT[base_date.month - 1]} {be_year}  วัน{day_name}"

    if data['is_holiday']:
        draw.rectangle([(0, 0), (W, H)], fill=WHITE)
        draw.rectangle([(18, 24), (W - 18, H - 24)], outline=RED, width=4)
        draw.rectangle([(18, 24), (W - 18, 82)], fill=RED)
        draw.text((30, 38), header_str, font=font_hdr, fill=WHITE)
        draw.text((42, 110), "⛔ วันหยุดทำการ", font=ImageFont.truetype(font_bold_path, 30), fill=RED)
        draw.text((42, 162), str(data['holiday_name'])[:32], font=ImageFont.truetype(font_bold_path, 20), fill=BLACK)
        draw.text((42, 206), "(ปิดทำการ / งดนัดหมายประจำวัน)", font=ImageFont.truetype(font_reg_path, 15), fill=GRAY)
        draw.text((42, 242), "คลินิกวัคซีนผู้ใหญ่ครบวงจร รพ.ราชวิถี", font=ImageFont.truetype(font_bold_path, 13), fill=RED)
        return img

    # Top Red Header Bar
    draw.rectangle([(0, 0), (W, 42)], fill=RED)
    draw.text((10, 8), header_str, font=font_hdr, fill=WHITE)
    sub_tag = "เปิดเฉพาะกิจ" if data.get('is_adhoc_open') else "รพ.ราชวิถี"
    draw.text((318, 13), sub_tag, font=font_hdr_sub, fill=WHITE)

    y_cur = 46
    row_height = 37

    for i, item in enumerate(data['long_terms']):
        if i % 2 == 1:
            draw.rectangle([(4, y_cur), (W - 4, y_cur + row_height - 1)], fill=LIGHT_BG)
        draw.text((12, y_cur + 5), item['label'], font=font_label, fill=BLACK)
        draw.text((150, y_cur + 4), "➔", font=font_label, fill=GRAY)
        draw.text((178, y_cur + 2), item['date_str'], font=font_date, fill=BLACK)

        if item['shifted']:
            draw.rounded_rectangle([(300, y_cur + 7), (392, y_cur + 27)], radius=3, fill=RED)
            draw.text((306, y_cur + 8), item['day_str'], font=ImageFont.truetype(font_bold_path, 11), fill=WHITE)
        else:
            draw.text((306, y_cur + 9), f"({item['day_str']})", font=font_day, fill=GRAY)

        draw.line([(8, y_cur + row_height - 1), (W - 8, y_cur + row_height - 1)], fill=(220, 220, 220), width=1)
        y_cur += row_height

    # Bottom Section: Follow-up Symptoms
    draw.line([(0, 233), (W, 233)], fill=BLACK, width=2)
    draw.rectangle([(0, 235), (W, 299)], fill=(246, 246, 246))
    draw.text((12, 237), "🩺 ติดตามอาการ (คลินิกวัคซีนผู้ใหญ่ รพ.ราชวิถี):", font=font_fu_title, fill=BLACK)

    fu1 = data['follow_ups'][0]
    draw.rounded_rectangle([(10, 256), (196, 293)], radius=4, outline=RED, width=1, fill=WHITE)
    draw.text((16, 264), "ครั้งที่ 1 (3-5ว.):", font=font_fu_lbl, fill=BLACK)
    draw.text((105, 262), fu1['date_str'], font=font_fu_val, fill=RED)

    fu2 = data['follow_ups'][1]
    draw.rounded_rectangle([(204, 256), (390, 293)], radius=4, outline=RED, width=1, fill=WHITE)
    draw.text((210, 264), "ครั้งที่ 2 (10-14ว.):", font=font_fu_lbl, fill=BLACK)
    draw.text((300, 262), fu2['date_str'], font=font_fu_val, fill=RED)

    draw.rectangle([(0, 0), (W - 1, H - 1)], outline=BLACK, width=1)
    return img

def main():
    parser = argparse.ArgumentParser(description="Generate daily E-ink appointment BMP & PNG images")
    parser.add_argument('--date', type=str, default=None, help="Target date YYYY-MM-DD (Default: today Bangkok time)")
    parser.add_argument('--out-dir', type=str, default=".", help="Output directory")
    parser.add_argument('--fonts-dir', type=str, default="fonts", help="Fonts directory")
    parser.add_argument('--state-file', type=str, default="clinic_state.json", help="Path to shared clinic_state.json")
    args = parser.parse_args()

    tz = datetime.timezone(datetime.timedelta(hours=7))
    if args.date:
        target_date = datetime.date.fromisoformat(args.date)
    else:
        target_date = datetime.datetime.now(tz).date()

    clinic_state = load_clinic_state(args.state_file)
    holidays_db = build_holidays_db(clinic_state)
    adhoc_open_set = set(clinic_state.get('adhocOpenDates', []))
    balance_mode = clinic_state.get('balanceMode', 'max_2')

    print(f"Generating E-Ink image for {target_date} (balanceMode={balance_mode}, adhocOpen={len(adhoc_open_set)})")
    data = calculate_balanced_appointments_for_date(target_date, holidays_db, adhoc_open_set, balance_mode=balance_mode)
    img = render_eink_image(target_date, data, font_dir=args.fonts_dir)

    os.makedirs(args.out_dir, exist_ok=True)
    bmp_path = os.path.join(args.out_dir, "today.bmp")
    bmp_bw_path = os.path.join(args.out_dir, "today_bw.bmp")
    png_path = os.path.join(args.out_dir, "today.png")

    # Save 24-bit RGB BMP (for 3-color E-Ink displays), 1-bit monochrome BMP, and PNG preview
    img.save(bmp_path, "BMP")
    img_bw = img.convert("L").point(lambda p: 255 if p > 180 else 0, mode="1")
    img_bw.save(bmp_bw_path, "BMP")
    img.save(png_path, "PNG")
    print(f"Saved: {bmp_path} ({os.path.getsize(bmp_path)} bytes), {bmp_bw_path} ({os.path.getsize(bmp_bw_path)} bytes), {png_path}")

if __name__ == '__main__':
    main()
