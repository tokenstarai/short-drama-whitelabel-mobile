import 'package:flutter/widgets.dart';

import '../core/api/app_models.dart';
import '../core/api/tenant_adapter_client.dart';
import '../core/config/app_capabilities.dart';
import '../core/config/feature_flags.dart';
import '../core/i18n/app_strings.dart';
import '../flavor/flavor.dart';

class AppRuntime extends ChangeNotifier {
  AppRuntime({
    required this.flavor,
    required this.client,
    String? endUserRef,
    String? localeCode,
    this.isDemoMode = false,
  })  : endUserRef = endUserRef ?? _defaultEndUserRef(flavor),
        localeCode = _normalizeLocaleCode(
          localeCode ?? _firstSupportedLocale(flavor.brand.supportedLocales),
        ),
        data = AppRuntimeData.seeded(flavor);

  final FlavorConfig flavor;
  final TenantAdapterClient client;
  final String endUserRef;
  final bool isDemoMode;
  String localeCode;
  AppRuntimeData data;
  bool loading = false;
  Object? error;
  bool _localeManuallySelected = false;
  final List<PlaybackHistoryEntry> _watchHistory = [];
  final Map<String, FavoriteDrama> _favoriteDramas = {};

  String get appName => data.config?.appName ?? flavor.brand.appName;

  AppStrings get strings => AppStrings(localeCode);

  List<String> get supportedLocaleCodes => _normalizedLocaleCodes(
        data.config?.supportedLocales ?? flavor.brand.supportedLocales,
      );

  AppCapabilities get effectiveCapabilities =>
      data.config?.capabilities.constrainedByNativeBuild(
        flavor.capabilities,
      ) ??
      flavor.capabilities;

  AppLegalUrls get effectiveLegal =>
      data.config?.legal ??
      AppLegalUrls(
        customerServiceUrl: flavor.brand.customerServiceUrl,
        termsUrl: flavor.brand.termsUrl,
        privacyUrl: flavor.brand.privacyUrl,
      );

  Color get effectiveBrandPrimaryColor =>
      _parseHexColor(data.config?.primaryColor) ?? flavor.brand.primaryColor;

  FeatureFlags get effectiveFeatures {
    final features = data.config?.features;
    if (features == null) {
      return flavor.features;
    }
    return FeatureFlags(
      enableCardRedeem:
          features['enableCardRedeem'] ?? flavor.features.enableCardRedeem,
      enableOfflineTopup:
          features['enableOfflineTopup'] ?? flavor.features.enableOfflineTopup,
      enableOnlinePayment: features['enableOnlinePayment'] ??
          flavor.features.enableOnlinePayment,
      enableAdsUnlock:
          features['enableAdsUnlock'] ?? flavor.features.enableAdsUnlock,
      enableAccountDeletion: features['enableAccountDeletion'] ??
          flavor.features.enableAccountDeletion,
    );
  }

  List<CatalogDrama> get catalog => data.catalog;

  UserAccount? get account => data.account;

  ConsumerWallet? get wallet => data.wallet;

  PaymentOptions? get paymentOptions => data.paymentOptions;

  List<ConsumerPaymentProvider> get effectivePaymentProviders {
    Iterable<String> providerWireValues = data.paymentOptions?.providers ??
        effectiveCapabilities.visiblePaymentProviders.map(
          (provider) => provider.wireValue,
        );
    final paymentOptions = data.paymentOptions;
    if (paymentOptions != null && !paymentOptions.externalPaymentsAllowed) {
      providerWireValues = providerWireValues.where(
        (provider) =>
            provider == ConsumerPaymentProvider.iap.wireValue ||
            provider == ConsumerPaymentProvider.playBilling.wireValue,
      );
    }
    final providers = effectiveCapabilities.visiblePaymentProvidersFromWire(
      providerWireValues,
    );
    if (!effectiveFeatures.enableCardRedeem) {
      return providers
          .where((provider) => provider != ConsumerPaymentProvider.pointCard)
          .toList(growable: false);
    }
    return providers;
  }

