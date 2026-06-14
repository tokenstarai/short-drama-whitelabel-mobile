import '../config/app_capabilities.dart';

List<String> _stringList(Object? value) {
  if (value is List) {
    return value.whereType<String>().toList();
  }
  return const [];
}

int _intValue(Object? value, {int fallback = 0}) {
  if (value is int) {
    return value;
  }
  if (value is num) {
    return value.toInt();
  }
  if (value is String) {
    return int.tryParse(value) ?? fallback;
  }
  return fallback;
}

StyleTemplate _styleTemplateFromWire(String? value) {
  return StyleTemplate.values.firstWhere(
    (template) => template.wireValue == value,
    orElse: () => StyleTemplate.hongguoInspired,
  );
}

StoreComplianceMode _storeComplianceModeFromWire(String? value) {
  return StoreComplianceMode.values.firstWhere(
    (mode) => mode.wireValue == value,
    orElse: () => StoreComplianceMode.appStore,
  );
}

AuthProvider? _authProviderFromWire(String value) {
  for (final provider in AuthProvider.values) {
    if (provider.wireValue == value) {
      return provider;
    }
  }
  return null;
}

ConsumerPaymentProvider? _consumerPaymentProviderFromWire(String value) {
  for (final provider in ConsumerPaymentProvider.values) {
    if (provider.wireValue == value) {
      return provider;
    }
  }
  return null;
}

Set<AuthProvider> _authProvidersFromWire(Object? value) {
  final providers = _stringList(
    value,
  ).map(_authProviderFromWire).whereType<AuthProvider>().toSet();
  return providers.isEmpty ? {AuthProvider.email} : providers;
}

Set<ConsumerPaymentProvider> _consumerPaymentProvidersFromWire(Object? value) {
  return _stringList(value)
      .map(_consumerPaymentProviderFromWire)
      .whereType<ConsumerPaymentProvider>()
      .toSet();
}

class AppLegalUrls {
  const AppLegalUrls({
    required this.customerServiceUrl,
    required this.termsUrl,
    required this.privacyUrl,
  });

  final String customerServiceUrl;
  final String termsUrl;
  final String privacyUrl;

  factory AppLegalUrls.fromJson(Map<String, dynamic> json) {
    return AppLegalUrls(
      customerServiceUrl: json['customerServiceUrl'] as String? ?? '#',
      termsUrl: json['termsUrl'] as String? ?? '#',
      privacyUrl: json['privacyUrl'] as String? ?? '#',
    );
  }

  Map<String, Object> toJson() {
    return {
      'customerServiceUrl': customerServiceUrl,
      'termsUrl': termsUrl,
      'privacyUrl': privacyUrl,
    };
  }
}

class AppConfig {
  const AppConfig({
    required this.requestId,
    required this.tenantId,
    required this.appKey,
    required this.appName,
    required this.brandName,
    required this.defaultLocale,
    required this.supportedLocales,
    this.primaryColor,
    required this.features,
    required this.capabilities,
    required this.legal,
  });

  final String requestId;
  final String tenantId;
  final String appKey;
  final String appName;
  final String brandName;
  final String defaultLocale;
  final List<String> supportedLocales;
  final String? primaryColor;
  final Map<String, bool> features;
  final AppCapabilities capabilities;
  final AppLegalUrls legal;

