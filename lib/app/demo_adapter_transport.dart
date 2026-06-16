import 'dart:convert';

import '../core/api/app_models.dart';
import '../core/api/tenant_adapter_client.dart';
import '../flavor/flavor.dart';
import 'app_runtime.dart';

class DemoAdapterTransport implements AdapterTransport {
  DemoAdapterTransport({
    required this.flavor,
    String? endUserRef,
  })  : endUserRef = endUserRef ?? _demoEndUserRef(flavor),
        _seeded = AppRuntimeData.seeded(flavor) {
    _ledger.add(
      _ledgerEntry(
        id: 'demo_welcome',
        type: 'welcome',
        title: 'Demo welcome bonus',
        delta: _balanceCoins,
        balanceAfter: _balanceCoins,
      ),
    );
  }

  final FlavorConfig flavor;
  final String endUserRef;
  final AppRuntimeData _seeded;
  final List<Map<String, Object?>> _ledger = [];
  int _balanceCoins = 480;
  int _sequence = 0;
  String _membershipTier = 'demo';
  List<String> _authProviders = const ['email'];

  @override
  Future<AdapterResponse> send(AdapterRequest request) async {
    final path = request.path.split('?').first;
    if (request.method == 'GET' && path == '/config') {
      return _ok(_configJson());
    }
    if (request.method == 'GET' && path == '/catalog') {
      return _ok({
        'requestId': _requestId('catalog'),
        'status': 'ok',
        'items': _seeded.catalog.map(_catalogDramaJson).toList(),
      });
    }
    if (request.method == 'GET' && path.startsWith('/dramas/')) {
      final dramaId = Uri.decodeComponent(path.substring('/dramas/'.length));
      final drama = _dramaById(dramaId);
      if (drama == null) {
        return _error('APP_NOT_FOUND', 'Demo drama not found.', 404);
      }
      return _ok(_dramaDetailJson(drama));
    }
    if (request.method == 'POST' && path == '/play') {
      return _handlePlay(request);
    }
    if (request.method == 'GET' && path == '/me') {
      return _ok(_accountJson(requestId: _requestId('me')));
    }
    if (request.method == 'GET' && path == '/wallet') {
      return _ok(_walletJson(requestId: _requestId('wallet')));
    }
    if (request.method == 'GET' && path == '/wallet/ledger') {
      return _ok(_walletLedgerJson(requestId: _requestId('ledger')));
    }
    if (request.method == 'GET' && path == '/payment/options') {
      return _ok(_paymentOptionsJson(requestId: _requestId('pay_options')));
    }
    if (request.method == 'GET' && path == '/topups/payment-channels') {
      return _ok(_topupChannelsJson());
    }
    if (request.method == 'POST' && path == '/payment/intents') {
      return _handlePaymentIntent(request);
    }
    if (request.method == 'POST' && path == '/payment/store-purchases/verify') {
      return _handleStorePurchaseVerify(request);
    }
    if (request.method == 'POST' && path == '/payment/offline-applications') {
      return _handleOfflineApplication(request);
    }
    if (request.method == 'POST' && path == '/topups/offline-applications') {
      return _handleOfficialOfflineApplication(request);
    }
    if (request.method == 'POST' && path == '/payment/card-redeem') {
      return _handleCardRedeem(request);
    }
    if (request.method == 'POST' && path == '/cards/redeem') {
      return _handleCardRedeem(request);
    }
    if (request.method == 'POST' && path == '/auth/email/start') {
      return _handleEmailStart(request);
    }
    if (request.method == 'POST' && path == '/auth/email/verify') {
      return _handleEmailVerify(request);
    }
    if (request.method == 'POST' && path.startsWith('/auth/oauth/')) {
      return _handleOAuth(request, path);
    }
    if (request.method == 'POST' && path == '/feedback') {
      return _ok({
        'requestId': _requestId('feedback'),
        'status': 'accepted',
        'feedbackId': 'demo_feedback_$_sequence',
        'category': request.body?['category'] ?? 'general',
        'hasMessage': (request.body?['message'] as String?)?.isNotEmpty == true,
      });
    }
    if (request.method == 'POST' && path == '/me/delete-request') {
      return _ok({
        'requestId': _requestId('delete'),
        'status': 'accepted',
        'deletionRequestId': 'demo_delete_$_sequence',
        'accountRefMasked': _maskedAccountRef,
      });
    }
    return _error('APP_NOT_FOUND', 'Demo route not configured.', 404);
  }

