import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:short_drama_whitelabel/core/api/app_models.dart';
import 'package:short_drama_whitelabel/core/api/tenant_adapter_client.dart';

class FakeAdapterTransport implements AdapterTransport {
  FakeAdapterTransport(this.responses);

  final List<AdapterResponse> responses;
  final List<AdapterRequest> requests = [];

  @override
  Future<AdapterResponse> send(AdapterRequest request) async {
    requests.add(request);
    if (responses.isEmpty) {
      throw StateError('No fake response configured.');
    }
    return responses.removeAt(0);
  }
}

AdapterResponse ok(Map<String, dynamic> body, {int statusCode = 200}) {
  return AdapterResponse(statusCode: statusCode, body: jsonEncode(body));
}

void expectTenantEdgeOnly(AdapterRequest request) {
  expect(request.path, isNot(contains('/v1/tenant')));
  expect(request.path, isNot(contains('cloudflare')));
  expect(
    request.headers.values.join(' '),
    isNot(contains('TENANT_APP_SECRET')),
  );
}

void main() {
  test(
    'fetchConfig parses public app capabilities without secret fields',
    () async {
      final transport = FakeAdapterTransport([
        ok({
          'requestId': 'req_config_1',
          'status': 'ok',
          'config': {
            'tenant': {
              'id': 'tenant_1001',
              'appKey': 'pk_tenant_1001',
              'name': 'GoldFruit Drama',
              'brandName': 'DramaHub',
              'defaultLocale': 'en-US',
              'supportedLocales': ['en-US', 'zh-CN'],
            },
            'features': {
              'enableCardRedeem': false,
              'enableOfflineTopup': false,
              'enableOnlinePayment': false,
              'enableAdsUnlock': true,
              'enableAccountDeletion': true,
            },
            'app': {
              'styleTemplate': 'douyin_inspired',
              'storeComplianceMode': 'android_direct',
              'authProviders': ['email', 'google', 'facebook'],
              'consumerPaymentProviders': ['stripe', 'paypal', 'point_card'],
              'externalPaymentsAllowed': true,
              'consumerLedgerScope': 'consumer',
            },
            'theme': {
              'primaryColor': '#00D4FF',
              'logoUrl': '/assets/brand/logo.png',
              'posterAspectRatio': '2:3',
            },
            'legal': {
              'customerServiceUrl': '/support',
              'termsUrl': '/terms',
              'privacyUrl': '/privacy',
            },
            'endpoints': {
              'config': '/config',
              'catalog': '/catalog',
              'dramaDetail': '/dramas/{dramaId}',
              'play': '/play',
              'me': '/me',
              'wallet': '/wallet',
              'paymentOptions': '/payment/options',
              'paymentIntent': '/payment/intents',
              'paymentStorePurchaseVerify':
                  '/payment/store-purchases/verify',
              'paymentCardRedeem': '/payment/card-redeem',
            },
          },
        }),
      ]);
      final client = TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      );

      final config = await client.fetchConfig();

      expect(config.appName, 'GoldFruit Drama');
      expect(config.capabilities.styleTemplate.wireValue, 'douyin_inspired');
      expect(
        config.capabilities.storeComplianceMode.wireValue,
        'android_direct',
      );
      expect(
        config.capabilities.visiblePaymentProviders.map(
          (provider) => provider.wireValue,
        ),
        contains('point_card'),
      );
      expect(config.legal.privacyUrl, '/privacy');
      expect(
        jsonEncode(config.toPublicJson()).toLowerCase(),
        isNot(contains('secret')),
      );
      expect(transport.requests.single.path, '/config');
      expectTenantEdgeOnly(transport.requests.single);
    },
  );

  test('fetchWallet, ledger, and paymentOptions stay in consumer scope',
      () async {
    final transport = FakeAdapterTransport([
      ok({
        'requestId': 'req_wallet_1',
        'status': 'ok',
        'wallet': {
          'tenantId': 'tenant_1001',
          'accountRefMasked': 'anon:d...3456',
          'ledgerScope': 'consumer',
          'balanceCoins': 120,
          'membershipTier': 'vip',
          'currency': 'coins',
        },
      }),
      ok({
        'requestId': 'req_wallet_ledger_1',
        'status': 'ok',
        'ledgerScope': 'consumer',
        'accountRefMasked': 'anon:d...3456',
        'entries': [
          {
            'ledgerId': 'consumer_ledger_1',
            'type': 'point_card',
            'title': 'Point card recharge',
            'pointsDelta': 100,
            'balanceAfter': 120,
            'createdAt': '2026-06-14T00:00:00Z',
            'status': 'posted',
          },
        ],
      }),
      ok({
        'requestId': 'req_payment_options_1',
        'status': 'ok',
        'providers': ['stripe', 'paypal', 'point_card'],
        'packages': [
          {
            'packageId': 'coins_300',
            'title': '300 coins',
            'storeProductId': 'com.example.drama.coins300',
            'coins': 300,
            'bonusCoins': 30,
            'amountOriginal': 24,
            'currency': 'USD',
          },
        ],
        'externalPaymentsAllowed': true,
        'ledgerScope': 'consumer',
        'storeComplianceMode': 'android_direct',
      }),
    ]);
    final client = TenantAdapterClient(
      baseUri: Uri.parse('https://tenant-edge.example.test'),
      transport: transport,
    );

    final wallet = await client.fetchWallet(
      deviceId: 'anon:device-full-value-123456',
    );
    final ledger = await client.fetchWalletLedger(
      deviceId: 'anon:device-full-value-123456',
    );
    final options = await client.fetchPaymentOptions();

    expect(wallet.balanceCoins, 120);
    expect(wallet.ledgerScope, 'consumer');
    expect(wallet.accountRefMasked, isNot(contains('device-full-value')));
    expect(ledger.ledgerScope, 'consumer');
    expect(ledger.accountRefMasked, isNot(contains('device-full-value')));
    expect(ledger.entries.single.ledgerId, 'consumer_ledger_1');
    expect(ledger.entries.single.pointsDelta, 100);
    expect(ledger.entries.single.balanceAfter, 120);
    expect(options.providers, ['stripe', 'paypal', 'point_card']);
    expect(options.packages.single.packageId, 'coins_300');
    expect(options.packages.single.storeProductId, 'com.example.drama.coins300');
    expect(options.packages.single.totalCoins, 330);
    expect(options.ledgerScope, 'consumer');
    expect(transport.requests.map((request) => request.path), [
      '/wallet',
      '/wallet/ledger',
      '/payment/options',
    ]);
    for (final request in transport.requests) {
      expectTenantEdgeOnly(request);
    }
  });

  test(
    'fetchTopupPaymentChannels parses public channel summaries without raw config',
    () async {
      final transport = FakeAdapterTransport([
        ok({
          'requestId': 'req_channels_1',
          'status': 'ok',
          'channels': [
            {
              'id': 'payment_bca',
              'country': 'ID',
              'method': '银行卡',
              'name': 'BCA Bank',
              'summary': 'account: 123***7800',
              'enabled': true,
              'qrFileName': 'bca-bank-qr.png',
              'qrImageUrl':
                  'https://media.example.test/payment-qrs/bca-bank-qr.png',
            },
          ],
        }),
      ]);
      final client = TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      );

      final channels = await client.fetchTopupPaymentChannels();

      expect(channels.requestId, 'req_channels_1');
      expect(channels.channels.single.id, 'payment_bca');
      expect(channels.channels.single.summary, 'account: 123***7800');
      expect(
        channels.channels.single.qrImageUrl,
        'https://media.example.test/payment-qrs/bca-bank-qr.png',
      );
      expect(jsonEncode(channels.channels.single.toPublicJson()),
          isNot(contains('1234567800')));
      expect(transport.requests.single.path, '/topups/payment-channels');
      expectTenantEdgeOnly(transport.requests.single);
    },
  );

  test(
    'createPaymentIntent returns app-safe order without provider client secret',
    () async {
      final transport = FakeAdapterTransport([
        ok({
          'requestId': 'req_payment_1',
          'status': 'requires_provider_confirmation',
          'orderId': 'consumer_order_req_payment_1',
          'provider': 'stripe',
          'packageId': 'coins_100',
          'amountOriginal': 9,
          'currency': 'USD',
          'ledgerScope': 'consumer',
          'storeComplianceMode': 'android_direct',
          'checkoutUrl':
              'https://tenant.example.test/payment/checkout?orderId=consumer_order_req_payment_1&provider=stripe',
        }, statusCode: 202),
      ]);
      final client = TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      );

      final intent = await client.createPaymentIntent(
        provider: 'stripe',
        packageId: 'coins_100',
        amountOriginal: 9,
        currency: 'USD',
        endUserRef: 'anon:device_1',
        idempotencyKey: 'consumer-pay-1',
      );

      expect(intent.orderId, 'consumer_order_req_payment_1');
      expect(intent.ledgerScope, 'consumer');
      expect(
        intent.checkoutUrl,
        'https://tenant.example.test/payment/checkout?orderId=consumer_order_req_payment_1&provider=stripe',
      );
      expect(transport.requests.single.path, '/payment/intents');
      expect(
        transport.requests.single.headers['idempotency-key'],
        'consumer-pay-1',
      );
      expect(transport.requests.single.body?['provider'], 'stripe');
      expect(transport.requests.single.body?['endUserRef'], 'anon:device_1');
      expectTenantEdgeOnly(transport.requests.single);
    },
  );

  test(
    'verifyStorePurchase posts native receipt to Tenant Edge only',
    () async {
      final transport = FakeAdapterTransport([
        ok({
          'requestId': 'req_store_purchase_1',
          'status': 'verification_received',
          'orderId': 'consumer_store_order_1',
          'provider': 'iap',
          'packageId': 'coins_100',
          'amountOriginal': 9,
          'currency': 'USD',
          'ledgerScope': 'consumer',
          'storeComplianceMode': 'app_store',
        }, statusCode: 202),
      ]);
      final client = TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      );

      final result = await client.verifyStorePurchase(
        provider: 'iap',
        packageId: 'coins_100',
        productId: 'com.example.drama.coins100',
        transactionId: 'txn_store_100',
        purchaseToken: 'store-token-value',
        verificationData: 'signed-store-receipt',
        verificationSource: 'app_store',
        endUserRef: 'anon:device_1',
        idempotencyKey: 'store-purchase-1',
      );

      expect(result.orderId, 'consumer_store_order_1');
      expect(result.status, 'verification_received');
      expect(result.ledgerScope, 'consumer');
      expect(transport.requests.single.path, '/payment/store-purchases/verify');
      expect(
        transport.requests.single.headers['idempotency-key'],
        'store-purchase-1',
      );
      expect(transport.requests.single.body?['provider'], 'iap');
      expect(
        transport.requests.single.body?['productId'],
        'com.example.drama.coins100',
      );
      expect(
        transport.requests.single.body?['verificationData'],
        'signed-store-receipt',
      );
      expect(transport.requests.single.body?['endUserRef'], 'anon:device_1');
      expectTenantEdgeOnly(transport.requests.single);
    },
  );

  test(
    'submitConsumerOfflineApplication forwards runtime end-user reference',
    () async {
      final transport = FakeAdapterTransport([
        ok({
          'requestId': 'req_consumer_offline_1',
          'status': 'pending',
          'applicationId': 'consumer_topup_1',
          'requestedCoins': 100,
        }, statusCode: 201),
      ]);
      final client = TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      );

      final result = await client.submitConsumerOfflineApplication(
        provider: 'bank_transfer',
        amountOriginal: 9,
        currency: 'USD',
        requestedCoins: 120,
        endUserRef: 'anon:device_1',
        idempotencyKey: 'consumer-offline-1',
      );

      expect(result.applicationId, 'consumer_topup_1');
      expect(result.requestedPoints, 100);
      expect(transport.requests.single.path, '/payment/offline-applications');
      expect(
        transport.requests.single.headers['idempotency-key'],
        'consumer-offline-1',
      );
      expect(transport.requests.single.body?['provider'], 'bank_transfer');
      expect(transport.requests.single.body?['requestedPoints'], 120);
      expect(transport.requests.single.body?['requestedBy'], 'anon:device_1');
      expectTenantEdgeOnly(transport.requests.single);
    },
  );

  test(
    'starts email and oauth login without app-side provider secrets',
    () async {
      final transport = FakeAdapterTransport([
        ok({
          'requestId': 'req_email_1',
          'status': 'accepted',
          'provider': 'email',
          'challengeId': 'email_reqemail1',
          'emailMasked': 'u...e@example.com',
        }, statusCode: 202),
        ok({
          'requestId': 'req_email_verify_1',
          'status': 'verified',
          'provider': 'email',
          'account': {
            'tenantId': 'tenant_1001',
            'accountRefMasked': 'anon:d...3456',
            'authProviders': ['email', 'google'],
            'membershipTier': 'registered',
            'deletionEndpoint': '/me/delete-request',
          },
        }),
        ok({
          'requestId': 'req_oauth_1',
          'status': 'ready',
          'provider': 'google',
          'oauthStartId': 'oauth_reqoauth1',
          'tenantId': 'tenant_1001',
          'authUrl':
              'https://tenant.example.test/auth/oauth/google/authorize?oauthStartId=oauth_reqoauth1',
        }),
        ok({
          'requestId': 'req_oauth_complete_1',
          'status': 'verified',
          'provider': 'google',
          'account': {
            'tenantId': 'tenant_1001',
            'accountRefMasked': 'anon:d...3456',
            'authProviders': ['email', 'google'],
            'membershipTier': 'registered',
            'deletionEndpoint': '/me/delete-request',
          },
        }),
      ]);
      final client = TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      );

      final email = await client.startEmailAuth(
        email: 'user@example.com',
        endUserRef: 'anon:device-full-value-123456',
      );
      final verified = await client.verifyEmailAuth(
        challengeId: email.challengeId,
        code: '123456',
        endUserRef: 'anon:device-full-value-123456',
      );
      final oauth = await client.startOAuth(
        provider: 'google',
        endUserRef: 'anon:device-full-value-123456',
      );
      final oauthVerified = await client.completeOAuth(
        provider: 'google',
        oauthStartId: oauth.oauthStartId,
        code: 'oauth-code-public',
        state: 'oauth-state-public',
        endUserRef: 'anon:device-full-value-123456',
      );

      expect(email.challengeId, 'email_reqemail1');
      expect(email.emailMasked, isNot(contains('user@example.com')));
      expect(verified.account.accountRefMasked, 'anon:d...3456');
      expect(verified.account.membershipTier, 'registered');
      expect(oauth.oauthStartId, 'oauth_reqoauth1');
      expect(
        oauth.authUrl,
        'https://tenant.example.test/auth/oauth/google/authorize?oauthStartId=oauth_reqoauth1',
      );
      expect(oauthVerified.account.accountRefMasked, 'anon:d...3456');
      expect(oauthVerified.account.membershipTier, 'registered');
      expect(transport.requests.map((request) => request.path), [
        '/auth/email/start',
        '/auth/email/verify',
        '/auth/oauth/google/start',
        '/auth/oauth/google/complete',
      ]);
      expect(
        transport.requests.first.body?['endUserRef'],
        'anon:device-full-value-123456',
      );
      expect(
        transport.requests[1].body?['endUserRef'],
        'anon:device-full-value-123456',
      );
      expect(
        transport.requests[2].body?['endUserRef'],
        'anon:device-full-value-123456',
      );
      expect(
        transport.requests[3].body?['endUserRef'],
        'anon:device-full-value-123456',
      );
      expect(transport.requests[3].body?['code'], 'oauth-code-public');
      expect(transport.requests[3].body?['state'], 'oauth-state-public');
      for (final request in transport.requests) {
        expectTenantEdgeOnly(request);
        expect(
          jsonEncode(request.body ?? const {}).toLowerCase(),
          isNot(contains('secret')),
        );
      }
    },
  );

  test(
    'fetchMe parses masked account state and C-end deletion endpoint',
    () async {
      final transport = FakeAdapterTransport([
        ok({
          'requestId': 'req_me_1',
          'status': 'ok',
          'account': {
            'tenantId': 'tenant_1001',
            'accountRefMasked': 'anon:d...3456',
            'authProviders': ['email', 'google'],
            'membershipTier': 'guest',
            'deletionEndpoint': '/me/delete-request',
          },
        }),
      ]);
      final client = TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      );

      final account = await client.fetchMe(
        deviceId: 'anon:device-full-value-123456',
      );

      expect(account.accountRefMasked, 'anon:d...3456');
      expect(account.accountRefMasked, isNot(contains('device-full-value')));
      expect(account.deletionEndpoint, '/me/delete-request');
      expect(transport.requests.single.path, '/me');
      expectTenantEdgeOnly(transport.requests.single);
    },
  );

  test(
    'authorizePlayback parses safe player URL instead of raw manifest URL',
    () async {
      final transport = FakeAdapterTransport([
        ok({
          'requestId': 'req_play_1',
          'status': 'authorized',
          'grantId': 'grant_1',
          'charge': {'points': 2, 'balanceAfter': 8},
          'playback': {
            'provider': 'cloudflare_stream',
            'tokenExpiresAt': '2026-06-07T08:00:00.000Z',
            'manifestHost': 'videodelivery.net',
            'iframeUrl': 'https://iframe.videodelivery.net/asset',
            'playerUrl': 'https://iframe.videodelivery.net/asset',
          },
        }),
      ]);
      final client = TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      );

      final result = await client.authorizePlayback(
        dramaId: 'drama_1',
        episodeId: 'episode_1',
        endUserRef: 'anon:device_1',
        idempotencyKey: 'play-idem-1',
      );

      expect(result.playerUrl, 'https://iframe.videodelivery.net/asset');
      expect(result.manifestHost, 'videodelivery.net');
      expect(result.playerUrl, isNot(contains('/manifest/')));
      expect(transport.requests.single.path, '/play');
      expectTenantEdgeOnly(transport.requests.single);
    },
  );

  test(
    'fetchDrama calls Tenant Edge detail path and parses episodes',
    () async {
      final transport = FakeAdapterTransport([
        ok({
          'requestId': 'req_detail_1',
          'status': 'ok',
          'drama': {
            'dramaId': 'drama_1',
            'title': 'Seed Drama',
            'posterUrl': '/assets/posters/1.png',
            'episodeCount': 1,
            'readyEpisodeCount': 1,
            'pointPrice': 2,
            'episodes': [
              {
                'episodeId': 'episode_1',
                'episodeNumber': 1,
                'title': 'Episode 1',
                'pointPrice': 2,
                'ready': true,
                'locked': false,
              },
            ],
          },
        }),
      ]);
      final client = TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      );

      final detail = await client.fetchDrama('drama_1');

      expect(transport.requests.single.method, 'GET');
      expect(transport.requests.single.path, '/dramas/drama_1');
      expectTenantEdgeOnly(transport.requests.single);
      expect(detail.drama.title, 'Seed Drama');
      expect(detail.episodes.single.episodeId, 'episode_1');
    },
  );

  test(
    'redeemConsumerCard stays on C-end payment card scope',
    () async {
      final transport = FakeAdapterTransport([
        ok({
          'requestId': 'req_consumer_card_1',
          'status': 'redeemed',
          'creditedPoints': 120,
          'balanceAfter': 240,
        }),
      ]);
      final client = TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      );

      final result = await client.redeemConsumerCard(
        cardCode: 'CP01-CONSUMER',
        endUserRef: 'anon:device_1',
        idempotencyKey: 'consumer-card-1',
      );

      expect(result.creditedPoints, 120);
      expect(result.balanceAfter, 240);
      expect(transport.requests.single.path, '/payment/card-redeem');
      expect(
        transport.requests.single.headers['idempotency-key'],
        'consumer-card-1',
      );
      expect(transport.requests.single.body, {
        'cardCode': 'CP01-CONSUMER',
        'endUserRef': 'anon:device_1',
      });
      expectTenantEdgeOnly(transport.requests.single);
    },
  );

  test(
    'redeemCard sends idempotency key to Tenant Edge and parses result',
    () async {
      final transport = FakeAdapterTransport([
        ok({
          'requestId': 'req_card_1',
          'status': 'redeemed',
          'creditedPoints': 1000,
          'balanceAfter': 2500,
        }),
      ]);
      final client = TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      );

      final result = await client.redeemCard(
        cardCode: 'PK01-TEST',
        idempotencyKey: 'card-idem-1',
      );

      expect(result, isA<CardRedeemResult>());
      expect(result.creditedPoints, 1000);
      expect(transport.requests.single.path, '/cards/redeem');
      expect(
        transport.requests.single.headers['idempotency-key'],
        'card-idem-1',
      );
      expectTenantEdgeOnly(transport.requests.single);
    },
  );

  test(
    'submitOfflineTopup calls app boundary and parses pending application',
    () async {
      final transport = FakeAdapterTransport([
        ok({
          'requestId': 'req_topup_1',
          'status': 'pending',
          'applicationId': 'topup_1',
          'requestedPoints': 1000,
        }, statusCode: 201),
      ]);
      final client = TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      );

      final result = await client.submitOfflineTopup(
        amountOriginal: 100,
        currency: 'USD',
        requestedPoints: 1000,
        idempotencyKey: 'topup-idem-1',
        requestedBy: 'anon:device_1',
      );

      expect(result, isA<OfflineTopupApplicationResult>());
      expect(result.status, 'pending');
      expect(transport.requests.single.path, '/topups/offline-applications');
      expect(
        transport.requests.single.headers['idempotency-key'],
        'topup-idem-1',
      );
      expect(transport.requests.single.body?['requestedBy'], 'anon:device_1');
      expectTenantEdgeOnly(transport.requests.single);
    },
  );

  test('submitFeedback stays on Tenant Edge feedback path', () async {
    final transport = FakeAdapterTransport([
      ok({
        'requestId': 'req_feedback_1',
        'status': 'accepted',
        'feedbackId': 'feedback_1',
        'category': 'playback',
        'hasMessage': true,
      }, statusCode: 202),
    ]);
    final client = TenantAdapterClient(
      baseUri: Uri.parse('https://tenant-edge.example.test'),
      transport: transport,
    );

    final result = await client.submitFeedback(
      category: 'playback',
      message: 'Episode 1 buffers.',
      dramaId: 'drama_1',
      episodeId: 'episode_1',
      endUserRef: 'anon:device_1',
    );

    expect(result, isA<FeedbackResult>());
    expect(result.feedbackId, 'feedback_1');
    expect(result.hasMessage, isTrue);
    expect(transport.requests.single.path, '/feedback');
    expectTenantEdgeOnly(transport.requests.single);
  });

  test('submitAccountDelete parses masked account ref only', () async {
    final transport = FakeAdapterTransport([
      ok({
        'requestId': 'req_delete_1',
        'status': 'accepted',
        'deletionRequestId': 'delete_1',
        'accountRefMasked': 'anon:d...3456',
      }, statusCode: 202),
    ]);
    final client = TenantAdapterClient(
      baseUri: Uri.parse('https://tenant-edge.example.test'),
      transport: transport,
    );

    final result = await client.submitAccountDelete(
      accountRef: 'anon:device-full-value-123456',
    );

    expect(result, isA<AccountDeletionRequestResult>());
    expect(result.accountRefMasked, 'anon:d...3456');
    expect(result.accountRefMasked, isNot(contains('device-full-value')));
    expect(transport.requests.single.path, '/me/delete-request');
    expectTenantEdgeOnly(transport.requests.single);
  });

  test('client maps Tenant Edge error response into AppApiException', () async {
    final transport = FakeAdapterTransport([
      ok({
        'error': {
          'code': 'APP_FEATURE_DISABLED',
          'message': 'Point-card redeem is disabled.',
          'requestId': 'req_error_1',
        },
      }, statusCode: 403),
    ]);
    final client = TenantAdapterClient(
      baseUri: Uri.parse('https://tenant-edge.example.test'),
      transport: transport,
    );

    await expectLater(
      client.redeemCard(cardCode: 'PK01-TEST', idempotencyKey: 'card-idem-1'),
      throwsA(isA<AppApiException>()),
    );
    expect(transport.requests.single.path, '/cards/redeem');
    expectTenantEdgeOnly(transport.requests.single);
  });
}