  factory AppConfig.fromJson(Map<String, dynamic> json) {
    final config = json['config'] as Map<String, dynamic>;
    final tenant = config['tenant'] as Map<String, dynamic>;
    final features = config['features'] as Map<String, dynamic>;
    final app = config['app'] as Map<String, dynamic>? ?? const {};
    final theme = config['theme'] as Map<String, dynamic>? ?? const {};
    final legal = config['legal'] as Map<String, dynamic>? ?? const {};
    final supportedLocales = List<String>.from(
      tenant['supportedLocales'] as List<dynamic>? ?? const ['en-US'],
    );
    return AppConfig(
      requestId: json['requestId'] as String,
      tenantId: tenant['id'] as String? ?? 'tenant',
      appKey: tenant['appKey'] as String? ?? '',
      appName: tenant['name'] as String,
      brandName: (tenant['brandName'] as String?) ?? (tenant['name'] as String),
      defaultLocale: tenant['defaultLocale'] as String? ??
          (supportedLocales.isEmpty ? 'en-US' : supportedLocales.first),
      supportedLocales: supportedLocales,
      primaryColor: theme['primaryColor'] as String?,
      features: features.map((key, value) => MapEntry(key, value == true)),
      capabilities: AppCapabilities(
        styleTemplate: _styleTemplateFromWire(app['styleTemplate'] as String?),
        storeComplianceMode: _storeComplianceModeFromWire(
          app['storeComplianceMode'] as String?,
        ),
        authProviders: _authProvidersFromWire(app['authProviders']),
        consumerPaymentProviders: _consumerPaymentProvidersFromWire(
          app['consumerPaymentProviders'],
        ),
      ),
      legal: AppLegalUrls.fromJson(legal),
    );
  }

  Map<String, Object> toPublicJson() {
    return {
      'requestId': requestId,
      'tenantId': tenantId,
      'appKey': appKey,
      'appName': appName,
      'brandName': brandName,
      'defaultLocale': defaultLocale,
      'supportedLocales': supportedLocales,
      if (primaryColor != null) 'primaryColor': primaryColor!,
      'features': features,
      ...capabilities.toPublicJson(),
      'legal': legal.toJson(),
    };
  }
}

class CatalogDrama {
  const CatalogDrama({
    required this.dramaId,
    required this.title,
    required this.posterUrl,
    required this.episodeCount,
    required this.readyEpisodeCount,
    required this.pointPrice,
  });

  final String dramaId;
  final String title;
  final String posterUrl;
  final int episodeCount;
  final int readyEpisodeCount;
  final int pointPrice;

  factory CatalogDrama.fromJson(Map<String, dynamic> json) {
    return CatalogDrama(
      dramaId: json['dramaId'] as String,
      title: json['title'] as String,
      posterUrl: json['posterUrl'] as String,
      episodeCount: json['episodeCount'] as int,
      readyEpisodeCount: json['readyEpisodeCount'] as int,
      pointPrice: json['pointPrice'] as int,
    );
  }
}

class DramaEpisode {
  const DramaEpisode({
    required this.episodeId,
    required this.episodeNumber,
    required this.title,
    required this.pointPrice,
    required this.ready,
    required this.locked,
  });

  final String episodeId;
  final int episodeNumber;
  final String title;
  final int pointPrice;
  final bool ready;
  final bool locked;

  factory DramaEpisode.fromJson(Map<String, dynamic> json) {
    return DramaEpisode(
      episodeId: json['episodeId'] as String,
      episodeNumber: json['episodeNumber'] as int,
      title: json['title'] as String,
      pointPrice: json['pointPrice'] as int,
      ready: json['ready'] == true,
      locked: json['locked'] == true,
    );
  }
}

class DramaDetail {
  const DramaDetail({required this.drama, required this.episodes});

  final CatalogDrama drama;
  final List<DramaEpisode> episodes;

