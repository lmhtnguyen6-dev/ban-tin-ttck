# -*- coding: utf-8 -*-
"""
scraper.py — Bản tin TTCK lọc bằng AI (Hybrid: code + Gemini)
=============================================================
Luồng xử lý:
    1. Lấy tin từ nhiều nguồn RSS tiếng Việt (CafeF, VnExpress, Vietstock, VietnamBiz).
    2. [CODE] Lọc thô MIỄN PHÍ: chỉ 24h gần nhất, chỉ tiếng Việt, loại nhóm tin nhiễu
       rõ ràng (quảng cáo, hình sự, lễ hội, giao thông, giá vàng hằng ngày...).
    3. [CODE] Gộp tin trùng theo tiêu đề + gộp loạt bài định kỳ (chỉ khác ngày/tháng).
    4. [AI - Gemini] Gọi 1 LẦN cho cả lô tin ứng viên để:
         - chấm "có tác động trực tiếp đến TTCK Việt Nam / 1 ngành / 1 DN niêm yết?"
         - cho điểm tác động 0-10, gán chủ đề, nêu lý do ngắn, đoán sắc thái,
         - gom các tin CÙNG SỰ KIỆN (gộp trùng theo NGHĨA, kể cả câu chữ khác nhau).
    5. Chọn tin điểm cao nhất -> ghi data.json -> web tĩnh hiển thị.

ĐƯỜNG LUI AN TOÀN (fallback): nếu KHÔNG có GEMINI_API_KEY, hoặc Gemini lỗi/hết lượt
free, chương trình TỰ ĐỘNG chấm điểm bằng CODE THUẦN (như web cũ) để bản tin không
bao giờ trống. data.json ghi rõ "che_do": "ai" hay "code" để biết lần chạy dùng cách nào.

Cách chạy thủ công (test trên máy):
    pip install -r requirements.txt
    python scraper.py                 # không có key -> chạy code thuần
    $env:GEMINI_API_KEY="..."         # (PowerShell) có key -> chạy AI
    python scraper.py
"""

import json
import os
import re
import html
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

import feedparser
import requests


# ===========================================================================
# 1. NGUỒN RSS (CHỈ TIẾNG VIỆT) — đã kiểm chứng trả về tin
# ===========================================================================
#   ten     : tên hiển thị
#   url     : URL feed
#   khu_vuc : "vn" (tin trong nước) hoặc "quoc_te" (tin quốc tế viết bằng TV)
RSS_SOURCES = [
    # ----- CafeF -----
    {"ten": "CafeF Chứng khoán", "url": "https://cafef.vn/thi-truong-chung-khoan.rss", "khu_vuc": "vn"},
    {"ten": "CafeF Doanh nghiệp", "url": "https://cafef.vn/doanh-nghiep.rss", "khu_vuc": "vn"},
    {"ten": "CafeF Tài chính", "url": "https://cafef.vn/tai-chinh-ngan-hang.rss", "khu_vuc": "vn"},
    {"ten": "CafeF Vĩ mô", "url": "https://cafef.vn/vi-mo-dau-tu.rss", "khu_vuc": "vn"},
    {"ten": "CafeF Tài chính quốc tế", "url": "https://cafef.vn/tai-chinh-quoc-te.rss", "khu_vuc": "quoc_te"},

    # ----- VnExpress -----
    {"ten": "VnExpress Kinh doanh", "url": "https://vnexpress.net/rss/kinh-doanh.rss", "khu_vuc": "vn"},
    {"ten": "VnExpress Thế giới", "url": "https://vnexpress.net/rss/the-gioi.rss", "khu_vuc": "quoc_te"},

    # ----- Vietstock -----
    {"ten": "Vietstock Kinh tế", "url": "https://vietstock.vn/761/kinh-te.rss", "khu_vuc": "vn"},
    {"ten": "Vietstock Thế giới", "url": "https://vietstock.vn/772/the-gioi.rss", "khu_vuc": "quoc_te"},

    # ----- VietnamBiz ----- (slug chứng khoán/vĩ mô cũ đã chết; dùng các feed còn sống)
    {"ten": "VietnamBiz Thị trường", "url": "https://vietnambiz.vn/thi-truong.rss", "khu_vuc": "vn"},
    {"ten": "VietnamBiz Tài chính", "url": "https://vietnambiz.vn/rss/tai-chinh.rss", "khu_vuc": "vn"},
    {"ten": "VietnamBiz Hàng hóa", "url": "https://vietnambiz.vn/hang-hoa.rss", "khu_vuc": "vn"},

    # ----- Báo Đầu tư -----
    # Chưa tìm được RSS còn sống; khi họ mở lại, bỏ dấu # và thay URL đúng:
    # {"ten": "Báo Đầu tư", "url": "https://baodautu.vn/rss/tai-chinh-chung-khoan.rss", "khu_vuc": "vn"},
]