  List<String> get effectivePaymentProviderWireValues =>
      effectivePaymentProviders.map((provider) => provider.wireValue).toList();

  bool get canRedeemConsumerPointCards => effectivePaymentProviders.contains(
        ConsumerPaymentProvider.pointCard,
      );

  TopupPaymentChannels? get topupPaymentChannels => data.topupPaymentChannels;

  List<TopupPaymentChannel> get enabledTopupPaymentChannels =>
      List.unmodifiable(
        (data.topupPaymentChannels?.channels ?? const [])
            .where((channel) => channel.enabled),
      );

  WalletLedger? get walletLedger => data.walletLedger;

  List<PlaybackHistoryEntry> get watchHistory =>
      List.unmodifiable(_watchHistory);

  List<FavoriteDrama> get favorites =>
      List.unmodifiable(_favoriteDramas.values);

  Future<void> bootstrap() async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      final config = await client.fetchConfig();
      final catalog = await client.fetchCatalog();
      _syncLocaleWithConfig(config);
      data = AppRuntimeData(
        config: config,
        catalog: catalog.isEmpty ? data.catalog : catalog,
        account: data.account,
        wallet: data.wallet,
        walletLedger: data.walletLedger,
        paymentOptions: data.paymentOptions,
        topupPaymentChannels: data.topupPaymentChannels,
      );
      try {
        final account = await client.fetchMe(deviceId: endUserRef);
        final wallet = await client.fetchWallet(
          deviceId: endUserRef,
        );
        final walletLedger = await _fetchWalletLedgerOrEmpty(
          deviceId: endUserRef,
          accountRefMasked: wallet.accountRefMasked,
        );
        final paymentOptions = await client.fetchPaymentOptions();
        data = AppRuntimeData(
          config: data.config,
          catalog: data.catalog,
          account: account,
          wallet: wallet,
          walletLedger: walletLedger,
          paymentOptions: paymentOptions,
          topupPaymentChannels: data.topupPaymentChannels,
        );
      } catch (walletError) {
        error = walletError;
      }
    } catch (bootstrapError) {
      error = bootstrapError;
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<DramaDetail> fetchDrama(String dramaId) {
    return client.fetchDrama(dramaId);
  }

  Future<PlayAuthorization> authorizePlayback({
    required String dramaId,
    required String episodeId,
    required String endUserRef,
    required String idempotencyKey,
  }) {
    return client.authorizePlayback(
      dramaId: dramaId,
      episodeId: episodeId,
      endUserRef: endUserRef,
      idempotencyKey: idempotencyKey,
    );
  }

  Future<void> refreshWallet({String? deviceId}) async {
    final resolvedDeviceId = deviceId ?? endUserRef;
    try {
      final wallet = await client.fetchWallet(deviceId: resolvedDeviceId);
      final walletLedger = await _fetchWalletLedgerOrEmpty(
        deviceId: resolvedDeviceId,
        accountRefMasked: wallet.accountRefMasked,
      );
      final paymentOptions = await client.fetchPaymentOptions();
      data = AppRuntimeData(
        config: data.config,
        catalog: data.catalog,
        account: data.account,
        wallet: wallet,
        walletLedger: walletLedger,
        paymentOptions: paymentOptions,
        topupPaymentChannels: data.topupPaymentChannels,
      );
      notifyListeners();
    } catch (walletError) {
      error = walletError;
      notifyListeners();
    }
  }

  Future<void> refreshTopupPaymentChannels() async {
    try {
      final channels = await client.fetchTopupPaymentChannels();
      data = AppRuntimeData(
        config: data.config,
        catalog: data.catalog,
        account: data.account,
        wallet: data.wallet,
        walletLedger: data.walletLedger,
        paymentOptions: data.paymentOptions,
        topupPaymentChannels: channels,
      );
      notifyListeners();
    } catch (channelsError) {
      error = channelsError;
      notifyListeners();
    }
  }

  Future<WalletLedger> _fetchWalletLedgerOrEmpty({
    required String? deviceId,
    required String accountRefMasked,
  }) async {
    try {
      return await client.fetchWalletLedger(deviceId: deviceId);
    } catch (_) {
      return WalletLedger(
        requestId: 'wallet_ledger_unavailable',
        ledgerScope: 'consumer',
        accountRefMasked: accountRefMasked,
        entries: const [],
      );
    }
  }

  void continueWithFallback() {
    error = null;
    loading = false;
    notifyListeners();
  }

  void applyAuthenticatedAccount(UserAccount account) {
    data = AppRuntimeData(
      config: data.config,
      catalog: data.catalog,
      account: account,
      wallet: data.wallet,
      walletLedger: data.walletLedger,
      paymentOptions: data.paymentOptions,
      topupPaymentChannels: data.topupPaymentChannels,
    );
    notifyListeners();
  }

  void signOut() {
    data = AppRuntimeData(
      config: data.config,
      catalog: data.catalog,
      account: UserAccount(
        requestId: 'local_sign_out',
        tenantId: data.account?.tenantId ?? data.wallet?.tenantId ?? '',
        accountRefMasked: endUserRef,
        authProviders: const [],
        membershipTier: 'guest',
        deletionEndpoint:
            data.account?.deletionEndpoint ?? '/me/delete-request',
      ),
      wallet: data.wallet,
      walletLedger: data.walletLedger,
      paymentOptions: data.paymentOptions,
      topupPaymentChannels: data.topupPaymentChannels,
    );
    notifyListeners();
  }

  void recordPlayback({
    required String dramaId,
    required String dramaTitle,
    required String episodeId,
    required String episodeTitle,
  }) {
    _watchHistory.removeWhere(
      (entry) => entry.dramaId == dramaId && entry.episodeId == episodeId,
    );
    _watchHistory.insert(
      0,
      PlaybackHistoryEntry(
        dramaId: dramaId,
        dramaTitle: dramaTitle,
        episodeId: episodeId,
        episodeTitle: episodeTitle,
        watchedAt: DateTime.now().toUtc(),
      ),
    );
    if (_watchHistory.length > 20) {
      _watchHistory.removeRange(20, _watchHistory.length);
    }
    notifyListeners();
  }

  bool isFavoriteDrama(String dramaId) => _favoriteDramas.containsKey(dramaId);

  void toggleFavorite({
    required String dramaId,
    required String title,
  }) {
    if (_favoriteDramas.containsKey(dramaId)) {
      _favoriteDramas.remove(dramaId);
    } else {
      _favoriteDramas[dramaId] = FavoriteDrama(
        dramaId: dramaId,
        title: title,
        favoritedAt: DateTime.now().toUtc(),
      );
    }
    notifyListeners();
  }

  void setLocale(String nextLocaleCode) {
    final resolved = _resolveSupportedLocale(
          nextLocaleCode,
          supportedLocaleCodes,
          fallback: localeCode,
        ) ??
        localeCode;
    if (resolved == localeCode) {
      return;
    }
    localeCode = resolved;
    _localeManuallySelected = true;
    notifyListeners();
  }

  void _syncLocaleWithConfig(AppConfig config) {
    final supported = _normalizedLocaleCodes(config.supportedLocales);
    final current = _resolveSupportedLocale(localeCode, supported);
    if (!_localeManuallySelected || current == null) {
      localeCode = _resolveSupportedLocale(
            config.defaultLocale,
            supported,
            fallback: supported.first,
          ) ??
          supported.first;
      return;
    }
    localeCode = current;
  }
}

