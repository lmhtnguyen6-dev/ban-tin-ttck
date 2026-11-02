# Radar TTCK — Bản tin nóng tác động thị trường chứng khoán

Web tĩnh tự động thu thập tin tài chính – kinh tế – vĩ mô – chính sách tiếng Việt,
**lọc bằng AI (Gemini)** để chỉ giữ tin **có tác động trực tiếp đến thị trường chứng
khoán Việt Nam / một ngành / một doanh nghiệp niêm yết**, gộp tin trùng, rồi hiển thị
kèm **link bài gốc**, **điểm tác động (0–10)**, **lý do**, **sắc thái** (tích cực/tiêu
cực/trung tính).

Chạy **miễn phí** trên GitHub Actions + GitHub Pages.

---

## Hoạt động thế nào (tóm tắt)

```
RSS (CafeF, VnExpress, Vietstock, VietnamBiz)
  → [CODE] lọc thô: 24h + tiếng Việt + loại tin nhiễu rõ ràng
  → [CODE] gộp tin trùng theo tiêu đề + gộp loạt bài định kỳ
  → [AI Gemini] 1 lần gọi: chấm tác động TTCK, gán chủ đề, nêu lý do, gộp trùng theo nghĩa
  → chọn tin điểm cao → data.json → web hiển thị
```

> **Đường lui an toàn:** nếu chưa cắm `GEMINI_API_KEY`, hoặc Gemini lỗi/hết lượt free,
> chương trình **tự động chấm bằng code thuần** để bản tin không bao giờ trống. Góc trên
> web hiện nhãn **"Lọc bằng AI"** hay **"Lọc bằng code"** để biết lần chạy dùng cách nào.

---

## Các file

| File | Vai trò |
|---|---|
| `scraper.py` | Bộ não: lấy RSS → lọc → gộp → chấm (AI + đường lui code) → ghi `data.json` |
| `index.html` / `style.css` / `script.js` | Web tĩnh đọc `data.json` |
| `.github/workflows/scrape.yml` | Chạy scraper mỗi giờ, commit `data.json` |
| `requirements.txt` | Thư viện Python: `feedparser`, `requests` |
| `data.json` | Dữ liệu (bot tự cập nhật — **không sửa tay**) |

---

## Cài đặt lần đầu (6 bước)

> Giả định anh dùng tài khoản GitHub `lmhtnguyen6-dev`.

### 1. Lấy Gemini API key (miễn phí)
- Vào **https://aistudio.google.com/apikey** → đăng nhập Google → **Create API key**.
- Copy chuỗi key (dạng `AIza...`). Giữ bí mật, **đừng dán vào code hay chat**.

### 2. Tạo repo mới trên GitHub
- Vào https://github.com/new → đặt tên `ban-tin-ttck` → Public → Create.

### 3. Đẩy code lên repo
Trong thư mục dự án, chạy (một lần):
```bash
git init
git add .
git commit -m "Khởi tạo Radar TTCK"
git branch -M main
git remote add origin https://github.com/lmhtnguyen6-dev/ban-tin-ttck.git
git push -u origin main
```

### 4. Cắm Gemini key vào repo (bí mật)
- Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
- Name: `GEMINI_API_KEY` — Secret: dán key ở bước 1 → **Add secret**.

### 5. Bật GitHub Pages
- Repo → **Settings** → **Pages** → **Source**: Deploy from a branch →
  Branch: `main` / `/ (root)` → **Save**.
- Sau ít phút, web ở: `https://lmhtnguyen6-dev.github.io/ban-tin-ttck/`

### 6. Chạy lần đầu
- Repo → tab **Actions** → chọn workflow **"Thu thập & chấm tin"** → **Run workflow**.
- Chờ ~1 phút, nó tạo/cập nhật `data.json`. Mở lại web để xem tin.

Từ đây, bot tự chạy **mỗi giờ**. Cần tin ngay thì vào **Actions → Run workflow**.

---

## Test nhanh trên máy

```bash
pip install -r requirements.txt
python scraper.py              # chưa có key → chạy code thuần
```
Có key (PowerShell):
```powershell
$env:GEMINI_API_KEY="AIza...cua_ban"
python scraper.py              # chạy chế độ AI
```
Mở `index.html` bằng trình duyệt để xem (hoặc chạy `python -m http.server` rồi vào
`http://localhost:8000`).

---

## Tinh chỉnh

- **Thêm/bớt nguồn RSS:** sửa `RSS_SOURCES` đầu `scraper.py`.
- **Đổi tiêu chí lọc AI:** sửa `PROMPT_HE_THONG` trong `scraper.py`.
- **Ngưỡng giữ tin:** `NGUONG_TAC_DONG` (mặc định 4/10).
- **Nhóm tin nhiễu loại bằng code:** `NHOM_TIN_NHIEU` + `LOC_NHOM_NHIEU`.
- **Đổi model Gemini:** đặt repo *Variable* `GEMINI_MODEL` (mặc định `gemini-2.5-flash`).

## Lưu ý về giới hạn Gemini free
Bậc miễn phí của Gemini có giới hạn số lượt/ngày (thay đổi theo thời gian). Vì mỗi lần
chạy chỉ gọi **1 lần** và chạy **theo giờ** (~24 lần/ngày), mức này thường nằm trong
hạn mức free. Nếu hết lượt, web tự rớt về chế độ **code thuần** — không bị gián đoạn.