# ===========================================================================
# 2. LỌC TIN "NHIỄU" BẰNG CODE (bước lọc thô MIỄN PHÍ, trước khi gọi AI)
# ===========================================================================
# Loại thẳng các tin chắc chắn không liên quan thị trường -> giảm số tin phải đưa cho
# AI (tiết kiệm lượt gọi free). AI sẽ lọc tinh phần còn lại.
NHOM_TIN_NHIEU = {
    "quang_cao": [
        "trọn đời", "đăng ký một lần", "hoàn tiền", "mở thẻ", "trả góp",
        "quà tặng", "tri ân", "cashback", "khuyến mãi", "ưu đãi lãi suất",
        "ra mắt gói", "hoàn phí", "tặng ngay", "voucher", "quay số trúng thưởng",
    ],
    "hinh_su": [
        "truy tìm", "truy nã", "bị bắt", "khởi tố", "lừa đảo", "chiếm đoạt",
        "lãnh án", "tuyên án", "bắt giam", "hầu tòa", "cáo trạng", "vòng lao lý",
        "trốn nã", "trộm", "cướp", "đánh bạc", "rửa tiền", "lỗ hổng tài khoản",
    ],
    "doi_song": [
        "nghiện mua", "nên chi tiêu", "chi tiêu thế nào", "chi tiêu ra sao",
        "quản lý chi tiêu", "quản lý tài chính cá nhân", "chi tiền vào đâu",
    ],
    "le_hoi": [
        "lễ hội", "đặc sản", "hoa hậu", "giải chạy", "cuộc thi", "khai mạc lễ",
        "ẩm thực", "du lịch hè", "check-in", "sống ảo",
    ],
    "giao_thong": [
        "tạm dừng khai thác", "phân luồng", "cấm xe", "cấm đường", "kẹt xe",
        "ùn tắc", "tai nạn giao thông", "khai thác cao tốc", "phạt nguội",
    ],
    "pr_doanh_nghiep": [
        "vinh danh", "giải thưởng", "awards", "bảng xếp hạng", "fortune",
        "được trao giải", "đạt giải", "top 500",
        "ký kết", "ký hợp tác", "hợp tác chiến lược", "biên bản ghi nhớ", "mou",
        "đồng hành", "tài trợ", "ra mắt", "core banking", "open banking",
    ],
    "nhan_su": [
        "bổ nhiệm", "miễn nhiệm", "từ nhiệm",
    ],
    "vi_mo_dia_phuong": [
        "tăng trưởng kinh tế 2 con số", "tăng trưởng 2 con số",
        "thuế thời gian", "ốc đảo ưu đãi",
    ],
}

# Các nhóm nhiễu ĐANG BẬT. Bỏ bớt tên trong list này để tắt một nhóm.
LOC_NHOM_NHIEU = ["quang_cao", "hinh_su", "le_hoi", "giao_thong", "doi_song",
                  "pr_doanh_nghiep", "nhan_su", "vi_mo_dia_phuong"]

# Tin CẬP NHẬT GIÁ VÀNG hằng ngày -> loại (vẫn giữ tin vàng vĩ mô vì không khớp cụm này).
CUM_GIA_VANG_HANG_NGAY = ["giá vàng", "vàng miếng", "vàng nhẫn", "vàng sjc"]

# Từ HAI NGHĨA: chỉ coi là nhiễu khi đi KÈM ngữ cảnh hình sự rõ ràng.
TU_HAI_NGHIA = ["cáo buộc", "gian lận"]
# KHÔNG đưa "bị cáo" vào đây (nó là substring của "bị cáo buộc" -> vô hiệu hóa bộ lọc).
NGU_CANH_HINH_SU = [
    "bị bắt", "khởi tố", "truy tố", "công an", "tòa án", "hầu tòa", "lừa đảo",
    "chiếm đoạt", "bắt giam", "truy nã", "truy tìm", "cáo trạng", "bị can", "rửa tiền",
]


def la_tu_hai_nghia_hinh_su(t: str) -> bool:
    """True nếu tiêu đề chứa từ hai nghĩa ('cáo buộc'/'gian lận') ĐI KÈM ngữ cảnh hình
    sự -> nhiễu. Nếu gắn ngữ cảnh doanh nghiệp/thị trường -> GIỮ (có thể ảnh hưởng CP)."""
    return (any(tu in t for tu in TU_HAI_NGHIA)
            and any(cum in t for cum in NGU_CANH_HINH_SU))