String _defaultEndUserRef(FlavorConfig flavor) {
  final raw = flavor.brand.tenantCode.toLowerCase();
  final slug = raw
      .replaceAll(RegExp(r'[^a-z0-9]+'), '-')
      .replaceAll(RegExp(r'^-+|-+$'), '');
  return 'anon:${slug.isEmpty ? 'tenant' : slug}-device';
}

String _firstSupportedLocale(List<String> locales) {
  if (locales.isEmpty) {
    return 'en-US';
  }
  for (final locale in locales) {
    if (AppStrings.languageKey(locale) == 'en') {
      return locale;
    }
  }
  return locales.first;
}

List<String> _normalizedLocaleCodes(List<String> locales) {
  final result = <String>[];
  for (final locale in locales) {
    final normalized = _normalizeLocaleCode(locale);
    if (!result.contains(normalized)) {
      result.add(normalized);
    }
  }
  return result.isEmpty ? const ['en-US'] : List.unmodifiable(result);
}

String _normalizeLocaleCode(String locale) {
  final parts = locale
      .split(RegExp('[-_]'))
      .where((part) => part.trim().isNotEmpty)
      .toList();
  if (parts.isEmpty) {
    return 'en-US';
  }
  final language = parts.first.toLowerCase();
  if (parts.length == 1) {
    return language;
  }
  return '$language-${parts[1].toUpperCase()}';
}

