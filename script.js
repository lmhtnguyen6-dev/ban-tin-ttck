/* =====================================================================
   Radar TTCK — đọc data.json, render bản tin, lọc theo chủ đề + tìm kiếm
   ===================================================================== */
"use strict";

const SAC_THAI_CLASS = { "tích cực": "pos", "tiêu cực": "neg", "trung tính": "neu" };

let TIN = [];            // toàn bộ tin từ data.json
let chuDeHienTai = "Tất cả";
let tuKhoaTim = "";

const $ = (sel) => document.querySelector(sel);

/* ---------- Tải dữ liệu ---------- */
async function taiDuLieu() {
  try {
    // thêm tham số thời gian để tránh cache cũ của trình duyệt
    const res = await fetch("data.json?t=" + Date.now());
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    TIN = Array.isArray(data.tin) ? data.tin : [];

    capNhatMeta(data);
    dungBoLoc();
    render();
  } catch (e) {
    $("#trang-thai").textContent =
      "Chưa đọc được dữ liệu (data.json). Sau khi chạy scraper lần đầu, tải lại trang.";
    console.error(e);
  }
}

function capNhatMeta(data) {
  const cheDo = $("#che-do");
  if (data.che_do === "ai") {
    cheDo.textContent = "Lọc bằng AI";
    cheDo.className = "badge ai";
  } else {
    cheDo.textContent = "Lọc bằng code";
    cheDo.className = "badge code";
  }
  if (data.cap_nhat_luc) {
    $("#cap-nhat").textContent = "Cập nhật: " + data.cap_nhat_luc;
  }
}

/* ---------- Bộ lọc chủ đề (chips) ---------- */
function dungBoLoc() {
  const dem = {};
  TIN.forEach((t) => { dem[t.chu_de] = (dem[t.chu_de] || 0) + 1; });

  const thuTu = [
    "Chính sách & NHNN", "Fed & lãi suất toàn cầu", "Doanh nghiệp niêm yết",
    "Vĩ mô Việt Nam", "Hàng hóa", "Dòng tiền & khối ngoại", "Thế giới & địa chính trị",
  ];
  const coTin = thuTu.filter((cd) => dem[cd] > 0);

  const chips = [["Tất cả", TIN.length]].concat(coTin.map((cd) => [cd, dem[cd]]));
  const box = $("#filters");
  box.innerHTML = "";
  chips.forEach(([ten, n]) => {
    const el = document.createElement("button");
    el.className = "chip" + (ten === chuDeHienTai ? " active" : "");
    el.innerHTML = ten + ` <span class="n">${n}</span>`;
    el.onclick = () => { chuDeHienTai = ten; dungBoLoc(); render(); };
    box.appendChild(el);
  });
}

/* ---------- Render danh sách ---------- */
function render() {
  const q = tuKhoaTim.trim().toLowerCase();
  let ds = TIN.slice();

  if (chuDeHienTai !== "Tất cả") ds = ds.filter((t) => t.chu_de === chuDeHienTai);
  if (q) {
    ds = ds.filter((t) =>
      (t.tieu_de || "").toLowerCase().includes(q) ||
      (t.ly_do || "").toLowerCase().includes(q));
  }
  ds.sort((a, b) => (b.diem_tac_dong || 0) - (a.diem_tac_dong || 0));

  const box = $("#danh-sach");
  const tt = $("#trang-thai");
  box.innerHTML = "";

  if (ds.length === 0) {
    tt.textContent = "Không có tin nào khớp bộ lọc.";
    tt.style.display = "block";
    return;
  }
  tt.style.display = "none";

  ds.forEach((t) => box.appendChild(taoCard(t)));
}

function taoCard(t) {
  const sac = SAC_THAI_CLASS[t.sac_thai] || "neu";
  const card = document.createElement("article");
  card.className = "card " + sac;

  const nhieuNguon = (t.so_nguon && t.so_nguon > 1)
    ? `<span class="nguon-nhieu">${t.so_nguon} báo cùng đưa</span><span class="dot">·</span>`
    : "";

  const lyDo = t.ly_do
    ? `<p class="ly-do"><b>Vì sao đáng chú ý:</b> ${escapeHtml(t.ly_do)}</p>` : "";

  card.innerHTML = `
    <div class="score">
      <div class="num">${t.diem_tac_dong ?? "-"}</div>
      <div class="lbl">tác động</div>
    </div>
    <div class="body">
      <div class="tags">
        <span class="tag">${escapeHtml(t.chu_de || "")}</span>
        <span class="tag sac ${sac}">${escapeHtml(t.sac_thai || "trung tính")}</span>
      </div>
      <h3 class="title">
        <a href="${encodeURI(t.link || "#")}" target="_blank" rel="noopener">${escapeHtml(t.tieu_de || "")}</a>
      </h3>
      ${lyDo}
      <div class="foot-line">
        ${nhieuNguon}
        <span>${escapeHtml(t.nguon || "")}</span>
        <span class="dot">·</span>
        <span>${escapeHtml(t.thoi_gian || "")}</span>
      </div>
    </div>`;
  return card;
}

/* ---------- An toàn: thoát HTML ---------- */
function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

/* ---------- Khởi động ---------- */
$("#search").addEventListener("input", (e) => { tuKhoaTim = e.target.value; render(); });
taiDuLieu();
// tự tải lại dữ liệu mỗi 10 phút để bắt bản cập nhật mới (web mở lâu)
setInterval(taiDuLieu, 10 * 60 * 1000);