  AdapterResponse _handlePlay(AdapterRequest request) {
    final dramaId = request.body?['dramaId'] as String?;
    final episodeId = request.body?['episodeId'] as String?;
    if (dramaId == null || episodeId == null) {
      return _error('APP_INVALID_REQUEST', 'Missing drama or episode.', 400);
    }
    final drama = _dramaById(dramaId);
    if (drama == null) {
      return _error('APP_NOT_FOUND', 'Demo drama not found.', 404);
    }
    final episode = _episodesFor(drama).firstWhere(
      (item) => item.episodeId == episodeId,
      orElse: () => const DramaEpisode(
        episodeId: '',
        episodeNumber: 0,
        title: '',
        pointPrice: 0,
        ready: false,
        locked: false,
      ),
    );
    if (episode.episodeId.isEmpty || !episode.ready) {
      return _error('APP_EPISODE_NOT_READY', 'Episode is not ready.', 409);
    }
    final charge = episode.locked ? episode.pointPrice : 0;
    if (_balanceCoins < charge) {
      return _error('APP_INSUFFICIENT_BALANCE', 'Insufficient balance.', 402);
    }
    if (charge > 0) {
      _balanceCoins -= charge;
      _ledger.insert(
        0,
        _ledgerEntry(
          id: 'demo_play_$_sequence',
          type: 'play',
          title: '${drama.title} - ${episode.title}',
          delta: -charge,
          balanceAfter: _balanceCoins,
        ),
      );
    }
    return _ok({
      'requestId': _requestId('play'),
      'status': 'authorized',
      'grantId': 'demo_grant_$_sequence',
      'charge': {
        'points': charge,
        'balanceAfter': _balanceCoins,
      },
      'playback': {
        'playerUrl':
            'https://flutter.github.io/assets-for-api-docs/assets/videos/bee.mp4',
        'manifestHost': 'demo-local',
        'tokenExpiresAt': DateTime.now()
            .toUtc()
            .add(const Duration(minutes: 15))
            .toIso8601String(),
      },
    });
  }

  AdapterResponse _handlePaymentIntent(AdapterRequest request) {
    final provider = request.body?['provider'] as String? ?? 'stripe';
    final packageId = request.body?['packageId'] as String?;
    final package = _packageById(packageId);
    if (package == null) {
      return _error('APP_PAYMENT_PACKAGE_NOT_FOUND', 'Package not found.', 404);
    }
    _creditWallet(
      package.totalCoins,
      '$provider demo recharge',
      type: provider,
    );
    return _ok({
      'requestId': _requestId('intent'),
      'status': 'demo_paid',
      'orderId': 'demo_order_$_sequence',
      'provider': provider,
      'packageId': package.packageId,
      'amountOriginal': package.amountOriginal,
      'currency': package.currency,
      'ledgerScope': 'consumer',
      'storeComplianceMode': flavor.capabilities.storeComplianceMode.wireValue,
    });
  }

  AdapterResponse _handleStorePurchaseVerify(AdapterRequest request) {
    final provider = request.body?['provider'] as String? ?? 'iap';
    final packageId = request.body?['packageId'] as String?;
    final package = _packageById(packageId);
    if (package == null) {
      return _error('APP_PAYMENT_PACKAGE_NOT_FOUND', 'Package not found.', 404);
    }
    _creditWallet(
      package.totalCoins,
      '$provider demo store purchase',
      type: provider,
    );
    return _ok({
      'requestId': _requestId('store_verify'),
      'status': 'verified',
      'orderId': 'demo_store_$_sequence',
      'provider': provider,
      'packageId': package.packageId,
      'amountOriginal': package.amountOriginal,
      'currency': package.currency,
      'ledgerScope': 'consumer',
      'storeComplianceMode': flavor.capabilities.storeComplianceMode.wireValue,
    });
  }