String? _resolveSupportedLocale(
  String requestedLocale,
  List<String> supportedLocales, {
  String? fallback,
}) {
  final normalizedRequested = _normalizeLocaleCode(requestedLocale);
  for (final locale in supportedLocales) {
    if (_normalizeLocaleCode(locale) == normalizedRequested) {
      return _normalizeLocaleCode(locale);
    }
  }
  final requestedLanguage = AppStrings.languageKey(normalizedRequested);
  for (final locale in supportedLocales) {
    if (AppStrings.languageKey(locale) == requestedLanguage) {
      return _normalizeLocaleCode(locale);
    }
  }
  return fallback;
}

Color? _parseHexColor(String? value) {
  final raw = value?.trim();
  if (raw == null || raw.isEmpty) {
    return null;
  }
  final hex = raw.startsWith('#') ? raw.substring(1) : raw;
  if (!RegExp(r'^[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$').hasMatch(hex)) {
    return null;
  }
  final argb = hex.length == 6 ? 'FF$hex' : hex;
  return Color(int.parse(argb, radix: 16));
}

class AppRuntimeScope extends InheritedNotifier<AppRuntime> {
  const AppRuntimeScope({
    required AppRuntime runtime,
    required super.child,
    super.key,
  }) : super(notifier: runtime);

  static AppRuntime of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<AppRuntimeScope>();
    assert(scope != null, 'AppRuntimeScope is missing.');
    return scope!.notifier!;
  }

  static AppRuntime? maybeOf(BuildContext context) {
    return context
        .dependOnInheritedWidgetOfExactType<AppRuntimeScope>()
        ?.notifier;
  }
}

class PlaybackHistoryEntry {
  const PlaybackHistoryEntry({
    required this.dramaId,
    required this.dramaTitle,
    required this.episodeId,
    required this.episodeTitle,
    required this.watchedAt,
  });

  final String dramaId;
  final String dramaTitle;
  final String episodeId;
  final String episodeTitle;
  final DateTime watchedAt;
}

class FavoriteDrama {
  const FavoriteDrama({
    required this.dramaId,
    required this.title,
    required this.favoritedAt,
  });

  final String dramaId;
  final String title;
  final DateTime favoritedAt;
}

class AppRuntimeData {
  const AppRuntimeData({
    required this.catalog,
    this.config,
    this.account,
    this.wallet,
    this.walletLedger,
    this.paymentOptions,
    this.topupPaymentChannels,
  });

  final AppConfig? config;
  final List<CatalogDrama> catalog;
  final UserAccount? account;
  final ConsumerWallet? wallet;
  final WalletLedger? walletLedger;
  final PaymentOptions? paymentOptions;
  final TopupPaymentChannels? topupPaymentChannels;