def la_tin_nhieu(tieu_de: str):
    """Trả về (True, tên_nhóm) nếu tiêu đề là tin nhiễu cần loại, ngược lại (False, "")."""
    t = tieu_de.lower()
    if any(cum in t for cum in CUM_GIA_VANG_HANG_NGAY):
        return True, "gia_vang_hang_ngay"
    if "hinh_su" in LOC_NHOM_NHIEU and la_tu_hai_nghia_hinh_su(t):
        return True, "hinh_su"
    for ten_nhom in LOC_NHOM_NHIEU:
        for cum in NHOM_TIN_NHIEU.get(ten_nhom, []):
            if cum in t:
                return True, ten_nhom
    return False, ""


# ===========================================================================
# 3. BỘ TỪ KHÓA & CHỦ ĐỀ (dùng cho ĐƯỜNG LUI code-thuần khi không có AI)
# ===========================================================================
TRONG_SO_TU_KHOA = {
    # Chứng khoán & thị trường
    "vn-index": 6, "vnindex": 6, "vn30": 5, "chứng khoán": 5, "cổ phiếu": 5,
    "hose": 4, "hnx": 3, "upcom": 3, "niêm yết": 4,
    "trái phiếu": 3, "khối ngoại": 5, "thanh khoản": 3,
    # Hoạt động doanh nghiệp trên sàn
    "cổ tức": 4, "trả cổ tức": 4, "chia cổ tức": 4,
    "phát hành cổ phiếu": 5, "chào bán cổ phiếu": 5, "phát hành riêng lẻ": 4,
    "cổ phiếu quỹ": 4, "mua lại cổ phiếu": 4,
    "đhđcđ": 4, "đại hội cổ đông": 4, "cổ đông lớn": 4, "thoái vốn": 4,
    "lợi nhuận": 4, "doanh thu": 2, "báo cáo tài chính": 3, "kết quả kinh doanh": 4,
    "thâu tóm": 4, "sáp nhập": 4, "m&a": 4, "ipo": 4, "vốn hóa": 3,
    # Tài chính - ngân hàng - chính sách tiền tệ
    "ngân hàng nhà nước": 4, "nhnn": 4, "lãi suất": 4, "tín dụng": 3,
    "tỷ giá": 2, "lạm phát": 3,
    # Fed & quốc tế
    "fed": 5, "fomc": 5, "powell": 4, "lãi suất mỹ": 5, "thuế quan": 3,
    # Vĩ mô VN
    "fdi": 3, "gdp": 3, "tăng trưởng": 2, "xuất khẩu": 2, "nhập khẩu": 2,
    "đầu tư công": 3, "giải ngân": 2,
    # Hàng hóa
    "giá dầu": 3, "dầu thô": 2, "opec": 2, "giá thép": 3, "cao su": 2, "giá điện": 3,
    # Khác
    "usd": 1, "bất động sản": 2, "trung quốc": 1, "trump": 2,
}

VN_MARKERS = ["vn-index", "vnindex", "hose", "hnx", "upcom", "vn30", "fdi", "nhnn", "vnd"]

# Chủ đề chuẩn của bản tin (AI phải chọn trong đúng tập này; code-thuần cũng gán vào đây).
CHU_DE_CHUAN = [
    "Chính sách & NHNN",
    "Fed & lãi suất toàn cầu",
    "Doanh nghiệp niêm yết",
    "Vĩ mô Việt Nam",
    "Hàng hóa",
    "Dòng tiền & khối ngoại",
    "Thế giới & địa chính trị",
]