  AdapterResponse _handleOfflineApplication(AdapterRequest request) {
    final provider = request.body?['provider'] as String? ?? 'bank_transfer';
    final requestedCoins = _intValue(
      request.body?['requestedCoins'] ?? request.body?['requestedPoints'],
      fallback: 0,
    );
    _ledger.insert(
      0,
      _ledgerEntry(
        id: 'demo_offline_$_sequence',
        type: provider,
        title: '$provider review pending',
        delta: 0,
        balanceAfter: _balanceCoins,
        status: 'pending',
      ),
    );
    return _ok({
      'requestId': _requestId('offline'),
      'status': 'pending_review',
      'applicationId': 'demo_offline_$_sequence',
      'requestedPoints': requestedCoins,
      'requestedCoins': requestedCoins,
    }, statusCode: 202);
  }

  AdapterResponse _handleOfficialOfflineApplication(AdapterRequest request) {
    final requestedPoints = _intValue(
      request.body?['requestedPoints'] ?? request.body?['requestedCoins'],
      fallback: 0,
    );
    return _ok({
      'requestId': _requestId('official_offline'),
      'status': 'demo_pending_review',
      'applicationId': 'demo_official_$_sequence',
      'requestedPoints': requestedPoints,
    }, statusCode: 202);
  }

  AdapterResponse _handleCardRedeem(AdapterRequest request) {
    final code = (request.body?['cardCode'] as String?)?.trim() ?? '';
    if (code.isEmpty) {
      return _error('APP_INVALID_REQUEST', 'Card code is required.', 400);
    }
    final credited = code.toUpperCase().contains('VIP') ? 700 : 120;
    _creditWallet(credited, 'Point card redeemed', type: 'point_card');
    return _ok({
      'requestId': _requestId('card'),
      'status': 'redeemed',
      'creditedCoins': credited,
      'creditedPoints': credited,
      'balanceAfter': _balanceCoins,
    });
  }

  AdapterResponse _handleEmailStart(AdapterRequest request) {
    final email = (request.body?['email'] as String?)?.trim();
    if (email == null || email.isEmpty) {
      return _error('APP_INVALID_REQUEST', 'Email is required.', 400);
    }
    return _ok({
      'requestId': _requestId('email_start'),
      'status': 'accepted',
      'provider': 'email',
      'challengeId': 'demo_email_$_sequence',
      'emailMasked': _maskEmail(email),
    }, statusCode: 202);
  }

  AdapterResponse _handleEmailVerify(AdapterRequest request) {
    _membershipTier = 'registered';
    _authProviders = const ['email'];
    return _ok({
      'requestId': _requestId('email_verify'),
      'status': 'verified',
      'provider': 'email',
      'account': _accountBody(),
    });
  }

  AdapterResponse _handleOAuth(AdapterRequest request, String path) {
    final segments = path.split('/');
    if (segments.length < 5) {
      return _error('APP_INVALID_REQUEST', 'OAuth provider is missing.', 400);
    }
    final provider = segments[3];
    final action = segments[4];
    if (action == 'start') {
      return _ok({
        'requestId': _requestId('oauth_start'),
        'status': 'ready',
        'provider': provider,
        'oauthStartId': 'demo_oauth_${provider}_$_sequence',
        'tenantId': _tenantId,
        'authUrl':
            'https://demo.coolshow.local/oauth/$provider?oauthStartId=demo_oauth_${provider}_$_sequence',
      });
    }
    if (action == 'complete') {
      _membershipTier = 'registered';
      _authProviders = ['email', provider];
      return _ok({
        'requestId': _requestId('oauth_complete'),
        'status': 'verified',
        'provider': provider,
        'account': _accountBody(),
      });
    }
    return _error('APP_INVALID_REQUEST', 'OAuth action is unsupported.', 400);
  }

