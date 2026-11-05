// 보딩패스 타임즈 공용 함수(모든 페이지). 날짜 표기, 이모지 SVG, 도시 → 국기 코드.
// - 날짜: MM/DD(요일), 기간 MM/DD(요일)~MM/DD(요일). 요일은 한국 날짜 그대로 계산(new Date(y, m-1, d)). UTC로 파싱하지 않음
// - 이모지: 문자 대신 images/emoji/<코드포인트>.svg(Noto Emoji, Apache-2.0). Windows 등에서 글자로 깨지는 것을 막음
(function () {
  const WK = '일월화수목금토';
  function parts(iso) {
    const m = String(iso || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m ? [+m[1], +m[2], +m[3]] : null;
  }
  function fmtMD(iso) {
    const p = parts(iso); if (!p) return '';
    const w = WK[new Date(p[0], p[1] - 1, p[2]).getDay()];
    return `${String(p[1]).padStart(2, '0')}/${String(p[2]).padStart(2, '0')}(${w})`;
  }
  function fmtRange(dep, ret) {
    const a = fmtMD(dep), b = fmtMD(ret);
    return a && b ? `${a}~${b}` : (a || b);
  }
  function fmtNights(n) { n = Number(n) || 0; return n ? `${n}박 ${n + 1}일` : ''; }
  function emoSrc(cp) { return `./images/emoji/${cp}.svg`; }
  const CITY_ISO2 = {"KIX": "jp", "FUK": "jp", "NRT": "jp", "CTS": "jp", "NGO": "jp", "OKA": "jp", "HSG": "jp", "TAK": "jp", "FSZ": "jp", "KOJ": "jp", "OIT": "jp", "YGJ": "jp", "KKJ": "jp", "SDJ": "jp", "MYJ": "jp", "HIJ": "jp", "KMJ": "jp", "NGS": "jp", "KMQ": "jp", "AOJ": "jp", "AKJ": "jp", "PVG": "cn", "PKX": "cn", "CAN": "cn", "TAO": "cn", "YNT": "cn", "DLC": "cn", "HGH": "cn", "XIY": "cn", "DYG": "cn", "HRB": "cn", "DAD": "vn", "CXR": "vn", "PQC": "vn", "HAN": "vn", "SGN": "vn", "HPH": "vn", "DLI": "vn", "BKK": "th", "CNX": "th", "HKT": "th", "CEB": "ph", "TAG": "ph", "CRK": "ph", "DPS": "id", "BKI": "my", "SIN": "sg", "VTE": "la", "BWN": "bn", "GUM": "gu", "SPN": "mp", "ALA": "kz", "TAS": "uz", "UBN": "mn", "TPE": "tw", "KHH": "tw", "HKG": "hk", "MFM": "mo", "UKB": "jp", "HKD": "jp", "OBO": "jp", "ISG": "jp", "SHI": "jp", "KMI": "jp", "TKS": "jp", "OKJ": "jp", "KIJ": "jp", "IBR": "jp", "SZX": "cn", "NKG": "cn", "NGB": "cn", "WEH": "cn", "XMN": "cn", "SYX": "cn", "TFU": "cn", "CKG": "cn", "KMG": "cn", "YNJ": "cn", "RMQ": "tw", "MNL": "ph", "KLO": "ph", "KTI": "kh", "SAI": "kh", "KUL": "my", "CGK": "id", "BTH": "id", "NQZ": "kz", "FRU": "kg", "DEL": "in", "KTM": "np", "CMB": "lk", "SYD": "au", "BNE": "au", "MEL": "au", "AKL": "nz", "HNL": "us", "ROR": "pw", "CDG": "fr", "LHR": "gb", "FRA": "de", "MUC": "de", "AMS": "nl", "ZRH": "ch", "CPH": "dk", "HEL": "fi", "FCO": "it", "MXP": "it", "BCN": "es", "MAD": "es", "LIS": "pt", "IST": "tr", "VIE": "at", "PRG": "cz", "BUD": "hu", "WAW": "pl", "WRO": "pl", "LAX": "us", "SFO": "us", "SEA": "us", "LAS": "us", "JFK": "us", "ORD": "us", "IAD": "us", "BOS": "us", "ATL": "us", "DFW": "us", "DTW": "us", "MSP": "us", "YVR": "ca", "YYZ": "ca", "YUL": "ca", "YYC": "ca"};
  function flagSrc(code) { const i = CITY_ISO2[code]; return i ? `./images/flags/${i}.svg` : ''; }
  window.BPT = { fmtMD, fmtRange, fmtNights, emoSrc, flagSrc, CITY_ISO2 };
})();