  factory DramaDetail.fromJson(Map<String, dynamic> json) {
    final drama = json['drama'] as Map<String, dynamic>;
    return DramaDetail(
      drama: CatalogDrama.fromJson(drama),
      episodes: (drama['episodes'] as List<dynamic>)
          .map((item) => DramaEpisode.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }
}

class PlayAuthorization {
  const PlayAuthorization({
    required this.requestId,
    required this.grantId,
    required this.playerUrl,
    required this.manifestHost,
    required this.tokenExpiresAt,
    required this.points,
    required this.balanceAfter,
  });

  final String requestId;
  final String grantId;
  final String playerUrl;
  final String manifestHost;
  final String tokenExpiresAt;
  final int points;
  final int balanceAfter;

  factory PlayAuthorization.fromJson(Map<String, dynamic> json) {
    final charge = json['charge'] as Map<String, dynamic>;
    final playback = json['playback'] as Map<String, dynamic>;
    return PlayAuthorization(
      requestId: json['requestId'] as String,
      grantId: json['grantId'] as String,
      playerUrl: (playback['playerUrl'] ?? playback['iframeUrl']) as String,
      manifestHost: playback['manifestHost'] as String? ?? 'stream',
      tokenExpiresAt: playback['tokenExpiresAt'] as String,
      points: charge['points'] as int,
      balanceAfter: charge['balanceAfter'] as int,
    );
  }
}

class ConsumerWallet {
  const ConsumerWallet({
    required this.requestId,
    required this.tenantId,
    required this.accountRefMasked,
    required this.ledgerScope,
    required this.balanceCoins,
    required this.membershipTier,
    required this.currency,
  });

  final String requestId;
  final String tenantId;
  final String accountRefMasked;
  final String ledgerScope;
  final int balanceCoins;
  final String membershipTier;
  final String currency;

  factory ConsumerWallet.fromJson(Map<String, dynamic> json) {
    final wallet = json['wallet'] as Map<String, dynamic>;
    return ConsumerWallet(
      requestId: json['requestId'] as String,
      tenantId: wallet['tenantId'] as String? ?? '',
      accountRefMasked: wallet['accountRefMasked'] as String,
      ledgerScope: wallet['ledgerScope'] as String,
      balanceCoins: wallet['balanceCoins'] as int,
      membershipTier: wallet['membershipTier'] as String? ?? 'guest',
      currency: wallet['currency'] as String? ?? 'coins',
    );
  }
}

class WalletLedgerEntry {
  const WalletLedgerEntry({
    required this.ledgerId,
    required this.type,
    required this.title,
    required this.pointsDelta,
    required this.balanceAfter,
    required this.createdAt,
    required this.status,
  });

  final String ledgerId;
  final String type;
  final String title;
  final int pointsDelta;
  final int balanceAfter;
  final String createdAt;
  final String status;

  factory WalletLedgerEntry.fromJson(Map<String, dynamic> json) {
    final type = (json['type'] ?? json['kind'] ?? json['eventType']) as String?;
    return WalletLedgerEntry(
      ledgerId: (json['ledgerId'] ?? json['id'] ?? '') as String,
      type: type ?? 'wallet',
      title: (json['title'] ?? json['description'] ?? type ?? 'Wallet entry')
          as String,
      pointsDelta: _intValue(json['pointsDelta'] ?? json['coinsDelta']),
      balanceAfter: _intValue(json['balanceAfter']),
      createdAt: (json['createdAt'] ?? json['created_at'] ?? '') as String,
      status: (json['status'] ?? 'posted') as String,
    );
  }
}

class WalletLedger {
  const WalletLedger({
    required this.requestId,
    required this.ledgerScope,
    required this.accountRefMasked,
    required this.entries,
  });

  final String requestId;
  final String ledgerScope;
  final String accountRefMasked;
  final List<WalletLedgerEntry> entries;

  factory WalletLedger.fromJson(Map<String, dynamic> json) {
    final entries = json['entries'] as List<dynamic>? ?? const [];
    return WalletLedger(
      requestId: json['requestId'] as String,
      ledgerScope: json['ledgerScope'] as String? ?? 'consumer',
      accountRefMasked: json['accountRefMasked'] as String? ?? '',
      entries: entries
          .map(
            (entry) =>
                WalletLedgerEntry.fromJson(entry as Map<String, dynamic>),
          )
          .toList(),
    );
  }
}

class PaymentOptions {
  const PaymentOptions({
    required this.requestId,
    required this.providers,
    required this.packages,
    required this.externalPaymentsAllowed,
    required this.ledgerScope,
    required this.storeComplianceMode,
  });

  final String requestId;
  final List<String> providers;
  final List<PaymentPackage> packages;
  final bool externalPaymentsAllowed;
  final String ledgerScope;
  final String storeComplianceMode;

  factory PaymentOptions.fromJson(Map<String, dynamic> json) {
    final packageRows = json['packages'] as List<dynamic>? ?? const [];
    final parsedPackages = packageRows
        .map(
          (item) => PaymentPackage.fromJson(item as Map<String, dynamic>),
        )
        .where((item) => item.packageId.isNotEmpty)
        .toList();
    return PaymentOptions(
      requestId: json['requestId'] as String,
      providers: _stringList(json['providers']),
      packages:
          parsedPackages.isEmpty ? defaultPaymentPackages : parsedPackages,
      externalPaymentsAllowed: json['externalPaymentsAllowed'] == true,
      ledgerScope: json['ledgerScope'] as String? ?? 'consumer',
      storeComplianceMode:
          json['storeComplianceMode'] as String? ?? 'app_store',
    );
  }
}

class TopupPaymentChannels {
  const TopupPaymentChannels({
    required this.requestId,
    required this.channels,
  });

  final String requestId;
  final List<TopupPaymentChannel> channels;

  factory TopupPaymentChannels.fromJson(Map<String, dynamic> json) {
    final channels = json['channels'] as List<dynamic>? ?? const [];
    return TopupPaymentChannels(
      requestId: json['requestId'] as String,
      channels: channels
          .map(
            (channel) =>
                TopupPaymentChannel.fromJson(channel as Map<String, dynamic>),
          )
          .toList(),
    );
  }
}

class TopupPaymentChannel {
  const TopupPaymentChannel({
    required this.id,
    required this.country,
    required this.method,
    required this.name,
    required this.summary,
    required this.enabled,
    this.qrFileName,
    this.qrImageUrl,
  });

  final String id;
  final String country;
  final String method;
  final String name;
  final String summary;
  final bool enabled;
  final String? qrFileName;
  final String? qrImageUrl;

  factory TopupPaymentChannel.fromJson(Map<String, dynamic> json) {
    return TopupPaymentChannel(
      id: json['id'] as String,
      country: json['country'] as String? ?? 'GLOBAL',
      method: json['method'] as String? ?? 'payment',
      name: json['name'] as String? ?? 'Payment channel',
      summary: json['summary'] as String? ?? 'Configured',
      enabled: json['enabled'] == true,
      qrFileName: json['qrFileName'] as String?,
      qrImageUrl: json['qrImageUrl'] as String?,
    );
  }

  Map<String, Object?> toPublicJson() {
    return {
      'id': id,
      'country': country,
      'method': method,
      'name': name,
      'summary': summary,
      'enabled': enabled,
      if (qrFileName != null) 'qrFileName': qrFileName,
      if (qrImageUrl != null) 'qrImageUrl': qrImageUrl,
    };
  }
}

class PaymentPackage {
  const PaymentPackage({
    required this.packageId,
    required this.title,
    required this.coins,
    required this.bonusCoins,
    required this.amountOriginal,
    required this.currency,
    String? storeProductId,
  }) : storeProductId = storeProductId ?? packageId;

  final String packageId;
  final String title;
  final String storeProductId;
  final int coins;
  final int bonusCoins;
  final int amountOriginal;
  final String currency;

  int get totalCoins => coins + bonusCoins;

  factory PaymentPackage.fromJson(Map<String, dynamic> json) {
    return PaymentPackage(
      packageId: json['packageId'] as String? ?? json['id'] as String? ?? '',
      title: json['title'] as String? ?? 'Coin package',
      storeProductId: json['storeProductId'] as String? ??
          json['productId'] as String? ??
          json['packageId'] as String? ??
          json['id'] as String? ??
          '',
      coins: _intValue(json['coins']),
      bonusCoins: _intValue(json['bonusCoins']),
      amountOriginal: _intValue(json['amountOriginal'] ?? json['amount']),
      currency: json['currency'] as String? ?? 'USD',
    );
  }
}

const defaultPaymentPackages = [
  PaymentPackage(
    packageId: 'coins_100',
    title: '100 coins',
    storeProductId: 'com.shortdrama.coins100',
    coins: 100,
    bonusCoins: 0,
    amountOriginal: 9,
    currency: 'USD',
  ),
  PaymentPackage(
    packageId: 'coins_300',
    title: '300 coins',
    storeProductId: 'com.shortdrama.coins300',
    coins: 300,
    bonusCoins: 30,
    amountOriginal: 24,
    currency: 'USD',
  ),
  PaymentPackage(
    packageId: 'coins_700',
    title: '700 coins',
    storeProductId: 'com.shortdrama.coins700',
    coins: 700,
    bonusCoins: 100,
    amountOriginal: 49,
    currency: 'USD',
  ),
];

class PaymentIntentResult {
  const PaymentIntentResult({
    required this.requestId,
    required this.status,
    required this.orderId,
    required this.provider,
    required this.packageId,
    required this.amountOriginal,
    required this.currency,
    required this.ledgerScope,
    required this.storeComplianceMode,
    this.checkoutUrl,
  });

  final String requestId;
  final String status;
  final String orderId;
  final String provider;
  final String packageId;
  final int amountOriginal;
  final String currency;
  final String ledgerScope;
  final String storeComplianceMode;
  final String? checkoutUrl;

  factory PaymentIntentResult.fromJson(Map<String, dynamic> json) {
    return PaymentIntentResult(
      requestId: json['requestId'] as String,
      status: json['status'] as String,
      orderId: json['orderId'] as String,
      provider: json['provider'] as String,
      packageId: json['packageId'] as String,
      amountOriginal: json['amountOriginal'] as int,
      currency: json['currency'] as String,
      ledgerScope: json['ledgerScope'] as String? ?? 'consumer',
      storeComplianceMode:
          json['storeComplianceMode'] as String? ?? 'app_store',
      checkoutUrl: json['checkoutUrl'] as String?,
    );
  }
}

class EmailAuthStartResult {
  const EmailAuthStartResult({
    required this.requestId,
    required this.status,
    required this.provider,
    required this.challengeId,
    required this.emailMasked,
  });

  final String requestId;
  final String status;
  final String provider;
  final String challengeId;
  final String emailMasked;

  factory EmailAuthStartResult.fromJson(Map<String, dynamic> json) {
    return EmailAuthStartResult(
      requestId: json['requestId'] as String,
      status: json['status'] as String,
      provider: json['provider'] as String,
      challengeId: json['challengeId'] as String,
      emailMasked: json['emailMasked'] as String,
    );
  }
}

class EmailAuthVerifyResult {
  const EmailAuthVerifyResult({
    required this.requestId,
    required this.status,
    required this.provider,
    required this.account,
  });

  final String requestId;
  final String status;
  final String provider;
  final UserAccount account;

  factory EmailAuthVerifyResult.fromJson(Map<String, dynamic> json) {
    return EmailAuthVerifyResult(
      requestId: json['requestId'] as String,
      status: json['status'] as String,
      provider: json['provider'] as String,
      account: UserAccount.fromJson({
        'requestId': json['requestId'],
        'account': json['account'],
      }),
    );
  }
}

class OAuthStartResult {
  const OAuthStartResult({
    required this.requestId,
    required this.status,
    required this.provider,
    required this.oauthStartId,
    required this.tenantId,
    required this.authUrl,
  });

  final String requestId;
  final String status;
  final String provider;
  final String oauthStartId;
  final String tenantId;
  final String authUrl;

  factory OAuthStartResult.fromJson(Map<String, dynamic> json) {
    return OAuthStartResult(
      requestId: json['requestId'] as String,
      status: json['status'] as String,
      provider: json['provider'] as String,
      oauthStartId: json['oauthStartId'] as String,
      tenantId: json['tenantId'] as String,
      authUrl: json['authUrl'] as String? ?? '',
    );
  }
}

class OAuthCompleteResult {
  const OAuthCompleteResult({
    required this.requestId,
    required this.status,
    required this.provider,
    required this.account,
  });

  final String requestId;
  final String status;
  final String provider;
  final UserAccount account;

  factory OAuthCompleteResult.fromJson(Map<String, dynamic> json) {
    return OAuthCompleteResult(
      requestId: json['requestId'] as String,
      status: json['status'] as String,
      provider: json['provider'] as String,
      account: UserAccount.fromJson({
        'requestId': json['requestId'],
        'account': json['account'],
      }),
    );
  }
}

class UserAccount {
  const UserAccount({
    required this.requestId,
    required this.tenantId,
    required this.accountRefMasked,
    required this.authProviders,
    required this.membershipTier,
    required this.deletionEndpoint,
  });

  final String requestId;
  final String tenantId;
  final String accountRefMasked;
  final List<String> authProviders;
  final String membershipTier;
  final String deletionEndpoint;

  factory UserAccount.fromJson(Map<String, dynamic> json) {
    final account = json['account'] as Map<String, dynamic>;
    return UserAccount(
      requestId: json['requestId'] as String,
      tenantId: account['tenantId'] as String? ?? '',
      accountRefMasked: account['accountRefMasked'] as String,
      authProviders: _stringList(account['authProviders']),
      membershipTier: account['membershipTier'] as String? ?? 'guest',
      deletionEndpoint:
          account['deletionEndpoint'] as String? ?? '/me/delete-request',
    );
  }
}

class CardRedeemResult {
  const CardRedeemResult({
    required this.requestId,
    required this.status,
    required this.creditedPoints,
    required this.balanceAfter,
  });

  final String requestId;
  final String status;
  final int creditedPoints;
  final int balanceAfter;

  factory CardRedeemResult.fromJson(Map<String, dynamic> json) {
    return CardRedeemResult(
      requestId: json['requestId'] as String,
      status: json['status'] as String,
      creditedPoints: json['creditedPoints'] as int,
      balanceAfter: json['balanceAfter'] as int,
    );
  }
}

class OfflineTopupApplicationResult {
  const OfflineTopupApplicationResult({
    required this.requestId,
    required this.status,
    required this.applicationId,
    required this.requestedPoints,
  });

  final String requestId;
  final String status;
  final String applicationId;
  final int requestedPoints;

  factory OfflineTopupApplicationResult.fromJson(Map<String, dynamic> json) {
    return OfflineTopupApplicationResult(
      requestId: json['requestId'] as String,
      status: json['status'] as String,
      applicationId: json['applicationId'] as String,
      requestedPoints: json['requestedPoints'] as int,
    );
  }
}

class FeedbackResult {
  const FeedbackResult({
    required this.requestId,
    required this.status,
    required this.feedbackId,
    required this.category,
    required this.hasMessage,
  });

  final String requestId;
  final String status;
  final String feedbackId;
  final String category;
  final bool hasMessage;

  factory FeedbackResult.fromJson(Map<String, dynamic> json) {
    return FeedbackResult(
      requestId: json['requestId'] as String,
      status: json['status'] as String,
      feedbackId: json['feedbackId'] as String,
      category: json['category'] as String,
      hasMessage: json['hasMessage'] == true,
    );
  }
}

class AccountDeletionRequestResult {
  const AccountDeletionRequestResult({
    required this.requestId,
    required this.status,
    required this.deletionRequestId,
    required this.accountRefMasked,
  });

  final String requestId;
  final String status;
  final String deletionRequestId;
  final String accountRefMasked;

  factory AccountDeletionRequestResult.fromJson(Map<String, dynamic> json) {
    return AccountDeletionRequestResult(
      requestId: json['requestId'] as String,
      status: json['status'] as String,
      deletionRequestId: json['deletionRequestId'] as String,
      accountRefMasked: json['accountRefMasked'] as String,
    );
  }
}

class AppApiException implements Exception {
  const AppApiException({
    required this.code,
    required this.message,
    required this.requestId,
  });

  final String code;
  final String message;
  final String requestId;

  @override
  String toString() => '$code: $message ($requestId)';
}