  Map<String, Object?> _configJson() {
    final capabilities = flavor.capabilities;
    return {
      'requestId': _requestId('config'),
      'status': 'ok',
      'config': {
        'tenant': {
          'id': _tenantId,
          'appKey': 'pk_demo_${flavor.brand.tenantCode}',
          'name': flavor.brand.appName,
          'brandName': flavor.brand.appName,
          'defaultLocale': flavor.brand.supportedLocales.first,
          'supportedLocales': flavor.brand.supportedLocales,
        },
        'features': {
          'enableCardRedeem': flavor.features.enableCardRedeem,
          'enableOfflineTopup': flavor.features.enableOfflineTopup,
          'enableOnlinePayment': flavor.features.enableOnlinePayment,
          'enableAdsUnlock': flavor.features.enableAdsUnlock,
          'enableAccountDeletion': flavor.features.enableAccountDeletion,
        },
        'app': {
          'styleTemplate': capabilities.styleTemplate.wireValue,
          'storeComplianceMode': capabilities.storeComplianceMode.wireValue,
          'authProviders': capabilities.normalizedAuthProviders
              .map((provider) => provider.wireValue)
              .toList(),
          'consumerPaymentProviders': capabilities.visiblePaymentProviders
              .map((provider) => provider.wireValue)
              .toList(),
          'externalPaymentsAllowed': capabilities.externalPaymentsAllowed,
          'consumerLedgerScope': 'consumer',
        },
        'legal': {
          'customerServiceUrl': flavor.brand.customerServiceUrl,
          'termsUrl': flavor.brand.termsUrl,
          'privacyUrl': flavor.brand.privacyUrl,
        },
      },
    };
  }

  Map<String, Object?> _walletJson({required String requestId}) {
    return {
      'requestId': requestId,
      'status': 'ok',
      'wallet': {
        'tenantId': _tenantId,
        'accountRefMasked': _maskedAccountRef,
        'ledgerScope': 'consumer',
        'balanceCoins': _balanceCoins,
        'membershipTier': _membershipTier,
        'currency': 'coins',
      },
    };
  }

  Map<String, Object?> _walletLedgerJson({required String requestId}) {
    return {
      'requestId': requestId,
      'status': 'ok',
      'ledgerScope': 'consumer',
      'accountRefMasked': _maskedAccountRef,
      'entries': _ledger,
    };
  }

  Map<String, Object?> _paymentOptionsJson({required String requestId}) {
    final capabilities = flavor.capabilities;
    return {
      'requestId': requestId,
      'status': 'ok',
      'providers': capabilities.visiblePaymentProviders
          .map((provider) => provider.wireValue)
          .toList(),
      'packages': defaultPaymentPackages.map(_paymentPackageJson).toList(),
      'externalPaymentsAllowed': capabilities.externalPaymentsAllowed,
      'ledgerScope': 'consumer',
      'storeComplianceMode': capabilities.storeComplianceMode.wireValue,
    };
  }

  Map<String, Object?> _topupChannelsJson() {
    return {
      'requestId': _requestId('channels'),
      'status': 'ok',
      'channels': [
        {
          'id': 'demo_bank_us',
          'country': 'US',
          'method': 'bank_transfer',
          'name': 'Demo bank transfer',
          'summary': 'Upload receipt. Tenant staff approves in the console.',
          'enabled': true,
        },
        {
          'id': 'demo_wallet_sea',
          'country': 'SEA',
          'method': 'local_wallet',
          'name': 'Demo local wallet',
          'summary': 'GCash, PromptPay, OVO, or tenant configured wallet.',
          'enabled': true,
          'qrFileName': 'demo-wallet-qr.png',
        },
        {
          'id': 'demo_crypto_usdc',
          'country': 'GLOBAL',
          'method': 'crypto',
          'name': 'USDT/USDC demo address',
          'summary': 'Network and address policy are configured server-side.',
          'enabled': true,
        },
      ],
    };
  }

  Map<String, Object?> _accountJson({required String requestId}) {
    return {
      'requestId': requestId,
      'status': 'ok',
      'account': _accountBody(),
    };
  }

  Map<String, Object?> _accountBody() {
    return {
      'tenantId': _tenantId,
      'accountRefMasked': _maskedAccountRef,
      'authProviders': _authProviders,
      'membershipTier': _membershipTier,
      'deletionEndpoint': '/me/delete-request',
    };
  }

  CatalogDrama? _dramaById(String dramaId) {
    for (final drama in _seeded.catalog) {
      if (drama.dramaId == dramaId) {
        return drama;
      }
    }
    return null;
  }

  PaymentPackage? _packageById(String? packageId) {
    for (final package in defaultPaymentPackages) {
      if (package.packageId == packageId) {
        return package;
      }
    }
    return null;
  }

  Map<String, Object?> _dramaDetailJson(CatalogDrama drama) {
    return {
      'requestId': _requestId('drama'),
      'status': 'ok',
      'drama': {
        ..._catalogDramaJson(drama),
        'episodes': _episodesFor(drama).map(_episodeJson).toList(),
      },
    };
  }

