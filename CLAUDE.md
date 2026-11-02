# CLAUDE.md — Radar TTCK (bối cảnh cho phiên Claude Code)

## Dự án là gì
Web tin **tài chính – chứng khoán tiếng Việt**, thu từ RSS, lọc bằng **Hybrid: code
lọc thô + AI (Gemini) chấm tác động TTCK & gộp trùng theo nghĩa**, xuất `data.json`,
hiển thị web tĩnh. Chạy tự động **miễn phí** trên GitHub Actions + Pages.

- Đây là **web mới**, tách khỏi dự án cũ `ban-tin-tai-chinh` (vẫn chạy song song).
- Chủ dự án (môi giới/nhà phân tích CK) là **người mới với Git/deploy** → giải thích
  ngắn gọn, ưu tiên tiếng Việt.
- Repo dự kiến: `github.com/lmhtnguyen6-dev/ban-tin-ttck`
  Web: `https://lmhtnguyen6-dev.github.io/ban-tin-ttck/`

## Quyết định thiết kế đã chốt (brainstorm)
- **Lõi lọc = Hybrid**: code loại ~70% rác dễ thấy (miễn phí), AI chỉ xử lý bước tinh.
- **AI = Gemini free tier** (người dùng chọn miễn phí). Gọi **1 LẦN/lần chạy** cho cả
  lô tin ứng viên (tiết kiệm lượt). **Luôn có đường lui code-thuần** khi không có key /
  lỗi / 429. `data.json.che_do` = `"ai"` hoặc `"code"`.
- **Chạy theo GIỜ** (cron `5 * * * *`), KHÔNG phải 15 phút — để hợp giới hạn free Gemini.
- **Phạm vi: toàn diện** (người dùng chọn), nhưng làm **theo giai đoạn**:
  - **Phase 1 (ĐÃ LÀM):** tin báo RSS + lọc/gộp AI + web mới.
  - **Phase 2 (chưa làm):** công bố thông tin DN niêm yết (BCTC, KQKD, CBTT bất thường)
    qua thư viện **vnstock 4.x** (có nhóm tin tức & công bố, free ~20 req/phút).
  - **Phase 3 (chưa làm):** bảng số liệu có cấu trúc (giá dầu/thép/cao su, vĩ mô). KHÓ:
    không có API free gộp đủ. Nguồn khả thi: World Bank Pink Sheet (thép/cao su, theo
    tháng), giá dầu nguồn free, vĩ mô VN từ GSO/SBV. Cập nhật chậm → để sau cùng.

## Kiến trúc `scraper.py`
1. `lay_tat_ca_tin()` — RSS → lọc 24h + tiếng Việt + `la_tin_nhieu` (nhóm nhiễu code).
2. `gop_tin_trung()` + `gop_bai_dinh_ky()` — gộp trùng theo chuỗi (bước code).
3. `cham_diem_ai()` — gọi Gemini 1 lần; trả tin đã chọn, hoặc **None** để fallback.
4. `cham_diem_code()` — đường lui: chấm điểm từ khóa có trọng số + hệ số ưu tiên.
5. `main()` — thử AI trước, None thì dùng code; ghi `data.json`.

## Schema `data.json`
```json
{ "cap_nhat_luc": "...", "che_do": "ai|code", "so_tin": N,
  "tin": [ { "tieu_de","chu_de","diem_tac_dong"(0-10),"ly_do",
             "sac_thai"(tích cực|tiêu cực|trung tính),
             "nguon","so_nguon","thoi_gian","link" } ] }
```
`chu_de` phải thuộc `CHU_DE_CHUAN` (7 chủ đề). Frontend `script.js` render chips theo đó.

## Gotcha
- **KHÔNG sửa tay `data.json`** (bot ghi đè). Đổi kết quả → sửa logic `scraper.py`.
- Workflow đã có `git pull --rebase --autostash` trước push (tránh xung đột như dự án cũ).
- `GEMINI_API_KEY` là **repo secret**; `GEMINI_MODEL` là repo variable (tùy chọn).
- Model Gemini free đổi tên theo thời gian (mặc định `gemini-2.5-flash`) — nếu 404 model,
  đổi `GEMINI_MODEL`.
- Trên máy chủ dự án: `git`/`gh` KHÔNG nằm trên PATH PowerShell (app có tích hợp git
  riêng). Python 3.12 có sẵn. Có thư mục `~/.vnstock` (hữu ích cho Phase 2).

## Ý tưởng để ngỏ / gợi ý thêm cho người dùng
- Thêm theo dõi: khối ngoại ròng, tỷ giá USD/VND & DXY, lợi suất TPCP, OMO/liên NH,
  lịch FOMC & ngày công bố CPI, đáo hạn phái sinh.
- Thêm nguồn Báo Đầu tư khi có RSS.
- Cân nhắc dùng embedding để gộp trùng thay vì chỉ `SequenceMatcher` + nhóm AI.