# Quy tắc gán chủ đề cho ĐƯỜNG LUI code-thuần (khớp trước thì gán trước).
CHU_DE_RULES = [
    ("Fed & lãi suất toàn cầu", ["fed", "fomc", "powell", "cục dự trữ liên bang",
                                 "lãi suất mỹ", "ngân hàng trung ương mỹ", "ecb", "boj"]),
    ("Dòng tiền & khối ngoại", ["khối ngoại", "tự doanh", "thanh khoản", "dòng tiền",
                                "mua ròng", "bán ròng"]),
    ("Doanh nghiệp niêm yết", ["cổ tức", "phát hành cổ phiếu", "chào bán cổ phiếu",
                               "cổ phiếu quỹ", "mua lại cổ phiếu", "đhđcđ",
                               "đại hội cổ đông", "cổ đông lớn", "thoái vốn",
                               "lợi nhuận", "kết quả kinh doanh", "báo cáo tài chính",
                               "thâu tóm", "sáp nhập", "m&a", "ipo", "niêm yết"]),
    ("Hàng hóa", ["giá dầu", "dầu thô", "opec", "giá thép", "cao su", "giá điện",
                  "xăng dầu", "quặng", "khí đốt"]),
    ("Chính sách & NHNN", ["chính phủ", "thủ tướng", "quốc hội", "nghị định", "nghị quyết",
                           "bộ tài chính", "ngân hàng nhà nước", "nhnn", "chính sách",
                           "thông tư", "đầu tư công", "giải ngân", "quy hoạch", "luật",
                           "lãi suất", "tín dụng", "room"]),
    ("Vĩ mô Việt Nam", ["vn-index", "vnindex", "vn30", "hose", "hnx", "upcom",
                        "chứng khoán", "cổ phiếu", "tỷ giá", "vnd", "fdi",
                        "xuất khẩu", "nhập khẩu", "lạm phát", "gdp", "cpi"]),
    ("Thế giới & địa chính trị", ["mỹ", "trung quốc", "nhật", "hàn quốc", "eu", "châu âu",
                                  "phố wall", "dow jones", "nasdaq", "s&p", "thế giới",
                                  "chiến tranh", "xung đột", "trump", "cấm vận",
                                  "đài loan", "iran", "israel", "ukraine", "nga"]),
]

# Hệ số ưu tiên (chỉ dùng cho ĐƯỜNG LUI code-thuần) — đẩy tin VN & Fed lên đầu.
HE_SO_UU_TIEN = {
    "Vĩ mô Việt Nam": 2.0,
    "Doanh nghiệp niêm yết": 2.0,
    "Chính sách & NHNN": 1.8,
    "Dòng tiền & khối ngoại": 1.8,
    "Fed & lãi suất toàn cầu": 1.6,
    "Hàng hóa": 1.3,
    "Thế giới & địa chính trị": 1.0,
}


# ===========================================================================
# 4. HÀM TIỆN ÍCH
# ===========================================================================
GIO_VN = timezone(timedelta(hours=7))  # múi giờ Việt Nam (UTC+7)

KY_TU_TV = set(
    "àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợ"
    "ùúủũụưứừửữựỳýỷỹỵđ"
)