  List<DramaEpisode> _episodesFor(CatalogDrama drama) {
    final count = drama.episodeCount < 1 ? 1 : drama.episodeCount;
    return List.generate(count, (index) {
      final episodeNumber = index + 1;
      return DramaEpisode(
        episodeId: index == 0
            ? 'episode_1'
            : '${drama.dramaId}_ep_${episodeNumber.toString().padLeft(3, '0')}',
        episodeNumber: episodeNumber,
        title: episodeNumber == 1
            ? 'The contract begins'
            : 'Episode $episodeNumber',
        pointPrice: index == 0 ? 0 : drama.pointPrice,
        ready: index < drama.readyEpisodeCount,
        locked: index > 0,
      );
    });
  }

  void _creditWallet(int coins, String title, {required String type}) {
    _balanceCoins += coins;
    _ledger.insert(
      0,
      _ledgerEntry(
        id: 'demo_${type}_$_sequence',
        type: type,
        title: title,
        delta: coins,
        balanceAfter: _balanceCoins,
      ),
    );
  }

  Map<String, Object?> _ledgerEntry({
    required String id,
    required String type,
    required String title,
    required int delta,
    required int balanceAfter,
    String status = 'posted',
  }) {
    return {
      'ledgerId': id,
      'type': type,
      'title': title,
      'pointsDelta': delta,
      'balanceAfter': balanceAfter,
      'createdAt': DateTime.now().toUtc().toIso8601String(),
      'status': status,
    };
  }

  String _requestId(String prefix) {
    _sequence += 1;
    return 'demo_${prefix}_$_sequence';
  }

  String get _tenantId => 'tenant_demo_${flavor.brand.tenantCode}';

  String get _maskedAccountRef => _maskAccountRef(endUserRef);
}

AdapterResponse _ok(Map<String, Object?> body, {int statusCode = 200}) {
  return AdapterResponse(statusCode: statusCode, body: jsonEncode(body));
}

AdapterResponse _error(String code, String message, int statusCode) {
  return AdapterResponse(
    statusCode: statusCode,
    body: jsonEncode({
      'error': {
        'code': code,
        'message': message,
        'requestId': 'demo_error_${DateTime.now().millisecondsSinceEpoch}',
      },
    }),
  );
}

Map<String, Object?> _catalogDramaJson(CatalogDrama drama) {
  return {
    'dramaId': drama.dramaId,
    'title': drama.title,
    'summary': drama.summary,
    'posterUrl': drama.posterUrl,
    'episodeCount': drama.episodeCount,
    'readyEpisodeCount': drama.readyEpisodeCount,
    'pointPrice': drama.pointPrice,
    'language': drama.language,
    'regions': drama.regions,
    'tags': drama.tags,
  };
}

Map<String, Object?> _episodeJson(DramaEpisode episode) {
  return {
    'episodeId': episode.episodeId,
    'episodeNumber': episode.episodeNumber,
    'title': episode.title,
    'pointPrice': episode.pointPrice,
    'ready': episode.ready,
    'locked': episode.locked,
  };
}

Map<String, Object?> _paymentPackageJson(PaymentPackage package) {
  return {
    'packageId': package.packageId,
    'title': package.title,
    'storeProductId': package.storeProductId,
    'coins': package.coins,
    'bonusCoins': package.bonusCoins,
    'amountOriginal': package.amountOriginal,
    'currency': package.currency,
  };
}

int _intValue(Object? value, {required int fallback}) {
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

String _maskEmail(String email) {
  final parts = email.split('@');
  if (parts.length != 2 || parts.first.isEmpty) {
    return 'd...o@example.com';
  }
  final local = parts.first;
  final first = local.substring(0, 1);
  return '$first...@${parts.last}';
}

String _maskAccountRef(String value) {
  if (value.length <= 8) {
    return value;
  }
  return '${value.substring(0, 6)}...${value.substring(value.length - 4)}';
}

String _demoEndUserRef(FlavorConfig flavor) {
  final raw = flavor.brand.tenantCode.toLowerCase();
  final slug = raw
      .replaceAll(RegExp(r'[^a-z0-9]+'), '-')
      .replaceAll(RegExp(r'^-+|-+$'), '');
  return 'anon:${slug.isEmpty ? 'tenant' : slug}-device';
}