  factory AppRuntimeData.seeded(FlavorConfig flavor) {
    return AppRuntimeData(
      catalog: const [
        CatalogDrama(
          dramaId: 'drama_1',
          title: 'Contract Wife',
          summary:
              'A fake marriage becomes a public fight for power, love, and revenge.',
          posterUrl: 'assets/visuals/poster_01.jpg',
          episodeCount: 68,
          readyEpisodeCount: 24,
          pointPrice: 30,
          language: 'en-US',
          regions: ['US', 'SG'],
          tags: ['Romance', 'Revenge', 'Billionaire'],
          categorySelections: {
            'genre': ['romance', 'revenge'],
            'market': ['US', 'SG'],
          },
        ),
        CatalogDrama(
          dramaId: 'drama_2',
          title: 'Heiress Returns',
          summary:
              'A missing heiress reclaims her name while enemies close in.',
          posterUrl: 'assets/visuals/poster_02.jpg',
          episodeCount: 60,
          readyEpisodeCount: 12,
          pointPrice: 30,
          language: 'en-US',
          regions: ['SG', 'MY'],
          tags: ['Heiress', 'Revenge', 'Romance'],
          categorySelections: {
            'genre': ['heiress', 'revenge', 'romance'],
            'market': ['SG', 'MY'],
          },
        ),
        CatalogDrama(
          dramaId: 'drama_3',
          title: 'Island Heiress',
          summary: 'She vanished from high society and returned with a secret.',
          posterUrl: 'assets/visuals/poster_03.jpg',
          episodeCount: 58,
          readyEpisodeCount: 5,
          pointPrice: 25,
          language: 'en-US',
          regions: ['PH', 'SG'],
          tags: ['Island', 'Heiress', 'Romance'],
          categorySelections: {
            'genre': ['island', 'heiress', 'romance'],
            'market': ['PH', 'SG'],
          },
        ),
        CatalogDrama(
          dramaId: 'drama_4',
          title: "The CEO's Revenge",
          summary: 'After betrayal, a powerful CEO returns in secret.',
          posterUrl: 'assets/visuals/poster_04.jpg',
          episodeCount: 72,
          readyEpisodeCount: 9,
          pointPrice: 35,
          language: 'en-US',
          regions: ['US', 'MY'],
          tags: ['CEO', 'Suspense', 'Trending'],
          categorySelections: {
            'genre': ['ceo', 'suspense', 'trending'],
            'market': ['US', 'MY'],
          },
        ),
        CatalogDrama(
          dramaId: 'drama_5',
          title: 'Hidden Vow',
          summary: 'The wedding was staged. The danger was real.',
          posterUrl: 'assets/visuals/poster_05.jpg',
          episodeCount: 46,
          readyEpisodeCount: 1,
          pointPrice: 20,
          language: 'en-US',
          regions: ['MY', 'ID'],
          tags: ['Wedding', 'Family', 'Secret'],
          categorySelections: {
            'genre': ['wedding', 'family', 'secret'],
            'market': ['MY', 'ID'],
          },
        ),
      ],
      account: const UserAccount(
        requestId: 'seed_me',
        tenantId: 'tenant_seed',
        accountRefMasked: 'anon:s...seed',
        authProviders: ['email'],
        membershipTier: 'guest',
        deletionEndpoint: '/me/delete-request',
      ),
      wallet: const ConsumerWallet(
        requestId: 'seed_wallet',
        tenantId: 'tenant_seed',
        accountRefMasked: 'anon:s...seed',
        ledgerScope: 'consumer',
        balanceCoins: 0,
        membershipTier: 'guest',
        currency: 'coins',
      ),
      walletLedger: const WalletLedger(
        requestId: 'seed_wallet_ledger',
        ledgerScope: 'consumer',
        accountRefMasked: 'anon:s...seed',
        entries: [
          WalletLedgerEntry(
            ledgerId: 'seed_ledger_welcome',
            type: 'welcome',
            title: 'Welcome bonus',
            pointsDelta: 0,
            balanceAfter: 0,
            createdAt: 'demo',
            status: 'posted',
          ),
        ],
      ),
      paymentOptions: PaymentOptions(
        requestId: 'seed_payment_options',
        providers: flavor.capabilities.visiblePaymentProviders
            .map((provider) => provider.wireValue)
            .toList(),
        packages: defaultPaymentPackages,
        externalPaymentsAllowed: flavor.capabilities.externalPaymentsAllowed,
        ledgerScope: 'consumer',
        storeComplianceMode: flavor.capabilities.storeComplianceMode.wireValue,
      ),
      topupPaymentChannels: const TopupPaymentChannels(
        requestId: 'seed_topup_channels',
        channels: [],
      ),
    );
  }
}