def lam_sach_text(s: str) -> str:
    """Bỏ thẻ HTML, giải mã ký tự đặc biệt, gọn khoảng trắng."""
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def chuan_hoa_de_so_sanh(tieu_de: str) -> str:
    """Chuẩn hóa tiêu đề để so trùng: chữ thường, bỏ ký tự lạ."""
    s = tieu_de.lower()
    s = re.sub(r"[^\w\s" + "".join(KY_TU_TV) + r"]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def bo_token_ngay(tieu_de: str) -> str:
    """Bỏ token ngày/tháng khỏi tiêu đề để so 'phần chữ' (gộp loạt bài định kỳ)."""
    s = tieu_de.lower()
    s = re.sub(r"\b\d{1,2}\s*[/-]\s*\d{1,2}(?:\s*[/-]\s*\d{2,4})?\b", " ", s)
    s = re.sub(r"\b(ngày|hôm nay|sáng nay|sáng|chiều nay|chiều|trưa|tối nay|tối|tuần này)\b", " ", s)
    s = re.sub(r"[^\w\s" + "".join(KY_TU_TV) + r"]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def la_tieng_viet(tieu_de: str) -> bool:
    """True nếu tiêu đề là tiếng Việt (có dấu, hoặc chứa marker tin VN)."""
    t = tieu_de.lower()
    if any(ch in KY_TU_TV for ch in t):
        return True
    if any(marker in t for marker in VN_MARKERS):
        return True
    return False


def lay_thoi_gian(entry) -> datetime:
    """Lấy thời gian đăng của entry RSS, trả về datetime có timezone (UTC)."""
    for field in ("published_parsed", "updated_parsed"):
        t = entry.get(field)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def diem_moi(gio_dang: datetime, bay_gio: datetime) -> float:
    """Điểm 'mới': 0h tuổi -> ~10 điểm; 24h tuổi -> 0 điểm."""
    tuoi_gio = (bay_gio - gio_dang).total_seconds() / 3600.0
    return round(max(0.0, 10.0 * (1 - tuoi_gio / 24.0)), 1)


def gan_chu_de_code(tieu_de: str, khu_vuc: str) -> str:
    """Gán chủ đề bằng code (đường lui). Không khớp -> theo khu vực nguồn."""
    t = tieu_de.lower()
    for chu_de, tu_khoas in CHU_DE_RULES:
        # 'Vĩ mô Việt Nam' và 'Chính sách & NHNN' chỉ áp cho nguồn trong nước
        # (từ chung dễ khớp nhầm tin quốc tế). KHÔNG chặn Fed theo khu vực.
        if chu_de in ("Vĩ mô Việt Nam", "Chính sách & NHNN") and khu_vuc != "vn":
            continue
        if any(tk in t for tk in tu_khoas):
            return chu_de
    return "Vĩ mô Việt Nam" if khu_vuc == "vn" else "Thế giới & địa chính trị"


# ===========================================================================
# 5. LẤY TIN TỪ CÁC FEED (lọc 24h + tiếng Việt + nhiễu)
# ===========================================================================
def lay_tat_ca_tin():
    """Duyệt mọi nguồn RSS, trả về danh sách tin thô đã lọc thô."""
    bay_gio = datetime.now(timezone.utc)
    gioi_han = bay_gio - timedelta(hours=24)
    tin_tho = []
    bo_vi_tieng_anh = 0
    bo_vi_nhieu = {}

    for nguon in RSS_SOURCES:
        print(f"-> Đang lấy: {nguon['ten']} ({nguon['url']})")
        try:
            feed = feedparser.parse(nguon["url"])
        except Exception as e:
            print(f"   !! Lỗi khi đọc feed: {e}")
            continue

        if not feed.entries:
            print("   (feed trống hoặc không đọc được - cân nhắc thay URL)")
            continue

        for entry in feed.entries:
            tieu_de = lam_sach_text(entry.get("title", ""))
            link = entry.get("link", "").strip()
            if not tieu_de or not link:
                continue

            if not la_tieng_viet(tieu_de):
                bo_vi_tieng_anh += 1
                continue

            nhieu, nhom_nhieu = la_tin_nhieu(tieu_de)
            if nhieu:
                bo_vi_nhieu[nhom_nhieu] = bo_vi_nhieu.get(nhom_nhieu, 0) + 1
                print(f"   [loại-{nhom_nhieu}] {tieu_de}")
                continue

            gio_dang = lay_thoi_gian(entry)
            if gio_dang < gioi_han:
                continue

            mo_ta = lam_sach_text(entry.get("summary", ""))[:300]
            tin_tho.append({
                "tieu_de": tieu_de,
                "mo_ta": mo_ta,
                "nguon": nguon["ten"],
                "khu_vuc": nguon["khu_vuc"],
                "link": link,
                "gio_dang": gio_dang,
            })

    tong_nhieu = sum(bo_vi_nhieu.values())
    print(f"=> Tổng tin thô trong 24h (tiếng Việt): {len(tin_tho)} "
          f"(đã loại {bo_vi_tieng_anh} tin không phải tiếng Việt, {tong_nhieu} tin nhiễu)")
    if bo_vi_nhieu:
        chi_tiet = ", ".join(f"{k}={v}" for k, v in sorted(bo_vi_nhieu.items()))
        print(f"   Chi tiết tin nhiễu bị loại: {chi_tiet}")
    return tin_tho


# ===========================================================================
# 6. GỘP TIN TRÙNG (theo tiêu đề) + GỘP LOẠT BÀI ĐỊNH KỲ
# ===========================================================================
def gop_tin_trung(tin_tho, nguong=0.72):
    """Gộp tin cùng sự kiện theo độ giống tiêu đề. Giữ bản mới nhất + tập nguồn."""
    nhom_list = []
    for tin in tin_tho:
        chuan = chuan_hoa_de_so_sanh(tin["tieu_de"])
        da_gop = False
        for nhom in nhom_list:
            if SequenceMatcher(None, chuan, nhom["_chuan"]).ratio() >= nguong:
                nhom["nguon_set"].add(tin["nguon"])
                if tin["gio_dang"] > nhom["gio_dang"]:
                    nhom.update({"tieu_de": tin["tieu_de"], "mo_ta": tin["mo_ta"],
                                 "gio_dang": tin["gio_dang"], "link": tin["link"],
                                 "khu_vuc": tin["khu_vuc"], "_chuan": chuan})
                da_gop = True
                break
        if not da_gop:
            nhom_list.append({
                "tieu_de": tin["tieu_de"], "mo_ta": tin["mo_ta"], "link": tin["link"],
                "gio_dang": tin["gio_dang"], "khu_vuc": tin["khu_vuc"],
                "nguon_set": {tin["nguon"]}, "_chuan": chuan,
            })
    print(f"=> Sau khi gộp trùng theo tiêu đề còn: {len(nhom_list)} nhóm tin")
    return nhom_list


def gop_bai_dinh_ky(nhom_list, nguong=0.85):
    """Gộp loạt bài chỉ khác ngày/tháng (bỏ token ngày rồi so phần chữ). Giữ bản mới nhất."""
    ket_qua = []
    bi_gop = []
    for nhom in nhom_list:
        khoa = bo_token_ngay(nhom["tieu_de"])
        trung = None
        for g in ket_qua:
            if SequenceMatcher(None, khoa, g["_khoa_ngay"]).ratio() >= nguong:
                trung = g
                break
        if trung is not None:
            trung["nguon_set"] |= nhom["nguon_set"]
            if nhom["gio_dang"] > trung["gio_dang"]:
                bi_gop.append((trung["tieu_de"], nhom["tieu_de"]))
                trung.update({"tieu_de": nhom["tieu_de"], "mo_ta": nhom["mo_ta"],
                              "gio_dang": nhom["gio_dang"], "link": nhom["link"],
                              "khu_vuc": nhom["khu_vuc"], "_khoa_ngay": khoa})
            else:
                bi_gop.append((nhom["tieu_de"], trung["tieu_de"]))
        else:
            n = dict(nhom)
            n["_khoa_ngay"] = khoa
            ket_qua.append(n)

    if bi_gop:
        print(f"=> Gộp loạt bài định kỳ: bỏ {len(bi_gop)} bản cũ, giữ bản mới nhất:")
        for bo, giu in bi_gop:
            print(f"   - BỎ : {bo}")
            print(f"     GIỮ: {giu}")
    else:
        print("=> Gộp loạt bài định kỳ: không có bài nào bị gộp.")
    print(f"=> Sau khi gộp loạt định kỳ còn: {len(ket_qua)} nhóm tin")
    return ket_qua


# ===========================================================================
# 7. [AI] CHẤM TÁC ĐỘNG TTCK + GỘP TRÙNG THEO NGHĨA bằng Gemini (1 LẦN GỌI)
# ===========================================================================
# Mô hình & key lấy từ biến môi trường để dễ đổi mà không sửa code.
# Lưu ý: GitHub Actions truyền biến chưa đặt thành CHUỖI RỖNG (không phải thiếu hẳn),
# nên dùng `or` để rơi về mặc định khi rỗng — tránh tên model rỗng làm URL Gemini hỏng.
GEMINI_API_KEY = (os.environ.get("GEMINI_API_KEY") or "").strip()
GEMINI_MODEL = (os.environ.get("GEMINI_MODEL") or "").strip() or "gemini-2.5-flash"
GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
              f"{GEMINI_MODEL}:generateContent")

# Ngưỡng điểm tác động tối thiểu để một tin được giữ lại (AI chấm 0-10).
NGUONG_TAC_DONG = 4

PROMPT_HE_THONG = """Bạn là trợ lý sàng lọc tin cho MỘT MÔI GIỚI CHỨNG KHOÁN Việt Nam.
Nhiệm vụ: với mỗi tin (tiêu đề + mô tả), đánh giá tin đó có ẢNH HƯỞNG TRỰC TIẾP đến
thị trường chứng khoán Việt Nam, một NGÀNH, hay một DOANH NGHIỆP NIÊM YẾT hay không,
rồi gom các tin NÓI VỀ CÙNG MỘT SỰ KIỆN lại.

CHỈ GIỮ tin thực sự có thể tác động giá cổ phiếu/chỉ số, ví dụ:
- Động thái Fed / ngân hàng trung ương lớn; động thái Ngân hàng Nhà nước VN (lãi suất,
  tỷ giá, tín dụng, OMO...).
- Chính sách chính phủ tác động TTCK (lãi suất, đất đai, thuế, đầu tư công, quy định mới).
- Tin doanh nghiệp niêm yết: KQKD/BCTC, cổ tức, phát hành/mua lại cổ phiếu, M&A, giao
  dịch cổ đông lớn, công bố thông tin bất thường, trúng thầu lớn...
- Giá hàng hóa ảnh hưởng DN trên sàn: dầu, thép, cao su, điện, phân bón, hóa chất...
- Chỉ số vĩ mô: lạm phát, lãi suất, tăng trưởng tín dụng, tỷ giá, FDI, xuất nhập khẩu.
- Dòng tiền: khối ngoại mua/bán ròng, tự doanh, thanh khoản thị trường.

LOẠI BỎ (gán lien_quan=false) các tin không tác động thị trường: đời sống, giải trí,
thể thao, du lịch, hình sự lặt vặt, PR/quảng cáo doanh nghiệp, lễ hội, giao thông,
nhân sự hành chính thường lệ, giá vàng bán lẻ hằng ngày.

Với MỖI tin trả về một object:
  "id": số id của tin (giữ nguyên)
  "lien_quan": true/false
  "diem_tac_dong": số nguyên 0-10 (mức tác động tới TTCK; 0 nếu không liên quan)
  "chu_de": CHỌN ĐÚNG MỘT trong: {chu_de_list}
  "ly_do": 1 câu NGẮN (<= 20 từ) giải thích vì sao tác động thị trường (tiếng Việt)
  "sac_thai": "tích cực" | "tiêu cực" | "trung tính" (với TTCK nói chung)
  "nhom": số nguyên — các tin CÙNG MỘT SỰ KIỆN phải có cùng số "nhom"

CHỈ trả về JSON hợp lệ: một mảng các object như trên, KHÔNG thêm chữ nào khác."""


def cham_diem_ai(nhom_list):
    """
    Gọi Gemini 1 LẦN cho cả lô tin ứng viên. Trả về danh sách tin đã chọn (dict theo
    schema data.json) nếu thành công, hoặc None nếu không dùng được AI (để fallback code).
    """
    if not GEMINI_API_KEY:
        print("=> [AI] Không có GEMINI_API_KEY -> dùng đường lui code-thuần.")
        return None
    if not nhom_list:
        return []

    # Đóng gói tin ứng viên (chỉ tiêu đề + mô tả ngắn) để tiết kiệm token.
    goi = [{"id": i, "tieu_de": n["tieu_de"], "mo_ta": n.get("mo_ta", "")[:200]}
           for i, n in enumerate(nhom_list)]
    prompt = (PROMPT_HE_THONG.format(chu_de_list=" | ".join(CHU_DE_CHUAN))
              + "\n\nDANH SÁCH TIN:\n" + json.dumps(goi, ensure_ascii=False))

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
    }
    try:
        resp = requests.post(GEMINI_URL, params={"key": GEMINI_API_KEY},
                             json=body, timeout=90)
    except Exception as e:
        print(f"=> [AI] Lỗi kết nối Gemini: {e} -> dùng đường lui code-thuần.")
        return None

    if resp.status_code == 429:
        print("=> [AI] Gemini báo 429 (hết lượt free) -> dùng đường lui code-thuần.")
        return None
    if resp.status_code != 200:
        print(f"=> [AI] Gemini trả về {resp.status_code}: {resp.text[:200]} "
              f"-> dùng đường lui code-thuần.")
        return None

    try:
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        danh_gia = json.loads(text)
        if not isinstance(danh_gia, list):
            raise ValueError("Kết quả AI không phải mảng JSON")
    except Exception as e:
        print(f"=> [AI] Không đọc được kết quả Gemini: {e} -> dùng đường lui code-thuần.")
        return None

    # Ghép kết quả AI vào từng nhóm tin theo id.
    theo_id = {}
    for d in danh_gia:
        try:
            theo_id[int(d["id"])] = d
        except (KeyError, ValueError, TypeError):
            continue

    ung_vien = []
    for i, nhom in enumerate(nhom_list):
        dg = theo_id.get(i)
        if not dg or not dg.get("lien_quan"):
            continue
        diem = dg.get("diem_tac_dong", 0)
        try:
            diem = int(diem)
        except (ValueError, TypeError):
            diem = 0
        if diem < NGUONG_TAC_DONG:
            continue
        chu_de = dg.get("chu_de", "")
        if chu_de not in CHU_DE_CHUAN:
            chu_de = gan_chu_de_code(nhom["tieu_de"], nhom["khu_vuc"])
        gio_vn = nhom["gio_dang"].astimezone(GIO_VN)
        ung_vien.append({
            "tieu_de": nhom["tieu_de"],
            "chu_de": chu_de,
            "diem_tac_dong": diem,
            "ly_do": (dg.get("ly_do") or "").strip(),
            "sac_thai": dg.get("sac_thai") if dg.get("sac_thai") in
                        ("tích cực", "tiêu cực", "trung tính") else "trung tính",
            "nguon": ", ".join(sorted(nhom["nguon_set"])),
            "so_nguon": len(nhom["nguon_set"]),
            "thoi_gian": gio_vn.strftime("%Y-%m-%d %H:%M"),
            "link": nhom["link"],
            "_nhom": dg.get("nhom"),
            "_gio": nhom["gio_dang"],
        })

    # Gộp trùng theo NGHĨA: tin cùng "nhom" -> giữ 1 bản (điểm cao nhất, mới nhất), gộp nguồn.
    theo_nhom = {}
    rieng_le = []
    for tin in ung_vien:
        key = tin.get("_nhom")
        if key is None:
            rieng_le.append(tin)
            continue
        if key not in theo_nhom:
            theo_nhom[key] = tin
        else:
            giu = theo_nhom[key]
            # Gộp số nguồn (ước lượng): cộng dồn nhãn nguồn khác nhau.
            nguon_gop = set(giu["nguon"].split(", ")) | set(tin["nguon"].split(", "))
            giu["nguon"] = ", ".join(sorted(nguon_gop))
            giu["so_nguon"] = len(nguon_gop)
            # Giữ bản điểm cao hơn; hòa thì giữ bản mới hơn.
            if (tin["diem_tac_dong"] > giu["diem_tac_dong"] or
                    (tin["diem_tac_dong"] == giu["diem_tac_dong"] and tin["_gio"] > giu["_gio"])):
                tin["nguon"], tin["so_nguon"] = giu["nguon"], giu["so_nguon"]
                theo_nhom[key] = tin

    ket_qua = list(theo_nhom.values()) + rieng_le
    for t in ket_qua:
        t.pop("_nhom", None)
        t.pop("_gio", None)
    ket_qua.sort(key=lambda x: x["diem_tac_dong"], reverse=True)
    print(f"=> [AI] Gemini giữ lại {len(ket_qua)} tin có tác động TTCK "
          f"(từ {len(nhom_list)} tin ứng viên).")
    return ket_qua


