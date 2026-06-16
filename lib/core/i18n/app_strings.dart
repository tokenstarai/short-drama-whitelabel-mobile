class AppStrings {
  const AppStrings(this.locale);

  final String locale;

  String get appTitle => _pick(
        en: 'Short Drama',
        zh: '短剧',
        th: 'ละครสั้น',
        id: 'Drama Pendek',
        vi: 'Phim ngắn',
        ms: 'Drama Pendek',
        fil: 'Maikling Drama',
      );
  String get home => _pick(
        en: 'Home',
        zh: '首页',
        th: 'หน้าแรก',
        id: 'Beranda',
        vi: 'Trang chủ',
        ms: 'Laman Utama',
        fil: 'Home',
      );
  String get catalog => _pick(
        en: 'Catalog',
        zh: '分类',
        th: 'หมวดหมู่',
        id: 'Kategori',
        vi: 'Danh mục',
        ms: 'Katalog',
        fil: 'Katalogo',
      );
  String get theater => _pick(
        en: 'Theater',
        zh: '剧场',
        th: 'โรงละคร',
        id: 'Teater',
        vi: 'Rạp',
        ms: 'Teater',
        fil: 'Teatro',
      );
  String get mine => _pick(
        en: 'Mine',
        zh: '我的',
        th: 'ของฉัน',
        id: 'Saya',
        vi: 'Của tôi',
        ms: 'Saya',
        fil: 'Akin',
      );
  String get startWatching => _pick(
        en: 'Start Watching',
        zh: '开始观看',
        th: 'เริ่มดู',
        id: 'Mulai Menonton',
        vi: 'Bắt đầu xem',
        ms: 'Mula Menonton',
        fil: 'Simulan Manood',
      );
  String get unlockAndPlay => _pick(
        en: 'Unlock and Play',
        zh: '解锁并播放',
        th: 'ปลดล็อกและเล่น',
        id: 'Buka dan Putar',
        vi: 'Mở khóa và phát',
        ms: 'Buka dan Main',
        fil: 'I-unlock at I-play',
      );
  String get serviceMaintenance => _pick(
        en: 'Service is under maintenance. Please try again later.',
        zh: '服务维护中，请稍后再试。',
        th: 'ระบบกำลังปรับปรุง โปรดลองอีกครั้งภายหลัง',
        id: 'Layanan sedang dalam pemeliharaan. Coba lagi nanti.',
        vi: 'Dịch vụ đang bảo trì. Vui lòng thử lại sau.',
        ms: 'Perkhidmatan sedang diselenggara. Sila cuba lagi kemudian.',
        fil: 'May maintenance ang serbisyo. Subukan muli mamaya.',
      );
  String get insufficientBalance => _pick(
        en: 'This content is temporarily unavailable. Please try again later.',
        zh: '当前内容暂时不可播放，请稍后再试。',
        th: 'เนื้อหานี้ยังไม่พร้อมให้เล่น โปรดลองอีกครั้งภายหลัง',
        id: 'Konten ini sementara belum dapat diputar. Coba lagi nanti.',
        vi: 'Nội dung hiện chưa thể phát. Vui lòng thử lại sau.',
        ms: 'Kandungan ini belum boleh dimainkan. Sila cuba lagi kemudian.',
        fil:
            'Hindi pansamantalang mapanood ang content na ito. Subukan muli mamaya.',
      );
  String get notAuthorized => _pick(
        en: 'This content is not available yet.',
        zh: '内容暂未开放。',
        th: 'เนื้อหานี้ยังไม่เปิดให้บริการ',
        id: 'Konten ini belum tersedia.',
        vi: 'Nội dung chưa được mở.',
        ms: 'Kandungan ini belum dibuka.',
        fil: 'Hindi pa bukas ang content na ito.',
      );
  String get episodeNotReady =>
      _pick(en: 'This episode is being prepared.', zh: '本集正在准备中。');
  String get playbackTokenFailed => _pick(
        en: 'Playback authorization failed. Please retry.',
        zh: '播放授权失败，请重试。',
      );
  String get cardRedeem => _pick(
        en: 'Redeem Card',
        zh: '点卡兑换',
        th: 'แลกบัตร',
        id: 'Tukar Kartu',
        vi: 'Đổi thẻ',
        ms: 'Tebus Kad',
        fil: 'I-redeem ang Card',
      );
  String get pointCardManagement => _pick(
        en: 'Point Card Management',
        zh: '点卡管理',
        th: 'จัดการบัตรแต้ม',
        id: 'Manajemen Kartu Poin',
        vi: 'Quản lý thẻ điểm',
        ms: 'Pengurusan Kad Mata',
        fil: 'Pamamahala ng Point Card',
      );
  String get noPointCardRecords => _pick(
        en: 'No point card records yet',
        zh: '暂无点卡记录',
        th: 'ยังไม่มีประวัติบัตรแต้ม',
        id: 'Belum ada catatan kartu poin',
        vi: 'Chưa có lịch sử thẻ điểm',
        ms: 'Tiada rekod kad mata lagi',
        fil: 'Wala pang point card records',
      );
  String get pointCardRedeemFailed => _pick(
        en: 'This point card cannot be used. Please check it and retry.',
        zh: '此点卡暂不可用，请检查后重试。',
        th: 'ไม่สามารถใช้บัตรแต้มนี้ได้ โปรดตรวจสอบแล้วลองอีกครั้ง',
        id: 'Kartu poin ini tidak dapat digunakan. Periksa lalu coba lagi.',
        vi: 'Không thể dùng thẻ điểm này. Vui lòng kiểm tra và thử lại.',
        ms: 'Kad mata ini tidak boleh digunakan. Semak dan cuba lagi.',
        fil: 'Hindi magamit ang point card na ito. Suriin ito at subukan muli.',
      );
  String get pointCardRedeemUnavailable => _pick(
        en: 'Point card recharge is not available in this build.',
        zh: '当前构建不支持点卡充值。',
        th: 'บิลด์นี้ยังไม่รองรับการเติมเงินด้วยบัตรแต้ม',
        id: 'Isi ulang kartu poin tidak tersedia di build ini.',
        vi: 'Bản dựng này chưa hỗ trợ nạp bằng thẻ điểm.',
        ms: 'Tambah nilai kad mata tidak tersedia dalam binaan ini.',
        fil: 'Hindi available ang point card recharge sa build na ito.',
      );
  String get consumerWallet => _pick(
        en: 'consumer wallet',
        zh: 'C端钱包',
        th: 'กระเป๋าผู้ใช้',
        id: 'dompet konsumen',
        vi: 'ví người dùng',
        ms: 'dompet pengguna',
        fil: 'consumer wallet',
      );
  String get onlinePayment => _pick(
        en: 'Online Top Up',
        zh: '在线充值',
        th: 'เติมเงินออนไลน์',
        id: 'Isi Saldo Online',
        vi: 'Nạp tiền trực tuyến',
        ms: 'Tambah Nilai Dalam Talian',
        fil: 'Online Top Up',
      );
  String get paymentFailed => _pick(
        en: 'Payment failed. Please choose another method or retry.',
        zh: '支付失败，请更换方式或重试。',
        th: 'ชำระเงินไม่สำเร็จ โปรดเลือกวิธีอื่นหรือลองอีกครั้ง',
        id: 'Pembayaran gagal. Pilih metode lain atau coba lagi.',
        vi: 'Thanh toán thất bại. Vui lòng chọn cách khác hoặc thử lại.',
        ms: 'Pembayaran gagal. Pilih kaedah lain atau cuba lagi.',
        fil: 'Nabigo ang pagbabayad. Pumili ng ibang paraan o subukan muli.',
      );
  String get accountDelete => _pick(
        en: 'Delete Account',
        zh: '删除账号',
        th: 'ลบบัญชี',
        id: 'Hapus Akun',
        vi: 'Xóa tài khoản',
        ms: 'Padam Akaun',
        fil: 'Burahin ang Account',
      );
  String get authFailed => _pick(
        en: 'Sign-in failed. Please retry or choose another method.',
        zh: '登录失败，请重试或选择其他登录方式。',
        th: 'เข้าสู่ระบบไม่สำเร็จ โปรดลองอีกครั้งหรือเลือกวิธีอื่น',
        id: 'Masuk gagal. Coba lagi atau pilih metode lain.',
        vi: 'Đăng nhập thất bại. Vui lòng thử lại hoặc chọn cách khác.',
        ms: 'Log masuk gagal. Cuba lagi atau pilih kaedah lain.',
        fil: 'Nabigo ang pag-sign in. Subukan muli o pumili ng ibang paraan.',
      );
  String get settings => _pick(
        en: 'Settings',
        zh: '设置',
        th: 'ตั้งค่า',
        id: 'Pengaturan',
        vi: 'Cài đặt',
        ms: 'Tetapan',
        fil: 'Mga Setting',
      );
  String get language => _pick(
        en: 'Language',
        zh: '语言',
        th: 'ภาษา',
        id: 'Bahasa',
        vi: 'Ngôn ngữ',
        ms: 'Bahasa',
        fil: 'Wika',
      );

  String get loadingTenantApp =>
      _pick(en: 'Loading tenant app', zh: '正在加载租户应用');
  String get tenantEdgeUnavailable =>
      _pick(en: 'Tenant Edge unavailable', zh: '租户 Edge 暂不可用');
  String get retry => _pick(en: 'Retry', zh: '重试');
  String get continueWithDemoData =>
      _pick(en: 'Continue with demo data', zh: '使用演示数据继续');
  String get tenantEdgeOfflineDemo => _pick(
        en: 'Tenant Edge offline, showing local template data.',
        zh: '租户 Edge 离线，正在展示本地模板数据。',
      );
  String get searchDrama => _pick(en: 'Search drama', zh: '搜索短剧');
  String get hotPicks => _pick(en: 'Hot Picks', zh: '热门推荐');
  String get walletCenter => _pick(
        en: 'Wallet Center',
        zh: '钱包中心',
        th: 'ศูนย์กระเป๋าเงิน',
        id: 'Pusat Dompet',
        vi: 'Ví của tôi',
        ms: 'Pusat Dompet',
        fil: 'Wallet Center',
      );
  String get loginRegister => _pick(en: 'Login / Register', zh: '登录/注册');
  String get signOut => _pick(en: 'Sign Out', zh: '退出登录');
  String get watchHistory => _pick(en: 'Watch History', zh: '观看历史');
  String get favorites => _pick(en: 'Favorites', zh: '收藏');
  String get noWatchHistory =>
      _pick(en: 'No watched episodes yet', zh: '暂无观看历史');
  String get noFavorites => _pick(en: 'No favorites yet', zh: '暂无收藏');
  String get offlineTopUp => _pick(en: 'Offline Top Up', zh: '银行卡/线下充值');
  String get support => _pick(en: 'Support', zh: '客服支持');
  String get termsOfService => _pick(en: 'Terms of Service', zh: '用户协议');
  String get privacyPolicy => _pick(en: 'Privacy Policy', zh: '隐私政策');
  String get legalLink => _pick(en: 'Legal Link', zh: '法务链接');
  String get tenantHostedLegalUrl => _pick(
        en: 'This page is hosted by the tenant. The app only displays the public URL and does not store legal-service credentials.',
        zh: '此页面由租户托管。App 仅展示公开 URL，不保存法务服务凭证。',
      );
  String get openInTenantBrowser => _pick(
        en: 'Open this URL in the tenant-hosted browser or system browser.',
        zh: '请在租户托管页面或系统浏览器打开此 URL。',
      );
  String get unlockEpisode => _pick(en: 'Unlock Episode', zh: '解锁剧集');
  String get watchAdToUnlock => _pick(en: 'Watch ad to unlock', zh: '观看广告解锁');
  String get moreUnlockOptions =>
      _pick(en: 'More unlock options', zh: '更多解锁方式');
  String get authorizing => _pick(en: 'Authorizing...', zh: '正在授权...');
  String get authorizedPlayer => _pick(en: 'Authorized player', zh: '已授权播放');
  String get preparingVideo => _pick(en: 'Preparing video...', zh: '正在准备视频...');
  String get playbackFallback => _pick(
        en: 'Native playback is unavailable. Use the tenant player URL below.',
        zh: '原生播放暂不可用，请使用下方租户播放链接。',
      );
  String get previousEpisode => _pick(en: 'Previous', zh: '上一集');
  String get nextEpisode => _pick(en: 'Next', zh: '下一集');
  String get episodeList => _pick(en: 'Episode List', zh: '剧集列表');
  String get shareDrama => _pick(en: 'Share Drama', zh: '分享短剧');
  String get tenantSafeShareLink =>
      _pick(en: 'Tenant-safe share link', zh: '租户安全分享链接');
  String get copyLink => _pick(en: 'Copy Link', zh: '复制链接');
  String get shareLinkCopied => _pick(en: 'Share link copied', zh: '分享链接已复制');
  String get paymentEntryGated =>
      _pick(en: 'Payment entry gated by store compliance', zh: '支付入口受商店合规限制');
  String get paymentsGated => _pick(en: 'payments gated', zh: '支付已受限');
  String get swipe => _pick(en: 'Swipe', zh: '滑动');
  String get list => _pick(en: 'List', zh: '列表');

  String episodesReady(int count) => _pick(
        en: '$count ready',
        zh: '$count 集可看',
        th: 'พร้อม $count ตอน',
        id: '$count siap',
        vi: '$count tập sẵn sàng',
        ms: '$count sedia',
        fil: '$count handa',
      );

  String episodeCostPoints(int points) => _pick(
        en: 'This episode costs $points points.',
        zh: '本集需 $points 点。',
      );

  String paymentMethods(int count) => _pick(
        en: '$count payment methods',
        zh: '$count 种支付方式',
      );

  String coins(int count) => _pick(en: '$count coins', zh: '$count 金币');

  String _pick({
    required String en,
    String? zh,
    String? th,
    String? id,
    String? vi,
    String? ms,
    String? fil,
  }) {
    final key = languageKey(locale);
    if (key == 'zh') {
      return zh ?? en;
    }
    if (key == 'th') {
      return th ?? en;
    }
    if (key == 'id') {
      return id ?? en;
    }
    if (key == 'vi') {
      return vi ?? en;
    }
    if (key == 'ms') {
      return ms ?? en;
    }
    if (key == 'fil') {
      return fil ?? en;
    }
    return en;
  }

  static String languageKey(String locale) {
    return locale.split(RegExp('[-_]')).first.toLowerCase();
  }

  static String languageNameFor(String locale) {
    return switch (languageKey(locale)) {
      'zh' => '中文',
      'th' => 'ไทย',
      'id' => 'Bahasa Indonesia',
      'vi' => 'Tiếng Việt',
      'ms' => 'Bahasa Melayu',
      'fil' => 'Filipino',
      _ => 'English',
    };
  }
}