# ===========================================================================
# 8. [CODE] ĐƯỜNG LUI: chấm điểm & chọn tin khi không dùng được AI
# ===========================================================================
def cham_diem_code(nhom_list, tong=30):
    """Chấm điểm bằng code thuần (khi không có AI) và chọn `tong` tin điểm cao nhất."""
    bay_gio = datetime.now(timezone.utc)
    ds = []
    for nhom in nhom_list:
        t = nhom["tieu_de"].lower()
        diem_tu_khoa = sum(ts for tu, ts in TRONG_SO_TU_KHOA.items() if tu in t)
        diem_goc = len(nhom["nguon_set"]) * 3 + diem_tu_khoa + diem_moi(nhom["gio_dang"], bay_gio)
        chu_de = gan_chu_de_code(nhom["tieu_de"], nhom["khu_vuc"])
        tong_diem = diem_goc * HE_SO_UU_TIEN.get(chu_de, 1.0)
        # Quy điểm thô về thang 1-10 (chỉ để hiển thị cho đồng bộ với chế độ AI).
        diem_hien = min(10, max(1, round(tong_diem / 7)))
        gio_vn = nhom["gio_dang"].astimezone(GIO_VN)
        ds.append({
            "tieu_de": nhom["tieu_de"],
            "chu_de": chu_de,
            "diem_tac_dong": diem_hien,
            "ly_do": "",
            "sac_thai": "trung tính",
            "nguon": ", ".join(sorted(nhom["nguon_set"])),
            "so_nguon": len(nhom["nguon_set"]),
            "thoi_gian": gio_vn.strftime("%Y-%m-%d %H:%M"),
            "link": nhom["link"],
            "_diem_raw": tong_diem,
        })
    ds.sort(key=lambda x: x["_diem_raw"], reverse=True)
    ds = ds[:tong]
    for t in ds:
        t.pop("_diem_raw", None)
    return ds


# ===========================================================================
# 9. HÀM CHÍNH
# ===========================================================================
def main():
    tin_tho = lay_tat_ca_tin()
    nhom_list = gop_tin_trung(tin_tho)
    nhom_list = gop_bai_dinh_ky(nhom_list)

    che_do = "ai"
    danh_sach = cham_diem_ai(nhom_list)
    if danh_sach is None:            # AI không dùng được -> đường lui code
        che_do = "code"
        danh_sach = cham_diem_code(nhom_list, tong=30)
    else:
        danh_sach = danh_sach[:30]   # chế độ AI: giữ tối đa 30 tin điểm cao nhất

    output = {
        "cap_nhat_luc": datetime.now(GIO_VN).strftime("%Y-%m-%d %H:%M:%S"),
        "che_do": che_do,
        "so_tin": len(danh_sach),
        "tin": danh_sach,
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"=> Đã ghi data.json: {len(danh_sach)} tin (chế độ: {che_do}).")


if __name__ == "__main__":
    main()
